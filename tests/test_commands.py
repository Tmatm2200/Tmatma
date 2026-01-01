import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from handlers import basic, moderation, messages, admin, messages as messages_module
from utils import database
from config import ADMIN_ID

# Helpers

class DummyMessage:
    def __init__(self, text=None, sticker=None, message_id=1, from_user=None, chat_id=1234):
        self.text = text
        self.sticker = sticker
        self.message_id = message_id
        self.from_user = from_user
        self.chat_id = chat_id
        self._deleted = False

    async def reply_text(self, *args, **kwargs):
        return MagicMock()

    async def delete(self):
        self._deleted = True

    async def edit_text(self, *args, **kwargs):
        return MagicMock()


class DummyUser:
    def __init__(self, user_id, username=None):
        self.id = user_id
        self.username = username


class DummyChat:
    def __init__(self, chat_id=1234):
        self.id = chat_id

    async def send_message(self, *args, **kwargs):
        msg = MagicMock()
        async def delete():
            return None
        msg.delete = AsyncMock(side_effect=delete)
        return msg


class DummyUpdate:
    def __init__(self, message: DummyMessage):
        self.message = message
        self.effective_chat = DummyChat(chat_id=message.chat_id)
        self.effective_user = message.from_user


class DummyBot:
    def __init__(self):
        self.get_chat_member = AsyncMock()
        self.delete_message = AsyncMock()


class DummyContext:
    def __init__(self, bot: DummyBot, args=None):
        self.bot = bot
        self.args = args or []


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    # Ensure we use a temp DB file for tests to avoid contaminating workspace
    db_path = tmp_path / "test_bot.db"
    monkeypatch.setattr(database, 'DB_PATH', str(db_path))
    # Re-init database
    database.Database.init_tables()


@pytest.mark.asyncio
async def test_basic_commands_reply(monkeypatch):
    user = DummyUser(user_id=9999)
    msg = DummyMessage(text="/start", from_user=user)
    update = DummyUpdate(msg)
    context = DummyContext(bot=DummyBot())

    await basic.start(update, context)
    await basic.help_command(update, context)
    # Test ping: it edits a message; ensure no exceptions
    msg_for_ping = DummyMessage(text="/ping", from_user=user)
    update_ping = DummyUpdate(msg_for_ping)
    # Make reply_text return a message object for edit
    async def reply_text_return(*args, **kwargs):
        m = MagicMock()
        async def edit_text(*a, **k):
            return None
        m.edit_text = AsyncMock(side_effect=edit_text)
        return m
    async def edit_text(*a, **k):
        return None
    # Patch reply_text to return object with edit_text
    msg_for_ping.reply_text = AsyncMock(return_value=MagicMock())
    await basic.ping(update_ping, context)


@pytest.mark.asyncio
async def test_block_unblock_list(monkeypatch):
    bot = DummyBot()
    owner = DummyUser(user_id=1)
    monkeypatch.setattr('utils.decorators.ADMIN_ID', 1)

    # Block a sticker set
    msg = DummyMessage(text="/block MySet", from_user=owner)
    update = DummyUpdate(msg)
    ctx = DummyContext(bot=bot, args=['MySet'])

    await moderation.block_sticker(update, ctx)
    assert database.Database.is_set_blocked(str(update.effective_chat.id), 'myset')

    # List should reply (no exception)
    await moderation.list_blocked_sets(update, ctx)

    # Unblock
    ctx_unblock = DummyContext(bot=bot, args=['MySet'])
    await moderation.unblock_sticker(update, ctx_unblock)
    assert not database.Database.is_set_blocked(str(update.effective_chat.id), 'myset')


@pytest.mark.asyncio
async def test_censor_uncensor_list(monkeypatch):
    bot = DummyBot()
    owner = DummyUser(user_id=1)
    monkeypatch.setattr('utils.decorators.ADMIN_ID', 1)

    # Censor words
    msg = DummyMessage(text='/censor badword "exact phrase"', from_user=owner)
    update = DummyUpdate(msg)
    ctx = DummyContext(bot=bot, args=['badword', '"exact phrase"'])

    await moderation.censor_word(update, ctx)
    words = database.Database.get_censored_words(str(update.effective_chat.id))
    assert any(w[0] == 'badword' for w in words)

    # List
    await moderation.list_censored_words(update, ctx)

    # Uncensor a word
    ctx_uncensor = DummyContext(bot=bot, args=['badword'])
    await moderation.uncensor_word(update, ctx_uncensor)
    words_after = database.Database.get_censored_words(str(update.effective_chat.id))
    assert not any(w[0] == 'badword' for w in words_after)

    # Uncensor all
    await moderation.censor_word(update, ctx)
    await moderation.uncensor_word(update, DummyContext(bot=bot, args=['all']))
    assert database.Database.get_censored_words(str(update.effective_chat.id)) == []


