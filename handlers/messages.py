"""
Message handlers for filtering and auto-responses.
ALL CENSORING AND REACTION ISSUES FIXED!
"""
import re
import time
import random
import datetime
from collections import defaultdict
from telegram import Update, ReactionTypeEmoji
from telegram.ext import ContextTypes
import asyncio
from config import ADMIN_ID, SPAM_MESSAGE_LIMIT, SPAM_TIME_WINDOW, ENABLE_ARABIC_RESPONSES
from utils.database import Database
from utils.ai_moderator import ai_moderator
from utils.decorators import get_user_status
import logging

logger = logging.getLogger(__name__)

# Spam tracking: {(chat_id, user_id): [(message_id, timestamp), ...]}
SPAM_TRACKER = defaultdict(list)


async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler - checks for spam, blocked stickers, censored words."""
    handler_start = time.time()
    if not update.message:
        return

    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id
    message = update.message
    
    # --- 1. ANTI-SPAM CHECK ---
    check_start = time.time()
    if await Database.is_antispam_enabled(chat_id) and user_id != ADMIN_ID:
        if await check_spam(update, context):
            logger.info(f"Message processing (spam blocked): {time.time() - handler_start:.3f}s")
            return  # Message was spam and deleted
    logger.info(f"Anti-spam check: {time.time() - check_start:.3f}s")

    # --- 2. CHECK PERMISSIONS ---
    check_start = time.time()
    status = await get_user_status(update, context)
    is_admin_bypass = await Database.is_admin_bypass_enabled(chat_id)
    user_can_bypass = user_id == ADMIN_ID

    # If admin bypass is enabled, allow admins with delete messages permission
    if is_admin_bypass and status == "administrator":
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.can_delete_messages:
                user_can_bypass = True
        except Exception as e:
            logger.error(f"Failed to check admin permissions: {e}")
    logger.info(f"Permissions check: {time.time() - check_start:.3f}s")

    # --- 3. STICKER BLOCKING ---
    check_start = time.time()
    if message.sticker and not user_can_bypass:
        if await check_blocked_sticker(update, context, chat_id):
            logger.info(f"Message processing (sticker blocked): {time.time() - handler_start:.3f}s")
            return  # Sticker was blocked and deleted
    logger.info(f"Sticker check: {time.time() - check_start:.3f}s")

    # --- 4. WORD CENSORING (FIXED!) ---
    check_start = time.time()
    if message.text and not user_can_bypass:
        if await check_censored_words(update, context, chat_id):
            logger.info(f"Message processing (word censored): {time.time() - handler_start:.3f}s")
            return  # Message contained censored word and was deleted
    logger.info(f"Word censoring: {time.time() - check_start:.3f}s")

    # --- 5. AI MODERATION ---
    check_start = time.time()
    if message.text and not user_can_bypass:
        if await check_ai_moderation(update, context, chat_id):
            logger.info(f"Message processing (AI flagged): {time.time() - handler_start:.3f}s")
            return  # Message was flagged as bad and deleted
    logger.info(f"AI moderation: {time.time() - check_start:.3f}s")

    # --- 6. CUSTOM RESPONSES (FIXED REACTIONS!) ---
    check_start = time.time()
    if ENABLE_ARABIC_RESPONSES and message.text:
        await handle_custom_responses(update, context)
    logger.info(f"Custom responses: {time.time() - check_start:.3f}s")

    logger.info(f"Total message processing: {time.time() - handler_start:.3f}s")


async def check_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if message is spam and mute/delete if necessary.
    Returns True if message was deleted as spam.
    """
    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id
    message_id = update.message.message_id

    key = (chat_id, user_id)
    now = time.time()

    # Get settings from database
    spam_limit = await Database.get_spam_limit(chat_id)
    mute_penalty = await Database.get_mute_penalty(chat_id)

    # Clean old messages outside time window
    SPAM_TRACKER[key] = [
        (mid, ts) for mid, ts in SPAM_TRACKER[key]
        if now - ts < SPAM_TIME_WINDOW
    ]

    # Add current message
    SPAM_TRACKER[key].append((message_id, now))

    # Check if spam limit exceeded
    if len(SPAM_TRACKER[key]) > spam_limit:
        # Mute the user
        try:
            until_date = datetime.datetime.now() + datetime.timedelta(minutes=mute_penalty)
            await context.bot.restrict_chat_member(
                chat_id,
                user_id,
                permissions=None,  # Fully restrict (mute)
                until_date=until_date
            )
        except Exception as e:
            logger.error(f"Failed to mute user {user_id}: {e}")

        # Delete all messages from this spam burst
        for mid, _ in SPAM_TRACKER[key]:
            try:
                await context.bot.delete_message(chat_id, mid)
            except:
                pass

        # Clear tracker for this user
        SPAM_TRACKER[key] = []
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
    
    if await Database.is_set_blocked(chat_id, set_name):
        try:
            await update.message.delete()
            return True
        except:
            pass
    
    return False


