# Signal bot (approve each trade)

Watches a Discord channel for signals, plans the order with Claude using
`../SIGNAL_RULES.md`, DMs you the plan, and places it only when you react ✅.

## One-time setup (on the computer/server that will run it)

1. **Discord bot**
   - https://discord.com/developers/applications → New Application → Bot.
   - Copy the bot token. Turn on **Message Content Intent**.
   - OAuth2 → URL Generator → scope `bot`, permissions *View Channels* and
     *Read Message History*. Send that invite link to the server owner; they
     add the bot and give it access to `#option-plays` only.
   - Share a server with the bot (theirs counts) so it can DM you, and allow
     DMs from server members.
2. **Claude Code + Robinhood**
   - Install Claude Code and log in: `claude`.
   - In this repo run `claude`, then `/mcp` → `robinhood-trading` →
     Authenticate, and finish the Robinhood login in the browser.
3. **Bot**
   ```bash
   cd bot
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # fill it in
   python signal_bot.py
   ```

Keep it running during market hours (e.g. `tmux`, or a systemd service).

## Files

- `trades.log`: everything the bot did.
- `history.json`: today's signals and outcomes, fed back to the planner so
  rules like "first trim only" work. Both are git-ignored.
