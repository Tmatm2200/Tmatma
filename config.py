"""
Configuration file for the Telegram Bot.
Load environment variables and set up constants.
"""
import os
from pathlib import Path
from typing import Final
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory
BASE_DIR: Path = Path(__file__).parent.absolute()

# Bot Configuration
BOT_TOKEN: Final[str] = os.getenv("BOT_TOKEN", "8524740209:AAEEAEetWa4zy3Qve3UCHfCwu9XC8D87FDg")
ADMIN_ID: Final[int] = int(os.getenv("ADMIN_ID", "6196091106"))

# Database
DB_PATH: Final[Path] = BASE_DIR / "bot_data.db"

# Message History
MAX_MESSAGE_HISTORY: Final[int] = 3000

# Anti-Spam Settings
SPAM_MESSAGE_LIMIT: Final[int] = 6
SPAM_TIME_WINDOW: Final[int] = 10  # seconds

# Rate Limits
MAX_CLEAR_COUNT: Final[int] = 100
DELETE_DELAY: Final[float] = 0.05  # seconds between deletes

# Logging
LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT: Final[str] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Feature Flags
ENABLE_ARABIC_RESPONSES: Final[bool] = True
ENABLE_CUSTOM_TRIGGERS: Final[bool] = True