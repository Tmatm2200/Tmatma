"""Startup smoke check for the bot.

Usage:
    python scripts/smoke_check.py          # quick checks (no network)
    python scripts/smoke_check.py --network  # includes a safe `get_me` network check

The script performs non-destructive checks:
- Validates required env/config values (BOT_TOKEN present and looks plausible)
- Ensures DB path directory is writable
- Optionally performs a network `get_me` call to Telegram to verify the token

Exit codes:
- 0  All checks passed
- 1  One or more checks failed

This is intended as a small smoke test you can run locally or in CI.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from typing import List, Tuple

try:
    from telegram import Bot
except Exception:  # pragma: no cover - in CI you should have the dependency
    Bot = None  # type: ignore

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from config import BOT_TOKEN, DB_PATH


def check_token_present() -> Tuple[bool, str]:
    token = os.getenv("BOT_TOKEN") or BOT_TOKEN
    if not token:
        return False, "BOT_TOKEN is missing"

    # Basic plausibility check: token usually contains a ':' and is at least 20 chars
    if ":" not in token or len(token) < 20:
        return False, "BOT_TOKEN looks invalid"

    return True, "BOT_TOKEN present and looks plausible"


def check_db_writable() -> Tuple[bool, str]:
    db_path = DB_PATH
    try:
        dir_path = os.path.dirname(str(db_path)) or "."
        with tempfile.NamedTemporaryFile(dir=dir_path, delete=True) as f:
            pass
        return True, f"DB path directory '{dir_path}' is writable"
    except Exception as e:
        return False, f"DB path directory not writable: {e}"


async def network_get_me(timeout: float = 5.0) -> Tuple[bool, str]:
    token = os.getenv("BOT_TOKEN") or BOT_TOKEN
    if Bot is None:
        return False, "python-telegram-bot not installed; cannot perform network check"

    try:
        bot = Bot(token=token)
        me = await asyncio.wait_for(bot.get_me(), timeout=timeout)
        return True, f"get_me succeeded (bot id={getattr(me, 'id', 'unknown')})"
    except Exception as e:
        return False, f"Network check failed: {e}"


def run_checks(network: bool = False) -> Tuple[bool, List[str]]:
    ok = True
    messages: List[str] = []

    t_ok, t_msg = check_token_present()
    messages.append(t_msg)
    ok = ok and t_ok

    d_ok, d_msg = check_db_writable()
    messages.append(d_msg)
    ok = ok and d_ok

    if network:
        # Run network check synchronously
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            n_ok, n_msg = loop.run_until_complete(network_get_me())
        except Exception as e:
            n_ok, n_msg = False, f"Network check failed: {e}"
        finally:
            try:
                loop.close()
            except Exception:
                pass

        messages.append(n_msg)
        ok = ok and n_ok

    return ok, messages


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Startup smoke check for Tmatma bot")
    parser.add_argument("--network", action="store_true", help="Perform a network check (`get_me`) using BOT_TOKEN")
    args = parser.parse_args(argv)

    ok, messages = run_checks(network=args.network)

    print("SMOKE CHECK RESULTS")
    print("-------------------")
    for m in messages:
        print("-", m)
    print("\n")
    if ok:
        print("All checks passed ✅")
        return 0
    else:
        print("One or more checks failed ⚠️")
        return 1


if __name__ == "__main__":
    sys.exit(main())