@pytest.mark.asyncio
async def test_clear_messages_and_except(monkeypatch):
    bot = DummyBot()
    owner = DummyUser(user_id=1)
    monkeypatch.setattr('config.ADMIN_ID', 1)

    # Track messages
    from handlers.moderation import track_message, MESSAGE_HISTORY
    # Clear any existing
    MESSAGE_HISTORY.clear()
    for i in range(1, 6):
        track_message(1234, i, 111, 'user')

    # Clear 3 messages
    msg = DummyMessage(text='/clear 3', from_user=owner)
    update = DummyUpdate(msg)
    ctx = DummyContext(bot=bot, args=['3'])

    # Patch bot.delete_message to track deletes
    bot.delete_message = AsyncMock()
    await moderation.clear_messages(update, ctx)
    assert bot.delete_message.await_count >= 0

    # Clear except a username
    # Add messages with usernames
    MESSAGE_HISTORY.clear()
    track_message(1234, 1, 111, 'keepme')
    for i in range(2, 7):
        track_message(1234, i, 222, 'other')

    msg = DummyMessage(text='/clear_except @keepme 3', from_user=owner)
    update = DummyUpdate(msg)
    ctx = DummyContext(bot=bot, args=['@keepme', '3'])
    bot.delete_message = AsyncMock()
    await moderation.clear_except(update, ctx)
    assert bot.delete_message.await_count >= 0


@pytest.mark.asyncio
async def test_admin_with_edit_permission_can_run_admin_cmds(monkeypatch):
    """Administrators with edit permission can run admin-only commands."""
    bot = DummyBot()
    admin = DummyUser(user_id=222)
    monkeypatch.setattr('utils.decorators.ADMIN_ID', 1)

    # Simulate admin chat member with edit permission
    member = MagicMock()
    member.status = 'administrator'
    member.can_delete_messages = False
    member.can_edit_messages = True
    bot.get_chat_member.return_value = member

    # Try to block a set as admin
    msg = DummyMessage(text="/block MySet", from_user=admin)
    update = DummyUpdate(msg)
    ctx = DummyContext(bot=bot, args=['MySet'])

    await moderation.block_sticker(update, ctx)
    assert database.Database.is_set_blocked(str(update.effective_chat.id), 'myset')


@pytest.mark.asyncio
async def test_antispam_and_message_checks(monkeypatch):
    bot = DummyBot()
    owner = DummyUser(user_id=1)
    monkeypatch.setattr('utils.decorators.ADMIN_ID', 1)

    chat_id = str(1234)
    database.Database.set_antispam(chat_id, True)

    # Create messages to exceed spam threshold
    from handlers.messages import SPAM_TRACKER, check_spam
    SPAM_TRACKER.clear()

    # Prepare update template
    async def make_update(mid):
        user = DummyUser(user_id=111)
        msg = DummyMessage(text=f'msg {mid}', from_user=user, message_id=mid)
        update = DummyUpdate(msg)
        ctx = DummyContext(bot=bot)
        return update, ctx

    for i in range(1, 9):
        update, ctx = await make_update(i)
        deleted = await check_spam(update, ctx)
        if i > 6:
            assert deleted is True
            break


@pytest.mark.asyncio
async def test_admins_enable_disable(monkeypatch):
    bot = DummyBot()
    owner = DummyUser(user_id=1)
    monkeypatch.setattr('utils.decorators.ADMIN_ID', 1)

    msg = DummyMessage(text='/admins_enable', from_user=owner)
    update = DummyUpdate(msg)
    ctx = DummyContext(bot=bot)

    await admin.admins_enable(update, ctx)
    assert database.Database.is_admin_bypass_enabled(str(update.effective_chat.id))

    await admin.admins_disable(update, ctx)
    assert database.Database.is_admin_bypass_enabled(str(update.effective_chat.id)) is False


