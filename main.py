"""
Main entry point for the Telegram Bot.
Initializes the bot and registers all handlers.
"""
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters
)

# Import configuration
from config import BOT_TOKEN, LOG_LEVEL, LOG_FORMAT

# Import database
from utils.database import Database

# Import handlers
from handlers.basic import start, ping, help_command
from handlers.moderation import (
    block_sticker, unblock_sticker, list_blocked_sets,
    censor_word, list_censored_words,
    clear_messages, clear_except,
    antispam_enable, antispam_disable, antispam_limit, antispam_penalty,
    label_bad, label_normal, list_collected,
    ai_moderation_on, ai_moderation_off, debug_badness
)
from handlers.admin import admins_enable, admins_disable
from handlers.messages import handle_messages, track_messages

# Setup logging
logging.basicConfig(
    format=LOG_FORMAT,
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)


def register_handlers(app: Application) -> None:
    """Register all command and message handlers."""
    
    # Basic commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("help", help_command))
    
    # Moderation commands
    app.add_handler(CommandHandler("block", block_sticker))
    app.add_handler(CommandHandler("unblock", unblock_sticker))
    app.add_handler(CommandHandler("list", list_blocked_sets))
    app.add_handler(CommandHandler("censor", censor_word))
    app.add_handler(CommandHandler("uncensor", unblock_sticker))
    app.add_handler(CommandHandler("censor_list", list_censored_words))
    app.add_handler(CommandHandler("clear", clear_messages))
    app.add_handler(CommandHandler("clear_except", clear_except))
    
    # Anti-spam commands
    app.add_handler(CommandHandler("antispam_enable", antispam_enable))
    app.add_handler(CommandHandler("antispam_disable", antispam_disable))
    app.add_handler(CommandHandler("antispam_limit", antispam_limit))
    app.add_handler(CommandHandler("antispam_penalty", antispam_penalty))

    # AI moderation commands
    app.add_handler(CommandHandler("lb", label_bad))
    app.add_handler(CommandHandler("ln", label_normal))
    app.add_handler(CommandHandler("lc", list_collected))
    app.add_handler(CommandHandler("br_on", ai_moderation_on))
    app.add_handler(CommandHandler("br_off", ai_moderation_off))
    app.add_handler(CommandHandler("bd", debug_badness))

    # Admin commands
    app.add_handler(CommandHandler("admins_enable", admins_enable))
    app.add_handler(CommandHandler("admins_disable", admins_disable))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.ALL, handle_messages))
    app.add_handler(TypeHandler(Update, track_messages), group=-1)
    
    logger.info("All handlers registered successfully")


def main() -> None:
    """Initialize and start the bot."""
    logger.info("Starting Telegram Bot...")
    
    # Initialize database
    try:
        Database.init_tables()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Register all handlers
    register_handlers(app)
    
    # Start bot
    logger.info("Bot is running...")
    print("✅ Bot started successfully! Press Ctrl+C to stop.")
    
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)