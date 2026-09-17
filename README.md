# TradingView Crypto Coins Screener → New Coin Alert (Telegram + Email)

Watches your TradingView "Crypto Coins Screener" filters and pings you on
Telegram and Email the moment a **new coin** starts matching them.

Filters currently configured (from your screenshot):
- Market cap: 10M – 800M USD
- Chg, 24h: > 0%
- Perf, YTD: < -30%
- Vol chg, 24h: > 20%
- Long liquidations, 24h: > 1M

No TradingView login/API key is needed for these fields — it uses the same
public scanner endpoint TradingView's own screener page calls.

---

## Option A: Run for free on GitHub Actions (recommended — no phone/server needed)

This runs entirely on GitHub's own servers on a schedule (every 10 minutes
by default). Your phone can be off. Nothing to host, nothing to pay for.

1. Create a **new GitHub repo** (public is simplest — public repos get
   unlimited free Actions minutes; private repos get 2,000 free
   minutes/month, which is enough for a 10-min interval but tighter).
2. Push everything in this folder to that repo, including the
   `.github/workflows/screener.yml` file and `config.json` (it's safe to
   commit — it only has filter thresholds, no secrets).
3. In the repo, go to **Settings → Secrets and variables → Actions →
   New repository secret** and add these one at a time:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `EMAIL_SMTP_USER` (your Gmail address)
   - `EMAIL_SMTP_PASSWORD` (your 16-char Gmail app password)
   - `EMAIL_FROM` (same as EMAIL_SMTP_USER)
   - `EMAIL_TO` (where you want alerts sent)
   - (`EMAIL_SMTP_HOST` / `EMAIL_SMTP_PORT` are optional — default to
     Gmail's `smtp.gmail.com` / `587` if you skip them)
4. Go to the **Actions** tab → you should see "TV Coin Screener" listed →
   click it → **Run workflow** to trigger a manual first run and confirm
   it works (check the run's logs).
5. After that, it runs automatically every 10 minutes via the cron
   schedule in `screener.yml`. Each run commits an updated `state.json`
   back to the repo so it remembers what it's already alerted on.

**Two things to know:**
- GitHub auto-disables scheduled workflows on a repo after **60 days with
  no commits/activity** — if you don't touch the repo for 2 months, just
  re-enable it from the Actions tab (Settings → Actions → re-enable, or
  push any small commit).
- Cron timing on GitHub isn't exact-to-the-minute under load — treat
  "every 10 min" as "roughly every 10 min," not a hard guarantee.

To adjust how often it runs, edit the `cron:` line in
`.github/workflows/screener.yml` (format: minute hour day month weekday).

**Before relying on it**, verify the two uncertain field names (see
"Verify the two uncertain field names" under Option B below — same steps
apply, just run `debug_fields.py` locally on your computer once, or as a
one-off manual Actions run and check its logs).

---

## Option B: Run on Termux (your phone, must stay on with internet)

## 1. Install on Termux

```bash
pkg update && pkg install python -y
pip install -r requirements.txt
```

## 2. Set up Telegram alerts

1. Message **@BotFather** on Telegram → `/newbot` → follow prompts → copy
   the **bot token** it gives you.
2. Message your new bot anything (e.g. "hi") so it can message you back.
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser
   — find `"chat":{"id": ...}` in the response, that's your **chat_id**.
4. Put both into `config.json` under `"telegram"`.

## 3. Set up Email alerts (Gmail example)

1. Turn on 2-Step Verification on your Google account.
2. Go to https://myaccount.google.com/apppasswords → generate an **App
   Password** for "Mail".
3. Put your Gmail address as `smtp_user`/`from_addr`/`to_addr`, and the
   16-character app password as `smtp_password` in `config.json`.
4. Using a different email provider? Just change `smtp_host`/`smtp_port` to
   match theirs.

## 4. Configure

```bash
cp config.example.json config.json
nano config.json   # fill in telegram + email details, adjust filters if needed
```

## 5. Verify the two uncertain field names (important, ~1 minute)

I pulled `market_cap_calc`, `24h_vol_cmc`, `24h_close_change|5`,
`24h_vol_to_market_cap`, and `fully_diluted_value` directly from the
TradingView screener package's source code, so those are confirmed correct.
`Perf.YTD` is a standard TradingView-wide field name, also high confidence.

Two fields I could **not** verify offline:
- `24h_vol_change` (for "Vol chg, 24h")
- `long_liquidations_24h` (for "Long liquidations, 24h") — this one is a
  guess/placeholder and likely needs correcting.

Run this once you have internet on your phone:

```bash
python3 debug_fields.py
```

It prints a table of real data. If a column is entirely blank/`NaN` across
every row, that field name is wrong.

**To find the correct name for real:**
1. Open your TradingView Crypto Coins Screener in a desktop browser.
2. Open DevTools (F12) → **Network** tab.
3. Reload the page or nudge a filter slightly.
4. Find the request to `scanner.tradingview.com/coin/scan` → click it →
   view the **Payload/Request body**.
5. Inside `"filter2"` (or `"filter"`), you'll see the exact field key
   TradingView uses for each of your filter chips — e.g. it might show
   something like `"left": "Long.Liquidations|1D"`. That's the real name.
6. Update `FIELDS["vol_change_24h"]` and `FIELDS["long_liquidations_24h"]`
   at the top of `tv_new_coin_alert.py` with the correct value(s), then
   re-run `debug_fields.py` to confirm the column now has real numbers.

## 6. Run it

```bash
python3 tv_new_coin_alert.py
```

First run just baselines the coins currently matching (no alert spam for
existing matches) — after that, only genuinely *new* matches trigger
Telegram + Email alerts.

## 7. Keep it running in the background on Termux

```bash
termux-wake-lock                     # stop Android from killing it
nohup python3 tv_new_coin_alert.py > /dev/null 2>&1 &
```

To check it's alive later: `tail -f screener.log`

Optional: install **Termux:Boot** (from F-Droid) and drop a start script in
`~/.termux/boot/` so it auto-starts after a phone reboot.

## Notes

- `poll_interval_seconds` in `config.json` controls how often it checks
  (default 300s = 5 min). TradingView's public scanner endpoint is
  rate-limited per IP — don't go much below ~60s.
- `state.json` tracks which coins currently match, so restarting the
  script won't re-fire alerts for coins already matching before restart —
  but it WILL re-baseline if you delete `state.json`.
- A coin that drops out of the filter and later re-qualifies will alert
  again (by design — that's a fresh "new match" event).
