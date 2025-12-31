"""
Decorators for permission checking and access control.
"""
import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID

logger = logging.getLogger(__name__)


async def get_user_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Get user's status in the chat.
    
    Returns:
        Status string: 'creator', 'administrator', 'member', etc.
    """
    try:
        member = await context.bot.get_chat_member(
            update.effective_chat.id,
            update.effective_user.id
        )
        return member.status
    except Exception as e:
        logger.error(f"Failed to get user status: {e}")
        return "member"


def owner_only(func):
    """Decorator to restrict command to bot owner only."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ This command is owner-only.")
            return
        return await func(update, context)
    return wrapper


def admin_or_owner(func):
    """
    Decorator to restrict command to admins with delete permission or owner.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        # Allow bot owner
        if user_id == ADMIN_ID:
            return await func(update, context)
        
        # Check admin status
        status = await get_user_status(update, context)
        
        # Allow chat creator
        if status == "creator":
            return await func(update, context)
        
        # Check if admin has delete permission
        if status == "administrator":
            try:
                member = await context.bot.get_chat_member(
                    update.effective_chat.id,
                    user_id
                )
                if member.can_delete_messages:
                    return await func(update, context)
            except Exception as e:
                logger.error(f"Failed to check admin permissions: {e}")
        
        await update.message.reply_text(
            "❌ You need to be an admin with message deletion permission."
        )
    
    return wrapper


def handle_errors(func):
    """Decorator for error handling in command handlers."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            try:
                await update.message.reply_text(
                    "❌ An error occurred while processing your command."
                )
            except:
                pass
    return wrapper