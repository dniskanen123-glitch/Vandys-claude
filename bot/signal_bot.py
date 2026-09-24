"""Discord signal bot with one-tap approval.

Flow for every post from the signal author in the signal channel:
1. PLAN: a headless `claude -p` run reads the signal, checks the Robinhood
   account and quotes, applies SIGNAL_RULES.md, and returns the exact order it
   would place. This run cannot place, cancel or exercise anything.
2. APPROVE: the bot DMs you the planned order. React ✅ to place it or ❌ to
   skip. Approvals expire after APPROVAL_TIMEOUT_S seconds.
3. EXECUTE: only after your ✅, a second `claude -p` run places exactly that
   order, waits for a fill, and cancels it if it doesn't fill in time.
"""

import asyncio
import datetime as dt
import json
import logging
import os
import pathlib
import re
import subprocess
import sys

import discord
from dotenv import load_dotenv

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BOT_DIR = REPO_ROOT / "bot"
LOG_FILE = BOT_DIR / "trades.log"
HISTORY_FILE = BOT_DIR / "history.json"

load_dotenv(BOT_DIR / ".env")

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["SIGNAL_CHANNEL_ID"])
# Comma-separated Discord user IDs (or webhook IDs) whose posts count as signals.
AUTHOR_IDS = {int(x) for x in os.environ["SIGNAL_AUTHOR_IDS"].split(",") if x.strip()}
# Your own Discord user ID: plans are DMed to you and only your ✅ counts.
APPROVER_ID = int(os.environ["APPROVER_USER_ID"])
ACCOUNT_NUMBER = os.environ["ROBINHOOD_ACCOUNT_NUMBER"]
APPROVAL_TIMEOUT_S = int(os.environ.get("APPROVAL_TIMEOUT_S", "120"))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_TIMEOUT_S = int(os.environ.get("CLAUDE_TIMEOUT_S", "180"))

MCP_SERVER = "robinhood-trading"
TOOL = f"mcp__{MCP_SERVER}__"
WRITE_TOOLS = [
    TOOL + "place_option_order",
    TOOL + "place_equity_order",
    TOOL + "place_crypto_order",
    TOOL + "cancel_option_order",
    TOOL + "cancel_equity_order",
    TOOL + "cancel_crypto_order",
    TOOL + "exercise_option",
]
APPROVE, REJECT = "✅", "❌"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE)],
)
log = logging.getLogger("signal_bot")


