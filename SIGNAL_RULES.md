# Signal copy-trading rules

Source: `#option-plays` (poster: vandy_trades)
Account: Robinhood "Agentic" account only

| Signal | Action |
|---|---|
| `SPY 777c at 1.24 1dte` (new entry) | Buy that contract with **75%** of buying power |
| `new avg 1.12` | Buy more of the same contract with the remaining **25%** |
| First trim (`in runners`, `trim`, `taking some off`, etc.) | Sell **25%** of the position |
| Later trims | Ignore (hold the rest) |
| `all out` | Sell the remaining **75%** (entire position) |
| `41%`, `50%`, ... (P/L updates) | Ignore |

## Defaults (change if needed)

- Contract counts round down; if 25% rounds to 0 (e.g. 1-3 contracts), skip the trim and hold until `all out`.
- Orders are limit orders at the current ask (buys) / bid (sells).
- Unfilled orders are canceled after 30 seconds.
- Messages that don't match a rule above are ignored and logged.