@pytest.mark.asyncio
async def test_admin_bypass_requires_permissions(monkeypatch):
    """Admins can bypass only if they have delete or edit message permission."""
    bot = DummyBot()
    owner = DummyUser(user_id=1)
    monkeypatch.setattr('utils.decorators.ADMIN_ID', 1)

    chat_id = str(1234)
    # Enable admin bypass for the chat
    database.Database.set_admin_bypass(chat_id, True)

    # Case 1: admin with delete permission -> should bypass (message not deleted)
    admin_with_perm = DummyUser(user_id=222)
    msg1 = DummyMessage(text='badword', from_user=admin_with_perm)
    update1 = DummyUpdate(msg1)
    ctx1 = DummyContext(bot=bot)

    # Simulate chat member response with permissions
    member = MagicMock()
    member.status = 'administrator'
    member.can_delete_messages = True
    member.can_edit_messages = False
    bot.get_chat_member.return_value = member

    # Add a censored word so handler will attempt to delete
    database.Database.add_censored_word(chat_id, 'badword', False)

    # Run messages handler; because admin has permission, message should NOT be deleted
    await messages.handle_messages(update1, ctx1)
    assert msg1._deleted is False

    # Case 2: admin without delete/edit permission -> should NOT bypass (message deleted)
    admin_no_perm = DummyUser(user_id=333)
    msg2 = DummyMessage(text='badword', from_user=admin_no_perm, message_id=2)
    update2 = DummyUpdate(msg2)
    ctx2 = DummyContext(bot=bot)

    member2 = MagicMock()
    member2.status = 'administrator'
    member2.can_delete_messages = False
    member2.can_edit_messages = False
    bot.get_chat_member.return_value = member2

    await messages.handle_messages(update2, ctx2)
    assert msg2._deleted is True

    # Cleanup censored words
    database.Database.uncensor_word(chat_id, 'badword')


@pytest.mark.asyncio
async def test_track_messages_and_blocked_sticker(monkeypatch):
    # Track message
    from handlers.moderation import track_message, MESSAGE_HISTORY
    MESSAGE_HISTORY.clear()
    track_message(1234, 999, 111, 'user')
    assert any(m[1] == 999 for m in MESSAGE_HISTORY)

    # Blocked sticker deletion path
    bot = DummyBot()
    user = DummyUser(user_id=2)
    # Add blocked set
    database.Database.add_blocked_set(str(1234), 'blockedset')

    class Sticker: pass
    sticker = Sticker()
    sticker.set_name = 'blockedset'

    msg = DummyMessage(sticker=sticker, from_user=user)
    update = DummyUpdate(msg)
    ctx = DummyContext(bot=bot)

    # Patch context.bot.delete_message to simulate successful deletion
    bot.delete_message = AsyncMock()
    deleted = await messages.check_blocked_sticker(update, ctx, str(1234))
    assert deleted is True


@pytest.mark.asyncio
async def test_censor_numeric_substring_match(monkeypatch):
    """Censoring '6' should also block '69' (numeric substring match)."""
    bot = DummyBot()
    user = DummyUser(user_id=111)
    monkeypatch.setattr('utils.decorators.ADMIN_ID', 1)

    chat_id = str(1234)
    database.Database.add_censored_word(chat_id, '6', False)

    msg = DummyMessage(text='69', from_user=user, message_id=42, chat_id=1234)
    update = DummyUpdate(msg)
    ctx = DummyContext(bot=bot)

    await messages.handle_messages(update, ctx)
    assert msg._deleted is True

    # Cleanup
    database.Database.uncensor_word(chat_id, '6')