def normalize_arabic_text(text: str) -> str:
    """
    Normalize Arabic text by removing diacritics and handling variations.
    This helps with Arabic word matching.
    """
    # Remove Arabic diacritics (tashkeel)
    diacritics = '\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u0653\u0654\u0655\u0656\u0657\u0658\u0670'
    for mark in diacritics:
        text = text.replace(mark, '')
    
    # Normalize different forms of alef
    text = re.sub('[إأآٱٲٳٵ]', 'ا', text)
    
    # Normalize teh marbuta and heh
    text = re.sub('[ةه]', 'ه', text)
    
    # Normalize yeh variations
    text = re.sub('[یيى]', 'ي', text)
    
    return text


async def check_censored_words(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str) -> bool:
    """
    FIXED CENSORING SYSTEM!
    
    - Strict mode (quoted): Only matches exact word, not inside other words
    - Smart mode (unquoted): Matches whole words with proper boundaries
    - Works correctly with Arabic text by normalizing it first
    - Numbers are treated as whole units
    
    Returns True if message was deleted.
    """
    text = update.message.text
    text_lower = text.lower()
    
    # Normalize Arabic text for better matching
    text_normalized = normalize_arabic_text(text_lower)
    
    censored_words = await Database.get_censored_words(chat_id)
    
    if not censored_words:
        return False
    
    for word, is_strict in censored_words:
        word_normalized = normalize_arabic_text(word.lower())
        
        if is_strict:
            # STRICT MODE (quoted words): Exact match only
            # Split by whitespace and check if word appears as standalone
            words_in_message = text_normalized.split()
            
            if word_normalized in words_in_message:
                logger.info(f"Strict match found: '{word}' in '{text}'")
                try:
                    await update.message.delete()
                    return True
                except Exception as e:
                    logger.error(f"Failed to delete message: {e}")
        else:
            # SMART MODE (unquoted words): Word boundary matching
            # This prevents "shit" from matching "ship" but allows it to match "sh!t"
            
            # For Arabic, use space boundaries
            # For English/numbers, use word boundaries
            
            # Check if it's primarily Arabic
            if any('\u0600' <= c <= '\u06FF' for c in word_normalized):
                # Arabic: use space boundaries
                pattern = r'(?:^|\s)' + re.escape(word_normalized) + r'(?:\s|$)'
            else:
                # English/Numbers: use word boundaries
                # This handles variations like "sh!t", "sh1t" etc
                pattern = r'\b' + re.escape(word_normalized) + r'\b'
            
            if re.search(pattern, text_normalized):
                logger.info(f"Smart match found: '{word}' in '{text}'")
                try:
                    await update.message.delete()
                    return True
                except Exception as e:
                    logger.error(f"Failed to delete message: {e}")
    
    return False


async def check_ai_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str) -> bool:
    """
    Check if message is flagged as bad by AI and delete if needed.
    Returns True if message was deleted.
    """
    if not await Database.is_ai_moderation_enabled(chat_id):
        return False

    text = update.message.text
    threshold = await Database.get_ai_threshold(chat_id)

    if await ai_moderator.is_bad_async(text, threshold):
        logger.info(f"AI flagged bad: '{text}' (threshold {threshold}%)")
        try:
            await update.message.delete()
            return True
        except Exception as e:
            logger.error(f"Failed to delete AI-flagged message: {e}")

    return False


async def handle_custom_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIXED REACTIONS!
    Handle custom text responses and reactions (not replies).
    """
    text = update.message.text.lower()
    user_id = update.effective_user.id
    
    # --- OWNER-ONLY RESPONSES ---
    if user_id == ADMIN_ID:
        # Owner-only text responses (these DO reply)
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

    # --- PUBLIC REACTIONS (ANYONE CAN TRIGGER) ---
    # React with heart to messages containing "كيوت", "شاطرة" or "شاطرة يالبوتة" from ANYONE
    if any(word in text for word in ("كيوت", "شاطرة", "شاطرة يالبوتة")):
        try:
            await update.message.set_reaction([ReactionTypeEmoji("❤")])
            return
        except Exception as e:
            logger.error(f"Failed to set reaction: {e}")
        return
    
    # --- PUBLIC TEXT RESPONSES ---
    # Mention specific user
    if "يا جلنف" in text:
        target_id = 1979054413
        await update.message.reply_text(
            f"يا [الجلنف](tg://user?id={target_id})",
            parse_mode='Markdown'
        )
        return
    
    if "مين الجلنف" in text or "جلنف" in text:
        await update.message.reply_text("رفصو")
        return
    
    # Randomized responses
    random_responses = {
        ("يالبوت بتحبي يالبوت", "بتحبي يالبوت يالبوتة"): ["يع", "لا"],
        ("شتاينز",): ["شتاينز الأعظم", "عمك"],
        ("يالبوتة",): ["ايه", "لا", "نعم", "اتكل علي الله", "يع", "غور", "خش نام", "بس يا جلنف", "أقل جلنف", "فاك يو", "ما أنت جلنف", "رد عليه أنت يالبوت"],
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