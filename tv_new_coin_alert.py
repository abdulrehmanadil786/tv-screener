#!/usr/bin/env python3
"""
TradingView Crypto Coins Screener -> New Coin Alert Bot
=========================================================

Watches a TradingView "Crypto Coins Screener" query (same one you build on
tradingview.com) and fires a Telegram + Email alert the moment a NEW coin
starts matching your filter conditions.

Requires no TradingView login for the filters used here (Market Cap, 24h
Change, Perf YTD, Volume). Runs in an infinite loop, polling every
POLL_INTERVAL_SECONDS.

Setup:
    pip install tradingview-screener requests --break-system-packages
    cp config.example.json config.json
    # edit config.json with your Telegram bot token / chat id / email creds
    python3 tv_new_coin_alert.py

See README.md for full setup instructions (Telegram bot, Gmail app
password, Termux background running, and how to verify the two
"unconfirmed" field names below).
"""

from __future__ import annotations

import json
import logging
import smtplib
import sys
import time
import traceback
from email.mime.text import MIMEText
from pathlib import Path

from tradingview_screener import Query, col
from tradingview_screener.screeners import coin

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"
LOG_PATH = BASE_DIR / "screener.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("tv_screener")

# ---------------------------------------------------------------------------
# Field names used for your filters.
#
# CONFIRMED (pulled directly from the tradingview_screener package's own
# built-in `coin()` screener definition -- these are exactly what TradingView's
# Crypto Coins Screener UI uses):
#   market_cap_calc          -> "Mkt cap"
#   24h_vol_cmc               -> "Vol in USD"
#   24h_close_change|5        -> "Chg, 24h"
#   24h_vol_to_market_cap     -> "Vol / mkt cap"
#   fully_diluted_value       -> "FD mkt cap"
#
# HIGH CONFIDENCE (standard TradingView-wide field, used the same way across
# stocks/crypto/forex screeners):
#   Perf.YTD                  -> "Perf, YTD"
#
# NEEDS YOUR CONFIRMATION -- these are less common / newer fields and I could
# not verify their exact key from here. See README.md "Verifying field
# names" section for a 30-second DevTools check.
#   24h_vol_change            -> "Vol chg, 24h"   (best guess)
#   long_liquidations_24h     -> "Long liquidations, 24h"   (placeholder guess)
# ---------------------------------------------------------------------------

FIELDS = {
    "market_cap": "market_cap_calc",
    "volume_usd": "24h_vol_cmc",
    "change_24h": "24h_close_change|5",
    "vol_to_mktcap": "24h_vol_to_market_cap",
    "fd_market_cap": "fully_diluted_value",
    "perf_ytd": "Perf.YTD",
    "vol_change_24h": "24h_vol_change",         # <-- verify me
    "long_liquidations_24h": "long_liquidations_24h",  # <-- verify me
}

DISPLAY_COLUMNS = [
    "name",
    FIELDS["market_cap"],
    FIELDS["volume_usd"],
    FIELDS["change_24h"],
    FIELDS["perf_ytd"],
    FIELDS["vol_change_24h"],
    FIELDS["long_liquidations_24h"],
]


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        log.error(
            "config.json not found. Copy config.example.json to config.json "
            "and fill in your filter thresholds first."
        )
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Secrets: prefer environment variables (GitHub Actions secrets) over
    # whatever is in config.json, so the same script works both on Termux
    # (values live in config.json) and on GitHub Actions (values live in
    # repo Secrets and never touch the committed file).
    import os

    tg = cfg.setdefault("telegram", {})
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        tg["enabled"] = True
        tg["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
        tg["chat_id"] = os.environ["TELEGRAM_CHAT_ID"]

    em = cfg.setdefault("email", {})
    if os.environ.get("EMAIL_SMTP_USER"):
        em["enabled"] = True
        em["smtp_host"] = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
        em["smtp_port"] = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
        em["smtp_user"] = os.environ["EMAIL_SMTP_USER"]
        em["smtp_password"] = os.environ["EMAIL_SMTP_PASSWORD"]
        em["from_addr"] = os.environ.get("EMAIL_FROM", em["smtp_user"])
        em["to_addr"] = os.environ.get("EMAIL_TO", em["smtp_user"])

    return cfg


def load_state() -> set[str]:
    if not STATE_PATH.exists():
        return set()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f).get("seen_symbols", []))
    except (json.JSONDecodeError, OSError):
        log.warning("state.json unreadable, starting fresh.")
        return set()


def save_state(symbols: set[str]) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"seen_symbols": sorted(symbols), "updated": time.time()}, f, indent=2)
    tmp.replace(STATE_PATH)


