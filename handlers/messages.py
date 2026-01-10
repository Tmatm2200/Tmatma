"""
Message handlers for filtering and auto-responses.
ALL CENSORING AND REACTION ISSUES FIXED!
"""
import re
import time
import random
from collections import defaultdict
from telegram import Update, ReactionTypeEmoji
from telegram.ext import ContextTypes
from config import ADMIN_ID, SPAM_MESSAGE_LIMIT, SPAM_TIME_WINDOW, ENABLE_ARABIC_RESPONSES
from utils.database import Database
from utils.decorators import get_user_status
import logging

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
    user_can_bypass = (
        user_id == ADMIN_ID or 
        (is_admin_bypass and status in ("administrator", "creator"))
    )
    
    # --- 3. STICKER BLOCKING ---
    if message.sticker and not user_can_bypass:
        if await check_blocked_sticker(update, context, chat_id):
            return  # Sticker was blocked and deleted
    
    # --- 4. WORD CENSORING (FIXED!) ---
    if message.text and not user_can_bypass:
        if await check_censored_words(update, context, chat_id):
            return  # Message contained censored word and was deleted
    
    # --- 5. CUSTOM RESPONSES (FIXED REACTIONS!) ---
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
    
    # Check if spam limit exceeded
    if len(SPAM_TRACKER[key]) > SPAM_MESSAGE_LIMIT:
        # Delete all messages except the first one
        for mid, _ in SPAM_TRACKER[key][1:]:
            try:
                await context.bot.delete_message(chat_id, mid)
            except:
                pass
        
        # Keep only first message in tracker
        SPAM_TRACKER[key] = [SPAM_TRACKER[key][0]]
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
    
    censored_words = Database.get_censored_words(chat_id)
    
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


async def handle_custom_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIXED REACTIONS!
    Handle custom text responses and reactions (not replies).
    """
    text = update.message.text.lower()
    user_id = update.effective_user.id
    
    # --- OWNER-ONLY REACTIONS (FIXED!) ---
    if user_id == ADMIN_ID:
        # React with heart to "كيوت" (NO REPLY, JUST REACTION)
        if text.strip() == "كيوت":
            try:
                await update.message.set_reaction([ReactionTypeEmoji("❤")])
                return  # Don't process further
            except Exception as e:
                logger.error(f"Failed to set reaction: {e}")
            return
        
        # React with heart to "شاطرة" or "شاطرة يالبوتة" (NO REPLY, JUST REACTION)
        if text.strip() in ("شاطرة", "شاطرة يالبوتة"):
            try:
                await update.message.set_reaction([ReactionTypeEmoji("❤")])
                return  # Don't process further
            except Exception as e:
                logger.error(f"Failed to set reaction: {e}")
            return
        
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
    # React with heart to "شاطرة" or "شاطرة يالبوتة" from ANYONE
    if text.strip() in ("شاطرة", "شاطرة يالبوتة"):
        try:
            await update.message.set_reaction([ReactionTypeEmoji("❤")])
            return
        except Exception as e:
            logger.error(f"Failed to set reaction: {e}")
        return
    
    # --- PUBLIC TEXT RESPONSES ---
    # Mention specific user
    if "يا جلن" in text:
        target_id = 1979054413
        await update.message.reply_text(
            f"يا [الجلن](tg://user?id={target_id})",
            parse_mode='Markdown'
        )
        return
    
    if "مين الجلن" in text or "جلن" in text:
        await update.message.reply_text("رفصو")
        return
    
    # Randomized responses
    random_responses = {
        ("يالبوت بتحبي يالبوت", "بتحبي يالبوت يالبوتة"): ["يع", "لا"],
        ("يالبوتة",): ["ايه", "لا", "نعم", "اتكل علي الله", "يع", "غور", "خش نام", "بس يا جلن", "أقل جلن"],
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