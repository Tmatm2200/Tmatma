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
    skipped = []
    for word in regular_words:
        # Prevent adding single-character censored tokens, which are prone to false positives
        if len(word) < 2:
            skipped.append(word)
            continue
        Database.add_censored_word(chat_id, word, is_strict=False)

    if skipped:
        await update.message.reply_text(
            f"✅ Word filter updated. Skipped too-short tokens: {', '.join(skipped)}"
        )
    else:
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
async def debug_censor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /debug_censor <text> or reply with /debug_censor - show which censor rules would match.

    This command does NOT delete messages; it returns diagnostic information about
    normalization and which censored tokens (if any) would trigger deletion and by
    which matching strategy.
    """
    from utils.helpers import normalize_text

    # Determine text to analyze: args take precedence, otherwise use replied-to message
    if context.args:
        raw = " ".join(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        raw = update.message.reply_to_message.text
    else:
        await update.message.reply_text("❌ Usage: `/debug_censor <text>` or reply to a message with `/debug_censor`", parse_mode='Markdown')
        return

    chat_id = str(update.effective_chat.id)
    text = raw or ""

    normalized_compact = normalize_text(text, remove_non_alnum=True, collapse_repeats=True)
    normalized_preserve = normalize_text(text, remove_non_alnum=False, collapse_repeats=False)
    normalized_compact_no_collapse = normalize_text(text, remove_non_alnum=True, collapse_repeats=False)

    censored_words = Database.get_censored_words(chat_id)

    parts = [f"*Input:* `{text}`", f"*Normalized (compact):* `{normalized_compact}`", f"*Normalized (preserve):* `{normalized_preserve}`", ""]

    if not censored_words:
        parts.append("No censored words configured for this chat.")
        await update.message.reply_text("\n".join(parts), parse_mode='Markdown')
        return

    matched_any = False
    for word, is_strict in censored_words:
        word_norm = normalize_text(word, remove_non_alnum=True, collapse_repeats=True)
        word_norm_no_collapse = normalize_text(word, remove_non_alnum=True, collapse_repeats=False)
        info = [f"• `{word}` {'(Strict)' if is_strict else '(Smart)'} --> norm: `{word_norm}`"]

        # Strict
        if is_strict and word_norm and word_norm in normalized_compact:
            info.append("  - Strict match: YES")
            matched_any = True
            parts.append("\n".join(info))
            continue
        elif is_strict:
            info.append("  - Strict match: NO")

        # Repeated-run
        has_repeats_in_word = False
        try:
            for m in re.finditer(r'(.)\1+', word_norm_no_collapse):
                has_repeats_in_word = True
                ch = m.group(1)
                run_len = m.end() - m.start()
                if re.search(fr'{re.escape(ch)}' + r'{' + f'{run_len},' + r'}', normalized_compact_no_collapse):
                    info.append(f"  - Repeated-run match: YES (char `{ch}` run >= {run_len})")
                    matched_any = True
                else:
                    info.append(f"  - Repeated-run match: NO (need run >= {run_len})")
        except Exception as e:
            info.append(f"  - Repeated-run check failed: {e}")

        if has_repeats_in_word:
            parts.append("\n".join(info))
            continue

        # Numeric substring
        if word_norm.isdigit():
            info.append(f"  - Numeric substring in compact: {'YES' if (word_norm and word_norm in normalized_compact) else 'NO'}")
            if word_norm and word_norm in normalized_compact:
                matched_any = True
            parts.append("\n".join(info))
            continue

        # Permissive regex against preserved form
        try:
            parts_chars = [re.escape(ch) for ch in word_norm]
            sep_class = r"[^a-z0-9\u0600-\u06FF]*"
            pattern = r"".join(p + sep_class for p in parts_chars)
            regex_match = bool(re.search(pattern, normalized_preserve))
            compact_match = bool(word_norm and word_norm in normalized_compact)

            info.append(f"  - Permissive regex match (preserve): {'YES' if regex_match else 'NO'}")
            info.append(f"  - Compact substring match: {'YES' if compact_match else 'NO'}")

            # Subsequence fallback (limited to length >=3)
            subseq_info = "N/A"
            if len(word_norm) >= 3:
                text_compacted = re.sub(r'[^a-z0-9\u0600-\u06FF]+', '', normalized_preserve)
                matched = 0
                pos = 0
                for ch in word_norm:
                    idx = text_compacted.find(ch, pos)
                    if idx != -1:
                        matched += 1
                        pos = idx + 1
                subseq_match = matched >= max(1, len(word_norm) - 1)
                subseq_info = f"YES (matched {matched}/{len(word_norm)})" if subseq_match else f"NO (matched {matched}/{len(word_norm)})"
                if subseq_match:
                    matched_any = True
            info.append(f"  - Subsequence fallback: {subseq_info}")

            if regex_match or compact_match:
                matched_any = True
        except Exception as e:
            info.append(f"  - Regex/subsequence check failed: {e}")

        parts.append("\n".join(info))

    if not matched_any:
        parts.append("\nNo censor rules matched this input.")

    # Send result (avoid overly long messages)
    msg = "\n\n".join(parts)
    if len(msg) > 3500:
        msg = msg[:3500] + "\n... (output truncated)"
    await update.message.reply_text(msg, parse_mode='Markdown')


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
    
    