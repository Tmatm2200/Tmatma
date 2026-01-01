"""
Message handlers for filtering and auto-responses.
"""
import logging
import re
import time
import random
from collections import defaultdict
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from config import ADMIN_ID, SPAM_MESSAGE_LIMIT, SPAM_TIME_WINDOW, ENABLE_ARABIC_RESPONSES
from utils.database import Database
from utils.decorators import get_user_status

logger = logging.getLogger(__name__)

# Spam tracking: {(chat_id, user_id): [(message_id, timestamp), ...]}
SPAM_TRACKER = defaultdict(list)


async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler - checks for spam, blocked stickers, censored words."""
    if not update.message:
        return
    
    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id
    message = update.message
    
    # --- 1. ANTI-SPAM CHECK ---
    if Database.is_antispam_enabled(chat_id) and user_id != ADMIN_ID:
        if await check_spam(update, context):
            return  # Message was spam and deleted
    
    # --- 2. CHECK PERMISSIONS ---
    status = await get_user_status(update, context)
    is_admin_bypass = Database.is_admin_bypass_enabled(chat_id)

    # Allow bot owner always
    user_can_bypass = user_id == ADMIN_ID

    # If admin bypass is enabled, only allow creators or administrators
    # who have message delete or edit permissions to bypass filters.
    if not user_can_bypass and is_admin_bypass and status in ("administrator", "creator"):
        if status == "creator":
            user_can_bypass = True
        else:
            try:
                member = await context.bot.get_chat_member(
                    update.effective_chat.id, user_id
                )
                # Require at least one of delete/edit permissions
                if getattr(member, 'can_delete_messages', False) or getattr(member, 'can_edit_messages', False):
                    user_can_bypass = True
            except Exception:
                # If we can't verify permissions, do not allow bypass
                pass
    
    # --- 3. STICKER BLOCKING ---
    if message.sticker and not user_can_bypass:
        if await check_blocked_sticker(update, context, chat_id):
            return  # Sticker was blocked and deleted
    
    # --- 4. WORD CENSORING ---
    if message.text and not user_can_bypass:
        if await check_censored_words(update, context, chat_id):
            return  # Message contained censored word and was deleted
    
    # --- 5. CUSTOM RESPONSES (Optional) ---
    if ENABLE_ARABIC_RESPONSES and message.text:
        await handle_custom_responses(update, context)


async def check_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if message is spam and delete if necessary.
    Returns True if message was deleted as spam.
    """
    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id
    message_id = update.message.message_id
    
    key = (chat_id, user_id)
    now = time.time()
    
    # Clean old messages outside time window
    SPAM_TRACKER[key] = [
        (mid, ts) for mid, ts in SPAM_TRACKER[key]
        if now - ts < SPAM_TIME_WINDOW
    ]
    
    # Add current message
    SPAM_TRACKER[key].append((message_id, now))
    
    # Get per-chat spam settings
    limit, mute_minutes = Database.get_spam_settings(chat_id)

    # Check if spam limit exceeded
    if len(SPAM_TRACKER[key]) > limit:
        logger.info(f"Spam threshold exceeded for user {user_id} in chat {chat_id}: {len(SPAM_TRACKER[key])} messages (limit {limit})")
        # Delete all messages except the first one
        deleted_count = 0
        for mid, _ in SPAM_TRACKER[key][1:]:
            try:
                await context.bot.delete_message(chat_id, mid)
                deleted_count += 1
            except Exception as e:
                logger.debug(f"Failed to delete spam message {mid} in chat {chat_id}: {e}")
        logger.info(f"Deleted {deleted_count} spam messages for user {user_id} in chat {chat_id}")

        # Keep only first message in tracker
        SPAM_TRACKER[key] = [SPAM_TRACKER[key][0]]

        # Mute the user for configured duration (disallow messages and media)
        try:
            until_ts = int(time.time() + mute_minutes * 60)
            # Build restrictive ChatPermissions (fields vary between PTB versions)
            permissions = ChatPermissions(
                can_send_messages=False,
                can_send_polls=False,
                can_send_other_messages=False
            )
            # Use bot.restrict_chat_member to mute
            try:
                # Verify bot has restrict capability (best-effort); avoid silent failures
                try:
                    bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
                    can_restrict = getattr(bot_member, 'can_restrict_members', False)
                except Exception as e:
                    logger.debug(f"Could not verify bot's chat member permissions: {e}")
                    can_restrict = True  # assume True and attempt; we'll catch errors below

                if not can_restrict:
                    logger.warning(f"Bot lacks restrict permissions in chat {chat_id}; cannot mute user {user_id}")
                    try:
                        await context.bot.send_message(chat_id, "⚠️ I don't have permission to mute users in this chat. Please grant 'Restrict members' admin permission.")
                    except Exception:
                        pass
                else:
                    await context.bot.restrict_chat_member(chat_id, user_id, permissions=permissions, until_date=until_ts)
                    logger.info(f"Muted user {user_id} in chat {chat_id} for {mute_minutes} minutes")
                    # Notify chat (best-effort)
                    try:
                        await context.bot.send_message(chat_id, f"🔇 User has been muted for {mute_minutes} minutes due to spam.")
                    except Exception as e:
                        logger.debug(f"Failed to send mute notification: {e}")
            except Exception as e:
                # Log error so we can see why mute isn't applied (missing permissions, etc.)
                logger.exception(f"Failed to mute user {user_id} in chat {chat_id}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error when muting user {user_id}: {e}")

        return True
    
    return False


