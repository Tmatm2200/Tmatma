"""
Moderation command handlers (block, clear, censor).
"""
import asyncio
import re
from collections import deque
from telegram import Update
from telegram.ext import ContextTypes
from config import MAX_CLEAR_COUNT, MAX_MESSAGE_HISTORY, SPAM_TIME_WINDOW
from utils.database import Database
from utils.decorators import admin_or_owner, handle_errors

# Global message history for clearing
MESSAGE_HISTORY = deque(maxlen=MAX_MESSAGE_HISTORY)


@admin_or_owner
@handle_errors
async def block_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /block command - block a sticker set."""
    if not context.args:
        await update.message.reply_text("❌ Usage: `/block <sticker_set_link_or_name>`", parse_mode='Markdown')
        return
    
    chat_id = str(update.effective_chat.id)
    raw = " ".join(context.args).strip()
    
    # Extract set name from link if provided
    if "addstickers/" in raw:
        set_name = raw.split("addstickers/")[-1].split("?")[0].strip().lower()
    else:
        set_name = raw.lower()
    
    if Database.add_blocked_set(chat_id, set_name):
        await update.message.reply_text(f"✅ Blocked sticker set: `{set_name}`", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Failed to block sticker set.")


@admin_or_owner
@handle_errors
async def unblock_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unblock command - unblock sticker set(s)."""
    if not context.args:
        await update.message.reply_text("❌ Usage: `/unblock <name|all>`", parse_mode='Markdown')
        return
    
    chat_id = str(update.effective_chat.id)
    
    # Handle "unblock all"
    if context.args[0].lower() == "all":
        if Database.clear_all_blocked_sets(chat_id):
            await update.message.reply_text("✅ All blocked sticker sets removed.")
        else:
            await update.message.reply_text("⚠️ No sticker sets to unblock.")
        return
    
    # Handle single set
    raw = " ".join(context.args)
    if "addstickers/" in raw:
        set_name = raw.split("addstickers/")[-1].split("?")[0].strip().lower()
    else:
        set_name = raw.lower()
    
    if Database.remove_blocked_set(chat_id, set_name):
        await update.message.reply_text(f"✅ Unblocked sticker set: `{set_name}`", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"⚠️ Sticker set `{set_name}` is not blocked.", parse_mode='Markdown')


@admin_or_owner
@handle_errors
async def list_blocked_sets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list command - list all blocked sticker sets."""
    chat_id = str(update.effective_chat.id)
    sets = Database.get_blocked_sets(chat_id)
    
    if not sets:
        await update.message.reply_text("📋 No sticker sets are blocked in this chat.")
        return
    
    sets_list = "\n".join([f"• `{s}`" for s in sets])
    await update.message.reply_text(
        f"🚫 *Blocked Sticker Sets:*\n\n{sets_list}",
        parse_mode='Markdown'
    )


@admin_or_owner
@handle_errors
async def censor_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /censor command - add censored words."""
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/censor word1 word2` or `/censor \"exact phrase\"`",
            parse_mode='Markdown'
        )
        return
    
    chat_id = str(update.effective_chat.id)
    raw = " ".join(context.args)
    
    # Extract quoted phrases (strict matching)
    strict_words = re.findall(r'"([^"]+)"', raw)
    for word in strict_words:
        Database.add_censored_word(chat_id, word.lower(), is_strict=True)
    
    # Extract regular words (smart matching)
    remaining = re.sub(r'"[^"]+"', '', raw)
    regular_words = [w.strip().lower() for w in remaining.replace(',', ' ').split() if w.strip()]
    for word in regular_words:
        Database.add_censored_word(chat_id, word, is_strict=False)
    
    await update.message.reply_text("✅ Word filter updated.")