def build_query(cfg: dict):
    f = cfg["filters"]
    q = coin()
    q.select(*DISPLAY_COLUMNS)
    q.where(
        col(FIELDS["market_cap"]).between(f["market_cap_min"], f["market_cap_max"]),
        col(FIELDS["change_24h"]) > f["change_24h_gt"],
        col(FIELDS["perf_ytd"]) < f["perf_ytd_lt"],
        col(FIELDS["vol_change_24h"]) > f["vol_change_24h_gt"],
        col(FIELDS["long_liquidations_24h"]) > f["long_liquidations_gt"],
    )
    q.limit(200)
    return q


def run_scan(cfg: dict):
    q = build_query(cfg)
    _, df = q.get_scanner_data()
    return df


def send_telegram(cfg: dict, message: str) -> None:
    tg = cfg.get("telegram", {})
    if not tg.get("enabled", False):
        return
    import requests

    url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={"chat_id": tg["chat_id"], "text": message, "parse_mode": "HTML"},
            timeout=15,
        )
        if resp.status_code != 200:
            log.error("Telegram send failed: %s %s", resp.status_code, resp.text)
    except Exception:
        log.error("Telegram send exception:\n%s", traceback.format_exc())


def send_email(cfg: dict, subject: str, message: str) -> None:
    em = cfg.get("email", {})
    if not em.get("enabled", False):
        return
    try:
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = em["from_addr"]
        msg["To"] = em["to_addr"]

        with smtplib.SMTP(em["smtp_host"], em["smtp_port"]) as server:
            server.starttls()
            server.login(em["smtp_user"], em["smtp_password"])
            server.sendmail(em["from_addr"], [em["to_addr"]], msg.as_string())
    except Exception:
        log.error("Email send exception:\n%s", traceback.format_exc())


def format_alert(row) -> str:
    name = row.get("name", "?")
    mkt_cap = row.get(FIELDS["market_cap"])
    vol = row.get(FIELDS["volume_usd"])
    chg = row.get(FIELDS["change_24h"])
    perf_ytd = row.get(FIELDS["perf_ytd"])
    vol_chg = row.get(FIELDS["vol_change_24h"])
    liq = row.get(FIELDS["long_liquidations_24h"])
    return (
        f"\U0001F6A8 New coin matched your screener: {name}\n"
        f"Mkt Cap: {mkt_cap:,.0f}\n"
        f"Vol (24h): {vol:,.0f}\n"
        f"Chg 24h: {chg:.2f}%\n"
        f"Perf YTD: {perf_ytd:.2f}%\n"
        f"Vol chg 24h: {vol_chg:.2f}%\n"
        f"Long liquidations 24h: {liq:,.0f}"
    )


def run_cycle(cfg: dict, seen: set[str], first_run: bool) -> tuple[set[str], bool]:
    """Runs one scan-and-compare cycle. Returns the updated (seen, first_run)."""
    df = run_scan(cfg)
    current_symbols = set(df["ticker"]) if "ticker" in df.columns else set(df.index.astype(str))

    if first_run:
        log.info(
            "First run: baselining %d coins currently matching the filter "
            "(no alerts fired for these).",
            len(current_symbols),
        )
        save_state(current_symbols)
        return current_symbols, False

    new_symbols = current_symbols - seen
    if new_symbols:
        log.info("New matches: %s", new_symbols)
        for _, row in df.iterrows():
            ticker = row.get("ticker", row.get("name"))
            if ticker in new_symbols:
                alert_text = format_alert(row)
                send_telegram(cfg, alert_text)
                send_email(cfg, "New coin matched your TradingView screener", alert_text)
                log.info("Alert sent for %s", ticker)
    else:
        log.info("No new matches this cycle. %d coins currently match.", len(current_symbols))

    save_state(current_symbols)
    return current_symbols, False


def main():
    import os

    cfg = load_config()
    seen = load_state()
    first_run = len(seen) == 0

    # RUN_ONCE=1 (set automatically on GitHub Actions) -> do a single cycle
    # and exit, letting the workflow's cron schedule act as the "loop".
    # Otherwise (Termux/local) -> loop forever with poll_interval_seconds.
    run_once = os.environ.get("RUN_ONCE", "0") == "1"

    if run_once:
        try:
            run_cycle(cfg, seen, first_run)
        except Exception:
            log.error("Scan cycle failed:\n%s", traceback.format_exc())
            sys.exit(1)
        return

    poll_seconds = cfg.get("poll_interval_seconds", 300)
    log.info("Starting screener loop. Poll interval: %ss", poll_seconds)
    while True:
        try:
            seen, first_run = run_cycle(cfg, seen, first_run)
        except Exception:
            log.error("Scan cycle failed:\n%s", traceback.format_exc())
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
