"""
Admin-only commands for bot configuration.
"""
from telegram import Update
from telegram.ext import ContextTypes
from utils.database import Database
from utils.decorators import owner_only, handle_errors


@owner_only
@handle_errors
async def admins_enable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admins_enable - allow admins to bypass filters."""
    chat_id = str(update.effective_chat.id)
    Database.set_admin_bypass(chat_id, True)
    await update.message.reply_text("✅ Admins can now bypass sticker blocks and word filters.")


@owner_only
@handle_errors
async def admins_disable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admins_disable - make admins follow rules."""
    chat_id = str(update.effective_chat.id)
    Database.set_admin_bypass(chat_id, False)
    await update.message.reply_text("✅ Admins must now follow all rules like regular users.")