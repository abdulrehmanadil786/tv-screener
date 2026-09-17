#!/usr/bin/env python3
"""
Run this once after setup to sanity-check the field names used in
tv_new_coin_alert.py -- especially the two "needs your confirmation" fields
(24h_vol_change and long_liquidations_24h).

Usage:
    python3 debug_fields.py

What to look for:
  - If a field name is WRONG, the tradingview_screener package will usually
    raise an error mentioning the invalid column, OR the column will come
    back as all None/NaN for every single row (a real field will vary
    across coins).
  - Compare the printed numbers for a coin you recognize (e.g. BTC, ETH)
    against what you see on tradingview.com's Crypto Coins Screener with
    those columns added, to confirm the values line up.

If a field is wrong, see README.md "Verifying field names" for how to find
the correct one via your browser's DevTools Network tab.
"""

from tradingview_screener.screeners import coin

FIELDS_TO_CHECK = [
    "name",
    "market_cap_calc",
    "24h_vol_cmc",
    "24h_close_change|5",
    "24h_vol_to_market_cap",
    "fully_diluted_value",
    "Perf.YTD",
    "24h_vol_change",
    "long_liquidations_24h",
]

if __name__ == "__main__":
    q = coin()
    q.select(*FIELDS_TO_CHECK)
    q.limit(15)
    try:
        _, df = q.get_scanner_data()
    except Exception as e:
        print("Query failed -- one of these field names is likely invalid:")
        print(FIELDS_TO_CHECK)
        print(f"\nError: {e}")
        raise

    import pandas as pd
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print(df)

    print("\n--- Sanity check ---")
    for col_name in ["24h_vol_change", "long_liquidations_24h"]:
        if col_name in df.columns:
            non_null = df[col_name].notna().sum()
            print(f"{col_name}: {non_null}/{len(df)} rows have a value")
            if non_null == 0:
                print(f"  -> Likely WRONG field name. See README.md to find the correct one.")
