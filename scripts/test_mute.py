import asyncio
from types import SimpleNamespace
import time
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils.database import Database
from handlers.messages import check_spam

# Ensure DB initialized
Database.init_tables()

async def run_test():
    chat_id = '12345'
    user_id = 111

    # Enable antispam for chat
    Database.set_antispam(chat_id, True)
    Database.set_spam_limit(chat_id, 3)
    Database.set_spam_mute(chat_id, 1)

    # Create fake bot with methods
    calls = {'deleted': [], 'restricted': [], 'messages': []}

    class FakeBot:
        id = 999
        async def delete_message(self, c, mid):
            calls['deleted'].append((c, mid))
        async def restrict_chat_member(self, c, uid, permissions=None, until_date=None):
            calls['restricted'].append((c, uid, until_date))
        async def send_message(self, c, text):
            calls['messages'].append((c, text))

    bot = FakeBot()

    # Build update/context objects
    async def make_update(mid):
        return SimpleNamespace(
            effective_chat=SimpleNamespace(id=chat_id),
            effective_user=SimpleNamespace(id=user_id),
            message=SimpleNamespace(message_id=mid, text='hello')
        )

    class Ctx:
        def __init__(self, bot):
            self.bot = bot

    ctx = Ctx(bot)

    # Send messages exceeding limit
    for i in range(5):
        upd = await make_update(i+1)
        deleted = await check_spam(upd, ctx)
        print(f"Message {i+1}, check_spam returned: {deleted}")
        await asyncio.sleep(0.1)

    print('Calls:', calls)

if __name__ == '__main__':
    asyncio.run(run_test())