def load_history() -> list[dict]:
    """Today's signals and outcomes (needed for rules like 'first trim')."""
    try:
        entries = json.loads(HISTORY_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    today = dt.date.today().isoformat()
    return [e for e in entries if e.get("date") == today]


def append_history(entry: dict) -> None:
    entries = load_history()
    entries.append({"date": dt.date.today().isoformat(), **entry})
    HISTORY_FILE.write_text(json.dumps(entries, indent=2))


def run_claude(prompt: str, allowed: list[str], disallowed: list[str]) -> str:
    """Blocking: one headless Claude Code turn; returns its final text."""
    cmd = [
        CLAUDE_BIN, "-p", prompt,
        "--mcp-config", str(REPO_ROOT / ".mcp.json"),
        "--strict-mcp-config",
        "--output-format", "text",
        "--allowedTools", *allowed,
    ]
    if disallowed:
        cmd += ["--disallowedTools", *disallowed]
    try:
        out = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        return "ERROR: Claude timed out"
    if out.returncode != 0:
        return f"ERROR: claude exited {out.returncode}: {out.stderr.strip()[-500:]}"
    return out.stdout.strip()


def parse_plan(text: str) -> dict | None:
    """Pull the last JSON object out of the planner's reply."""
    blocks = re.findall(r"\{.*\}", text, re.DOTALL)
    for block in reversed(blocks):
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue
    return None


def plan_prompt(signal: str, posted_at: str) -> str:
    rules = (REPO_ROOT / "SIGNAL_RULES.md").read_text()
    past = "\n".join(
        f"- [{e['posted_at']}] {e['signal']!r} -> {e['outcome']}" for e in load_history()
    ) or "(none yet today)"
    return f"""You plan copy-trades for a Robinhood account. You can NOT place orders;
a human approves each plan before it is placed.

Account number: {ACCOUNT_NUMBER} (use only this account).
Current time: {dt.datetime.now().astimezone().isoformat()}

Trading rules:
{rules}

Earlier signals today and outcomes:
{past}

New message posted at {posted_at}:
{signal!r}

Decide which rule this message triggers. If it triggers an order: check buying
power (get_portfolio) and open option positions, resolve the contract
(get_option_instruments), get a live quote, apply the budget and
strike-substitution rules, and call review_option_order to validate it.

Reply with ONLY a JSON object, no other text:
{{"action": "order" | "ignore",
  "reason": "<one short line>",
  "summary": "<e.g. BUY 1x SPY 2026-09-24 775C @ 0.35 limit (~$35)>",
  "option_id": "<instrument uuid>",
  "side": "buy" | "sell",
  "position_effect": "open" | "close",
  "quantity": "<int as string>",
  "price": "<limit price as string>",
  "alerts": "<review_option_order alerts, or empty>"}}
For "ignore", only action and reason are needed."""


def execute_prompt(plan: dict) -> str:
    return f"""Place exactly this single-leg option order, which the account owner
has just approved. Do not change any parameter.

account_number: {ACCOUNT_NUMBER}
option_id: {plan['option_id']}
side: {plan['side']}
position_effect: {plan['position_effect']}
quantity: {plan['quantity']}
type: limit
price: {plan['price']}
time_in_force: gfd

Then check the order with get_option_orders about every 10 seconds for up to 30
seconds. If it has not filled by then, cancel it (cancel_option_order).
Reply with ONE line: FILLED / PARTIAL / CANCELED / REJECTED, the order id, and
fill price if any."""


class SignalBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_reactions = True
        super().__init__(intents=intents)
        self.queue: asyncio.Queue[discord.Message] = asyncio.Queue()

    async def setup_hook(self) -> None:
        self.loop.create_task(self.worker())

    async def on_ready(self) -> None:
        log.info("Logged in as %s; watching channel %s", self.user, CHANNEL_ID)

    async def on_message(self, message: discord.Message) -> None:
        if message.channel.id != CHANNEL_ID:
            return
        if (message.webhook_id or message.author.id) not in AUTHOR_IDS:
            return
        if not message.content.strip():
            return
        log.info("Signal received: %r", message.content)
        await self.queue.put(message)

    async def worker(self) -> None:
        # One signal at a time, in posting order, so entries and exits never race.
        while True:
            message = await self.queue.get()
            try:
                await self.handle(message)
            except Exception:
                log.exception("Failed handling %r", message.content)
            finally:
                self.queue.task_done()

    async def handle(self, message: discord.Message) -> None:
        signal = message.clean_content
        posted_at = message.created_at.astimezone().isoformat()
        approver = await self.fetch_user(APPROVER_ID)

        # Planner gets read tools + review, never anything that changes the account.
        raw = await asyncio.to_thread(
            run_claude, plan_prompt(signal, posted_at), [f"mcp__{MCP_SERVER}"], WRITE_TOOLS
        )
        plan = parse_plan(raw)
        if plan is None:
            await approver.send(f"⚠️ Couldn't plan `{signal}`\n```{raw[-1500:]}```")
            append_history({"posted_at": posted_at, "signal": signal, "outcome": "plan failed"})
            return
        if plan.get("action") != "order":
            log.info("Ignored %r: %s", signal, plan.get("reason"))
            append_history({"posted_at": posted_at, "signal": signal,
                            "outcome": f"ignored: {plan.get('reason')}"})
            return

        prompt_msg = await approver.send(
            f"📣 **Signal:** `{signal}`\n"
            f"**Order:** {plan.get('summary')}\n"
            f"**Why:** {plan.get('reason')}\n"
            + (f"**Alerts:** {plan['alerts']}\n" if plan.get("alerts") else "")
            + f"React {APPROVE} to place or {REJECT} to skip "
            f"(expires in {APPROVAL_TIMEOUT_S}s)."
        )
        await prompt_msg.add_reaction(APPROVE)
        await prompt_msg.add_reaction(REJECT)

        def check(payload: discord.RawReactionActionEvent) -> bool:
            return (payload.message_id == prompt_msg.id
                    and payload.user_id == APPROVER_ID
                    and str(payload.emoji) in (APPROVE, REJECT))

        try:
            payload = await self.wait_for("raw_reaction_add", check=check,
                                          timeout=APPROVAL_TIMEOUT_S)
        except asyncio.TimeoutError:
            await approver.send("⌛ Expired, not placed.")
            append_history({"posted_at": posted_at, "signal": signal,
                            "outcome": f"planned {plan.get('summary')}; approval expired"})
            return

        if str(payload.emoji) == REJECT:
            await approver.send("Skipped.")
            append_history({"posted_at": posted_at, "signal": signal,
                            "outcome": f"planned {plan.get('summary')}; user skipped"})
            return

        await approver.send("Placing…")
        # Executor may only place/check/cancel the one approved order.
        result = await asyncio.to_thread(
            run_claude, execute_prompt(plan),
            [TOOL + "place_option_order", TOOL + "get_option_orders",
             TOOL + "cancel_option_order"],
            [],
        )
        log.info("Executed %r: %s", plan.get("summary"), result)
        await approver.send(f"🧾 {result}")
        append_history({"posted_at": posted_at, "signal": signal,
                        "outcome": f"approved {plan.get('summary')}; {result}"})


if __name__ == "__main__":
    SignalBot().run(DISCORD_TOKEN, log_handler=None)