@admin_or_owner
@handle_errors
async def list_censored_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /censor_list command - list all censored words."""
    chat_id = str(update.effective_chat.id)
    words = Database.get_censored_words(chat_id)
    
    if not words:
        await update.message.reply_text("📋 No words are censored in this chat.")
        return
    
    word_list = "\n".join([
        f"• `{word}` {'(Strict)' if strict else '(Smart)'}"
        for word, strict in words
    ])
    await update.message.reply_text(
        f"🛡️ *Censored Words:*\n\n{word_list}",
        parse_mode='Markdown'
    )


@admin_or_owner
@handle_errors
async def uncensor_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /uncensor command - remove censored words or clear all."""
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/uncensor word1 word2` or `/uncensor all`",
            parse_mode='Markdown'
        )
        return

    chat_id = str(update.effective_chat.id)

    # Handle "uncensor all"
    if len(context.args) == 1 and context.args[0].lower() == "all":
        if Database.clear_all_censored_words(chat_id):
            await update.message.reply_text("✅ All censored words removed.")
        else:
            await update.message.reply_text("⚠️ No censored words to remove.")
        return

    removed_any = False
    for raw in context.args:
        word = raw.strip().lower()
        if Database.remove_censored_word(chat_id, word):
            removed_any = True

    if removed_any:
        await update.message.reply_text("✅ Censored words updated.")
    else:
        await update.message.reply_text("⚠️ No specified words were found in the censored list.")


@admin_or_owner
@handle_errors
async def clear_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear command - delete last N messages.

    Usage:
    - `/clear 10` - delete last 10 messages
    - `/clear @username 5` - delete last 5 messages from @username
    - `/clear @username` - delete last 10 messages from @username (default)
    """
    count = 10  # Default
    target_user = None

    # Parse args: support `/clear @username [count]` or `/clear <count>`
    if context.args:
        # Clear messages for a specific user by username
        if context.args[0].startswith('@'):
            target_user = context.args[0].replace('@', '').lower()
            count = next((int(arg) for arg in context.args[1:] if arg.isdigit()), 10)
            count = min(count, MAX_CLEAR_COUNT)
        # Clear last N messages
        elif context.args[0].isdigit():
            count = min(int(context.args[0]), MAX_CLEAR_COUNT)

    chat_id = update.effective_chat.id

    # Get messages from this chat (optionally filter by user)
    if target_user:
        chat_messages = [m for m in MESSAGE_HISTORY if m[0] == chat_id and m[3] == target_user]
    else:
        chat_messages = [m for m in MESSAGE_HISTORY if m[0] == chat_id]

    chat_messages.sort(key=lambda x: x[1], reverse=True)

    # Delete command message
    try:
        await update.message.delete()
    except:
        pass

    # Delete messages
    deleted = 0
    for msg_data in chat_messages[:count]:
        try:
            await context.bot.delete_message(chat_id, msg_data[1])
            deleted += 1
        except:
            continue
        await asyncio.sleep(0.05)  # Rate limiting

    # Send status message and auto-delete
    if target_user:
        status_msg = await update.effective_chat.send_message(
            f"🗑️ Deleted {deleted} messages from @{target_user}."
        )
    else:
        status_msg = await update.effective_chat.send_message(f"🗑️ Deleted {deleted} messages.")

    await asyncio.sleep(2)
    try:
        await status_msg.delete()
    except:
        pass


@admin_or_owner
@handle_errors
async def clear_except(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear_except command - delete messages except from specified users."""
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/clear_except @user1 @user2 <count>`",
            parse_mode='Markdown'
        )
        return
    
    # Extract usernames and count
    target_users = [arg.replace('@', '').lower() for arg in context.args if arg.startswith('@')]
    count = next((int(arg) for arg in context.args if arg.isdigit()), 10)
    count = min(count, MAX_CLEAR_COUNT)
    
    chat_id = update.effective_chat.id
    
    # Get messages NOT from target users
    chat_messages = [
        m for m in MESSAGE_HISTORY 
        if m[0] == chat_id and m[3] not in target_users
    ]
    chat_messages.sort(key=lambda x: x[1], reverse=True)
    
    # Delete command message
    try:
        await update.message.delete()
    except:
        pass
    
    # Delete messages
    deleted = 0
    for msg_data in chat_messages[:count]:
        try:
            await context.bot.delete_message(chat_id, msg_data[1])
            deleted += 1
        except:
            continue
        await asyncio.sleep(0.05)
    
    # Send status message
    status_msg = await update.effective_chat.send_message(
        f"🗑️ Deleted {deleted} messages (except from {', '.join(target_users)})."
    )
    await asyncio.sleep(2)
    try:
        await status_msg.delete()
    except:
        pass


@admin_or_owner
@handle_errors
async def antispam_enable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /antispam_enable command."""
    chat_id = str(update.effective_chat.id)
    Database.set_antispam(chat_id, True)
    limit, minutes = Database.get_spam_settings(chat_id)
    await update.message.reply_text(f"🚨 Anti-Spam enabled ({limit} msgs / {SPAM_TIME_WINDOW}s).")


@admin_or_owner
@handle_errors
async def antispam_disable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /antispam_disable command."""
    chat_id = str(update.effective_chat.id)
    Database.set_antispam(chat_id, False)
    await update.message.reply_text("😴 Anti-Spam disabled.")


@admin_or_owner
@handle_errors
async def antispam_set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /antispam_set_limit <count> - set messages allowed in time window."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Usage: `/antispam_set_limit <count>`", parse_mode='Markdown')
        return
    limit = max(1, min(int(context.args[0]), 100))
    chat_id = str(update.effective_chat.id)
    Database.set_spam_limit(chat_id, limit)
    await update.message.reply_text(f"✅ Anti-Spam limit set to {limit} messages per {SPAM_TIME_WINDOW} seconds.")


@admin_or_owner
@handle_errors
async def antispam_set_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /antispam_set_mute <minutes> - set mute duration after spam."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Usage: `/antispam_set_mute <minutes>`", parse_mode='Markdown')
        return
    minutes = max(1, min(int(context.args[0]), 1440))
    chat_id = str(update.effective_chat.id)
    Database.set_spam_mute(chat_id, minutes)
    await update.message.reply_text(f"✅ Mute duration set to {minutes} minutes for spamming.")


def track_message(chat_id: int, message_id: int, user_id: int, username: str):
    """Add message to history for clear commands."""
    MESSAGE_HISTORY.append((chat_id, message_id, user_id, username))
    
    