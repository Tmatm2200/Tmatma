"""Quick verification script for censoring logic.

Run locally:
    python scripts/verify_censor.py

This will add a censored word to the local DB and try several obfuscated variants
so you can see whether the handler deletes them.
"""
import asyncio
from types import SimpleNamespace
import sys
import os
from pathlib import Path

# Ensure repo root is on sys.path so local imports work when running the script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.database import Database
from handlers import messages


class DummyUser:
    def __init__(self, user_id):
        self.id = user_id


class DummyMessage:
    def __init__(self, text, message_id=1, from_user=None, chat_id=1234):
        self.text = text
        self.message_id = message_id
        self.from_user = from_user
        self.chat_id = chat_id
        self._deleted = False
        self.sticker = None

    async def delete(self):
        self._deleted = True

    async def reply_text(self, *args, **kwargs):
        return None


class DummyUpdate:
    def __init__(self, message):
        self.message = message
        self.effective_chat = SimpleNamespace(id=message.chat_id)
        self.effective_user = message.from_user


class DummyBot:
    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status='member')


async def run_check():
    Database.init_tables()
    chat_id = str(1234)
    Database.clear_all_censored_words(chat_id)
    Database.add_censored_word(chat_id, 'shit', False)

    variants = ['sh!t', 's.h.i.t', '5h1t', 's h i t', 'shiiit', 's#h$t']

    print('Testing variants for censored word "shit":')

    for v in variants:
        msg = DummyMessage(text=v, message_id=hash(v) % 100000, from_user=DummyUser(111), chat_id=1234)
        update = DummyUpdate(msg)
        ctx = SimpleNamespace(bot=DummyBot())
        # Reset delete flag
        msg._deleted = False
        await messages.handle_messages(update, ctx)
        print(f"{v:10} -> {'DELETED' if msg._deleted else 'ALLOWED'}")

    # Arabic tests
    print('\nTesting Arabic variants for censored word "لعنة":')
    Database.add_censored_word(chat_id, 'لعنة', False)
    arabic_variants = ['لعنة', 'ل@ع#ن%ة', 'ل ع ن ة', 'لّعنَة']
    for v in arabic_variants:
        msg = DummyMessage(text=v, message_id=hash(v) % 100000, from_user=DummyUser(111), chat_id=1234)
        update = DummyUpdate(msg)
        ctx = SimpleNamespace(bot=DummyBot())
        msg._deleted = False
        # Print normalization for debugging
        from utils.helpers import normalize_text
        print('---')
        print('raw:', v)
        print('compact:', normalize_text(v, remove_non_alnum=True))
        print('preserve:', normalize_text(v, remove_non_alnum=False))
        await messages.handle_messages(update, ctx)
        print(f"{v:10} -> {'DELETED' if msg._deleted else 'ALLOWED'}")

    # Arabic numerals
    print('\nTesting Arabic numerals (censor "٦" should block "٦٩")')
    Database.add_censored_word(chat_id, '٦', False)
    msg_num = DummyMessage(text='٦٩', message_id=42, from_user=DummyUser(111), chat_id=1234)
    update_num = DummyUpdate(msg_num)
    ctx_num = SimpleNamespace(bot=DummyBot())
    msg_num._deleted = False
    await messages.handle_messages(update_num, ctx_num)
    print(f"٦٩ -> {'DELETED' if msg_num._deleted else 'ALLOWED'}")

    # Cleanup
    Database.remove_censored_word(chat_id, 'shit')
    Database.remove_censored_word(chat_id, 'لعنة')
    Database.remove_censored_word(chat_id, '٦')


if __name__ == '__main__':
    asyncio.run(run_check())
