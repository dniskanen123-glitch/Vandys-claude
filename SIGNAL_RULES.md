# Signal copy-trading rules

Source: `#option-plays` (poster: vandy_trades)
Account: Robinhood "Agentic" account only

| Signal | Action |
|---|---|
| `SPY 777c at 1.24 1dte` (new entry) | Buy that contract with **75%** of buying power |
| `new avg 1.12` | Buy more of the same contract with the remaining **25%** |
| `in runners` | Sell **3/4** of the position, keep the rest |
| `all out` | Sell the entire position |
| `41%`, `50%`, ... (P/L updates) | Ignore |

## Defaults (change if needed)

- Contract counts round down; if 3/4 rounds to 0, sell 1.
- Orders are limit orders at the current ask (buys) / bid (sells).
- Unfilled orders are canceled after 30 seconds.
- Messages that don't match a rule above are ignored and logged.