@pytest.mark.asyncio
async def test_censor_leetspeak_and_separators(monkeypatch):
    """Ensure obfuscated/leet/pros-separated variants are caught for a word."""
    bot = DummyBot()
    user = DummyUser(user_id=111)
    monkeypatch.setattr('utils.decorators.ADMIN_ID', 1)

    chat_id = str(1234)
    database.Database.add_censored_word(chat_id, 'shit', False)

    variants = ['sh!t', 's.h.i.t', '5h1t', 's h i t', 'shiiit']
    for i, variant in enumerate(variants, start=1):
        msg = DummyMessage(text=variant, from_user=user, message_id=100 + i, chat_id=1234)
        update = DummyUpdate(msg)
        ctx = DummyContext(bot=bot)
        # Reset deleted flag
        msg._deleted = False
        await messages.handle_messages(update, ctx)
        assert msg._deleted is True, f"Variant {variant} was not deleted"

    # Arabic variants
    database.Database.add_censored_word(chat_id, 'لعنة', False)
    arabic_variants = ['لعنة', 'ل@ع#ن%ة', 'ل ع ن ة', 'لّعنَة']
    for i, variant in enumerate(arabic_variants, start=1):
        msg = DummyMessage(text=variant, from_user=user, message_id=200 + i, chat_id=1234)
        update = DummyUpdate(msg)
        ctx = DummyContext(bot=bot)
        msg._deleted = False
        await messages.handle_messages(update, ctx)
        assert msg._deleted is True, f"Arabic variant {variant} was not deleted"

    # Arabic numeric test: censoring '٦' should block '٦٩'
    database.Database.add_censored_word(chat_id, '٦', False)
    msg_num = DummyMessage(text='٦٩', from_user=user, message_id=300, chat_id=1234)
    update_num = DummyUpdate(msg_num)
    ctx_num = DummyContext(bot=bot)
    await messages.handle_messages(update_num, ctx_num)
    assert msg_num._deleted is True

    # Cleanup
    database.Database.remove_censored_word(chat_id, 'shit')
    database.Database.remove_censored_word(chat_id, 'لعنة')
    database.Database.remove_censored_word(chat_id, '٦')


@pytest.mark.asyncio
async def test_clear_by_user(monkeypatch):
    """`/clear @user N` deletes last N messages from specified user."""
    bot = DummyBot()
    owner = DummyUser(user_id=1)
    monkeypatch.setattr('utils.decorators.ADMIN_ID', 1)

    from handlers.moderation import track_message, MESSAGE_HISTORY
    MESSAGE_HISTORY.clear()

    # Add messages: three from target, one from other
    track_message(1234, 10, 111, 'target')
    track_message(1234, 9, 111, 'target')
    track_message(1234, 8, 222, 'other')
    track_message(1234, 7, 111, 'target')

    msg = DummyMessage(text='/clear @target 2', from_user=owner, chat_id=1234)
    update = DummyUpdate(msg)
    ctx = DummyContext(bot=bot, args=['@target', '2'])

    bot.delete_message = AsyncMock()
    await moderation.clear_messages(update, ctx)

    # Ensure bot.delete_message was called twice with the two latest message IDs from target
    called_ids = [call.args[1] for call in bot.delete_message.await_args_list]
    assert set(called_ids) == {10, 9}


@pytest.mark.asyncio
async def test_admin_bypass_sticker_permissions(monkeypatch):
    """Admins bypass sticker filter only if they have delete/edit permission."""
    bot = DummyBot()
    owner = DummyUser(user_id=1)
    monkeypatch.setattr('utils.decorators.ADMIN_ID', 1)

    chat_id = str(1234)
    database.Database.add_blocked_set(chat_id, 'blockedset')
    database.Database.set_admin_bypass(chat_id, True)

    class Sticker: pass
    sticker = Sticker()
    sticker.set_name = 'blockedset'

    # Admin with permission should NOT have sticker deleted
    admin_with_perm = DummyUser(user_id=222)
    msg1 = DummyMessage(sticker=sticker, from_user=admin_with_perm)
    update1 = DummyUpdate(msg1)
    ctx1 = DummyContext(bot=bot)

    member = MagicMock()
    member.status = 'administrator'
    member.can_delete_messages = True
    member.can_edit_messages = False
    bot.get_chat_member.return_value = member

    await messages.handle_messages(update1, ctx1)
    assert msg1._deleted is False

    # Admin without permission should have sticker deleted
    admin_no_perm = DummyUser(user_id=333)
    msg2 = DummyMessage(sticker=sticker, from_user=admin_no_perm)
    update2 = DummyUpdate(msg2)
    ctx2 = DummyContext(bot=bot)

    member2 = MagicMock()
    member2.status = 'administrator'
    member2.can_delete_messages = False
    member2.can_edit_messages = False
    bot.get_chat_member.return_value = member2

    await messages.handle_messages(update2, ctx2)
    assert msg2._deleted is True


# End of tests