async def check_blocked_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str) -> bool:
    """
    Check if sticker is from blocked set and delete if needed.
    Returns True if sticker was deleted.
    """
    sticker = update.message.sticker
    if not sticker or not sticker.set_name:
        return False
    
    set_name = sticker.set_name.lower()
    
    if Database.is_set_blocked(chat_id, set_name):
        try:
            await update.message.delete()
            return True
        except:
            pass
    
    return False


async def check_censored_words(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str) -> bool:
    """
    Check if message contains censored words and delete if needed.
    Returns True if message was deleted.

    Uses normalization and permissive regex matching to catch obfuscated words
    (e.g., 'sh!t', 's.h.i.t', '5h1t', 'shiiit').
    """
    from utils.helpers import normalize_text

    raw_text = update.message.text or ""
    # Normalized versions of the message
    # compact version removes non-alnum and (by default) collapses repeated chars
    normalized_compact = normalize_text(raw_text, remove_non_alnum=True, collapse_repeats=True)
    # preserve version keeps separators as spaces and (importantly) keeps repeated chars
    normalized_preserve = normalize_text(raw_text, remove_non_alnum=False, collapse_repeats=False)
    # compact version without collapsing repeats (used for detecting repeated runs)
    normalized_compact_no_collapse = normalize_text(raw_text, remove_non_alnum=True, collapse_repeats=False)

    censored_words = Database.get_censored_words(chat_id)
    if not censored_words:
        return False

    for word, is_strict in censored_words:
        word_norm = normalize_text(word, remove_non_alnum=True, collapse_repeats=True)
        word_norm_no_collapse = normalize_text(word, remove_non_alnum=True, collapse_repeats=False)

        # Strict match: normalized substring anywhere in compact normalized message
        if is_strict:
            if word_norm and word_norm in normalized_compact:
                try:
                    logger.info(f"Censor matched '{word}' via strict match in chat {chat_id}")
                    await update.message.delete()
                    return True
                except Exception as e:
                    logger.debug(f"Failed to delete message after strict match: {e}")
            continue

        # Special handling: if the censored token contains repeated characters
        # (e.g., 'خخخخخ'), treat it as a run match and require at least that many
        # consecutive characters in the incoming message. This avoids collapsing
        # repeats and matching single characters.
        has_repeats_in_word = False
        try:
            for m in re.finditer(r'(.)\1+', word_norm_no_collapse):
                has_repeats_in_word = True
                ch = m.group(1)
                run_len = m.end() - m.start()
                # Check for run in the message (compact, no collapse so repeats preserved)
                if re.search(fr'{re.escape(ch)}' + r'{' + f'{run_len},' + r'}', normalized_compact_no_collapse):
                    try:
                        logger.info(f"Censor matched '{word}' via repeated-run match in chat {chat_id}")
                        await update.message.delete()
                        return True
                    except Exception as e:
                        logger.debug(f"Failed to delete message after repeated-run match: {e}")
        except Exception:
            pass

        # If the censored token included repeated runs but we didn't find a
        # matching long run in the message, continue to next censored token
        # to avoid matching a collapsed version (which would match a single char).
        if has_repeats_in_word:
            continue

        # Smart match:
        # If purely numeric, do substring match in compact normalized
        if word_norm.isdigit():
            if word_norm and word_norm in normalized_compact:
                try:
                    logger.info(f"Censor matched '{word}' via numeric substring in chat {chat_id}")
                    await update.message.delete()
                    return True
                except Exception as e:
                    logger.debug(f"Failed to delete message after numeric substring match: {e}")
            continue

        # Otherwise, build permissive regex from normalized word that allows
        # non-alphanumeric separators between characters and check against the
        # normalized_preserve form (which has separators preserved as spaces).
        if word_norm:
            try:
                # Build pattern like: s[^a-z0-900-FF]*h[^a-z0-900-FF]*...
                # Use a character class that includes Arabic letters and digits
                parts = [re.escape(ch) for ch in word_norm]
                sep_class = r"[^a-z0-9\u0600-\u06FF]*"
                pattern = r"".join(p + sep_class for p in parts)
                if re.search(pattern, normalized_preserve):
                    try:
                        logger.info(f"Censor matched '{word}' via permissive regex in chat {chat_id}")
                        await update.message.delete()
                        return True
                    except Exception as e:
                        logger.debug(f"Failed to delete message after regex match: {e}")
                # Fallback: compact substring check
                if word_norm in normalized_compact:
                    try:
                        logger.info(f"Censor matched '{word}' via compact substring in chat {chat_id}")
                        await update.message.delete()
                        return True
                    except Exception as e:
                        logger.debug(f"Failed to delete message after compact substring match: {e}")

                # Additional fallback (restricted): subsequence match allowing at most one missing
                # character — only applied to words of reasonable length to avoid false positives.
                try:
                    MIN_SUBSEQ_LEN = 3
                    if len(word_norm) >= MIN_SUBSEQ_LEN:
                        # Build a compacted searchable text (letters and digits and arabic letters only)
                        text_compacted = re.sub(r'[^a-z0-9\u0600-\u06FF]+', '', normalized_preserve)
                        # Count matched characters of word_norm as ordered subsequence
                        matched = 0
                        pos = 0
                        for ch in word_norm:
                            idx = text_compacted.find(ch, pos)
                            if idx != -1:
                                matched += 1
                                pos = idx + 1
                        # Allow at most one missing character
                        if matched >= max(1, len(word_norm) - 1):
                            try:
                                logger.info(f"Censor matched '{word}' via subsequence fallback in chat {chat_id}")
                                await update.message.delete()
                                return True
                            except Exception as e:
                                logger.debug(f"Failed to delete message after subsequence match: {e}")
                except Exception as e:
                    logger.exception(f"Error during subsequence fallback: {e}")
            except Exception:
                pass

    return False


