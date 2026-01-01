import asyncio
from types import SimpleNamespace
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils import database
from handlers.messages import check_censored_words

class DummyMessage:
    def __init__(self, text=None, from_user=None, message_id=1, chat_id=1234):
        self.text = text
        self.from_user = from_user
        self.message_id = message_id
        self.chat_id = chat_id

    async def delete(self):
        self._deleted = True

    async def reply_text(self, *args, **kwargs):
        return None

class DummyUser:
    def __init__(self, user_id):
        self.id = user_id

class DummyUpdate:
    def __init__(self, message):
        self.message = message
        self.effective_chat = SimpleNamespace(id=message.chat_id)
        self.effective_user = message.from_user

class DummyBot:
    pass

class DummyContext:
    def __init__(self, bot):
        self.bot = bot

async def run():
    database.Database.init_tables()
    chat_id = str(1234)
    database.Database.clear_all_censored_words(chat_id)
    database.Database.clear_all_whitelisted_words(chat_id)
    database.Database.add_censored_word(chat_id, 'shit', is_strict=False)
    database.Database.add_whitelisted_word(chat_id, 'shittener')

    owner = DummyUser(1)
    # message with whitelist
    msg = DummyMessage(text='this is shittener', from_user=owner)
    upd = DummyUpdate(msg)
    ctx = DummyContext(DummyBot())
    res = await check_censored_words(upd, ctx, chat_id)
    print('shittener deleted?', res)

    # message with shit
    msg2 = DummyMessage(text='this is shit', from_user=owner)
    upd2 = DummyUpdate(msg2)
    res2 = await check_censored_words(upd2, ctx, chat_id)
    print('shit deleted?', res2)

if __name__ == '__main__':
    asyncio.run(run())