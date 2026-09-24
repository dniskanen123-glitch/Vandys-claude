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
| New entry while already in a trade | Buy with **all remaining** buying power |
| No `all out` on a 0DTE | Hold; Robinhood force-closes at 3:45pm ET |
| `41%`, `50%`, ... (P/L updates) | Ignore |

## Budget too small for the signaled contract

If one contract of the signaled strike costs more than the budget for that buy
(ask x 100 > budget), buy the **closest strike further out of the money** (same
ticker, same expiration, same call/put) whose ask x 100 fits the budget. Tell
the user which strike was substituted. `new avg` buys more of the contract
actually held (skip if even 1 doesn't fit). If no strike fits, skip the signal.

## Defaults (change if needed)

- Contract counts round down; if 25% rounds to 0 (e.g. 1-3 contracts), skip the trim and hold until `all out`.
- Orders are limit orders at the current ask (buys) / bid (sells).
- Unfilled orders are canceled after 30 seconds.
- Messages that don't match a rule above are ignored and logged.