async def handle_custom_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom text responses (Arabic responses example)."""
    text = update.message.text.lower()
    user_id = update.effective_user.id
    
    # --- OWNER-ONLY TRIGGERS ---
    if user_id == ADMIN_ID:
        owner_responses = {
            "بنتي": "نعم",
            "يالبتبوتة": "نعم",
            "مين حبيبة بابا": "أنا",
            "مين أشطر كتكوتة": "أنا",
        }
        
        for trigger, response in owner_responses.items():
            if trigger in text:
                await update.message.reply_text(response)
                return
        
        # Special reactions for owner
        if text.strip() == "كيوت":
            # Try to set a reaction if supported; fallback to sending emoji text
            try:
                if hasattr(update.message, "set_reaction"):
                    try:
                        await update.message.set_reaction("❤️")
                    except TypeError:
                        try:
                            await update.message.set_reaction(reaction="❤️")
                        except Exception:
                            await update.message.reply_text("❤️")
                else:
                    await update.message.reply_text("❤️")
            except Exception:
                try:
                    await update.message.reply_text("❤️")
                except:
                    pass
            return

    
    # --- PUBLIC RESPONSES ---
    # Mention specific user
    if "يا جلنف" in text:
        target_id = 1979054413
        await update.message.reply_text(
            f"يا [جلنف](tg://user?id={target_id})",
            parse_mode='Markdown'
        )
        return
    
    if "مين الجلنف" in text or "جلنف" in text:
        await update.message.reply_text("رفصو")
        return
    
        if text.strip() in ("شاطرة", "شاطرة يالبوتة"):
            # Try to set a reaction if supported; fallback to sending emoji text
            try:
                if hasattr(update.message, "set_reaction"):
                    try:
                        await update.message.set_reaction("❤️")
                    except TypeError:
                        try:
                            await update.message.set_reaction(reaction="❤️")
                        except Exception:
                            await update.message.reply_text("❤️")
                else:
                    await update.message.reply_text("❤️")
            except Exception:
                try:
                    await update.message.reply_text("❤️")
                except:
                    pass
            return

    # Randomized responses
    random_responses = {
        ("يالبوت بتحبي يالبوت", "بتحبي يالبوت يالبوتة"): ["يع", "لا"],
        ("يالبوتة", "يا بنته"): ["ايه", "لا", "نعم", "اتكل علي الله", "يع", "غور", "خش نام", "بس يا جلنف", "أقل جلنف", "فاك يو"],
        ("شتاينز",): ["شتاينز الأعظم", "عمك"]
    }
    
    for triggers, responses in random_responses.items():
        if any(trigger in text for trigger in triggers):
            await update.message.reply_text(random.choice(responses))
            return


async def track_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track messages for clear commands."""
    from handlers.moderation import track_message
    
    msg = update.message or update.edited_message
    if not msg:
        return
    
    user = msg.from_user
    if not user:
        return
    
    username = user.username.lower() if user.username else "unknown"
    track_message(msg.chat_id, msg.message_id, user.id, username)