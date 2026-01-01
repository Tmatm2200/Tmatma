"""
Basic command handlers (start, ping, help).
"""
import time
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import handle_errors


@handle_errors
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    text = (
        "🎭 *Moderation Bot*\n\n"
        "*Basic Commands:*\n"
        "⚡ `/ping` - Check bot response time\n"
        "ℹ️ `/help` - Show detailed help\n\n"
        
        "*Moderation:*\n"
        "🧹 `/clear 10` - Clear last N messages (also supports `/clear @username N`)\n"
        "🧹 `/clear_except` @user 10 - Clear except user\n\n"
        
        "*Sticker Control:*\n"
        "🚫 `/block` <link> - Block sticker set\n"
        "✅ `/unblock` <name> - Unblock sticker set\n"
        "📋 `/list` - List blocked sets\n\n"
        
        "*Word Filter:*\n"
        "🛡️ `/censor` word - Add censored word\n"
        "🛡️ `/censor` \"exact phrase\" - Strict match\n"
        "🛡️ `/censor_list` - Show censored words\n\n"
        
        "*Anti-Spam:*\n"
        "🚨 `/antispam_enable` - Enable (5 msgs/10s)\n"
        "😴 `/antispam_disable` - Disable\n"
        "⚙️ `/antispam_limit <count>` - Set message limit\n"
        "🔧 `/antispam_penalty <minutes>` - Set mute penalty\n\n"
        
        "*Admin Settings:* (Owner Only)\n"
        "🔓 `/admins_enable` - Admins bypass filters (only admins with delete/edit message permission)\n"
        "🔒 `/admins_disable` - Admins follow rules"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


@handle_errors
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ping command - check bot latency."""
    start_time = time.time()
    msg = await update.message.reply_text("🏓 Pinging...")
    
    latency = int((time.time() - start_time) * 1000)
    await msg.edit_text(f"🏓 Pong! `{latency}ms`", parse_mode='Markdown')


@handle_errors
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    text = (
        "📚 *Detailed Command Guide*\n\n"
        
        "*Message Clearing:*\n"
        "`/clear 20` - Delete last 20 messages (or `/clear @username 20`)\n"
        "`/clear_except @user1 @user2 15` - Delete 15 messages except from specified users\n\n"
        
        "*Sticker Blocking:*\n"
        "`/block https://t.me/addstickers/SetName` - Block by link\n"
        "`/block SetName` - Block by name\n"
        "`/unblock SetName` - Unblock specific set\n"
        "`/unblock all` - Unblock all sets\n"
        "`/list` - Show all blocked sets\n\n"
        
        "*Word Censoring:*\n"
        "`/censor word1 word2` - Smart match (word boundaries)\n"
        "`/censor \"exact phrase\"` - Strict match (anywhere in text)\n"
        "`/censor_list` - View all censored words\n\n"
        
        "*Anti-Spam Protection:*\n"
        "Automatically deletes messages from users sending more than 5 messages in 10 seconds.\n"
        "Commands: `/antispam_enable`, `/antispam_disable`, `/antispam_limit`, `/antispam_penalty`\n\n"
        
        "*Admin Bypass:*\n"
        "When enabled, admins with delete/edit message permission can bypass sticker blocks and word filters.\n"
        "Owner-only: `/admins_enable` and `/admins_disable`"
    )
    await update.message.reply_text(text, parse_mode='Markdown')