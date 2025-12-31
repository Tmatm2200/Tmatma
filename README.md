# 🤖 Telegram Moderation Bot

A professional, modular Telegram bot for group moderation with advanced features like sticker blocking, word filtering, anti-spam protection, and message management.

## ✨ Features

- **🛡️ Advanced Moderation**
  - Block/unblock entire sticker sets
  - Word censorship with strict/smart matching
  - Bulk message deletion
  - Selective message clearing

- **🚨 Anti-Spam Protection**
  - Configurable rate limiting (6 messages / 10 seconds)
  - Automatic spam message deletion
  - Admin bypass option

- **⚙️ Flexible Configuration**
  - Per-chat settings
  - Admin permission controls
  - SQLite database for persistence

- **🏗️ Professional Architecture**
  - Modular design
  - Separation of concerns
  - Type hints throughout
  - Comprehensive error handling

## 📁 Project Structure

```
telegram_bot/
├── main.py              # Entry point
├── config.py            # Configuration
├── requirements.txt     # Dependencies
├── .env.example        # Environment template
│
├── handlers/           # Command handlers
│   ├── basic.py       # Start, ping, help
│   ├── moderation.py  # Block, clear, censor
│   ├── admin.py       # Admin settings
│   └── messages.py    # Message handling
│
└── utils/             # Utilities
    ├── database.py    # Database operations
    ├── decorators.py  # Permission checks
    └── helpers.py     # Helper functions
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- pip
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Installation

1. **Clone or download the project**
   ```bash
   mkdir telegram_bot
   cd telegram_bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the bot**
   
   Create `.env` file:
   ```env
   BOT_TOKEN=your_bot_token_here
   ADMIN_ID=your_telegram_user_id
   LOG_LEVEL=INFO
   ```

4. **Run the bot**
   ```bash
   python main.py
   ```

## 📚 Commands

### Basic Commands
- `/start` - Display welcome message and command list
- `/ping` - Check bot response time
- `/help` - Show detailed help

### Moderation Commands
- `/clear <n>` - Delete last N messages (default: 10, max: 100)
- `/clear_except @user1 @user2 <n>` - Delete messages except from specified users
- `/block <link|name>` - Block a sticker set
- `/unblock <name|all>` - Unblock sticker set(s)
- `/list` - List all blocked sticker sets

### Word Filter Commands
- `/censor word1 word2` - Add words to filter (smart matching)
- `/censor "exact phrase"` - Add phrase (strict matching)
- `/censor_list` - Show all censored words

### Anti-Spam Commands
- `/antispam_enable` - Enable anti-spam (6 msgs/10s limit)
- `/antispam_disable` - Disable anti-spam

### Admin Commands (Owner Only)
- `/admins_enable` - Allow admins to bypass filters
- `/admins_disable` - Make admins follow rules

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram bot token | Required |
| `ADMIN_ID` | Your Telegram user ID | Required |
| `LOG_LEVEL` | Logging level | INFO |

### Database

The bot uses SQLite for data persistence. Database file: `bot_data.db`

**Tables:**
- `blocked_sets` - Blocked sticker sets per chat
- `censored_words` - Censored words per chat
- `admin_perms` - Admin bypass settings
- `chat_settings` - Chat-specific settings

## 🛠️ Development

### Adding New Features

1. **Create a new handler** in `handlers/`
2. **Add database methods** in `utils/database.py`
3. **Register handler** in `main.py`

### Code Style

- Follow PEP 8
- Use type hints
- Add docstrings to functions
- Keep functions small and focused

### Testing

```bash
# Run with debug logging
LOG_LEVEL=DEBUG python main.py
```

### Smoke test (quick)

A simple startup smoke check is included to validate the environment and perform an optional network check:

- Quick (no network):

```bash
python scripts/smoke_check.py
```

- With network (checks token by calling `get_me`):

```bash
python scripts/smoke_check.py --network
```

The script exits with code `0` when all checks pass and non-zero when any check fails. The quick check is safe for CI.

## 🐛 Troubleshooting

**Bot not responding?**
- Check bot token is correct
- Ensure bot is added to group
- Verify bot has admin permissions

**Commands not working?**
- Check if you're an admin
- Verify bot has delete message permission
- Check logs for errors

**Database errors?**
- Ensure write permissions in bot directory
- Check disk space
- Restart bot

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request
