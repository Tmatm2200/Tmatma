"""
Helper utility functions.
"""
from telegram import User


def get_markdown_mention(user: User) -> str:
    """
    Create a markdown mention link for a user.
    
    Args:
        user: Telegram User object
        
    Returns:
        Markdown formatted mention string
    """
    try:
        if user.username:
            return f"[{user.first_name}​](https://t.me/{user.username})"
        else:
            return f"[{user.first_name}​](tg://user?id={user.id})"
    except:
        return user.first_name or "User"


def format_user_info(user: User) -> str:
    """
    Format user information as a readable string.
    
    Args:
        user: Telegram User object
        
    Returns:
        Formatted user information
    """
    info = f"👤 *User Information*\n\n"
    info += f"Name: {user.first_name}"
    
    if user.last_name:
        info += f" {user.last_name}"
    
    info += f"\nID: `{user.id}`"
    
    if user.username:
        info += f"\nUsername: @{user.username}"
    
    if user.is_bot:
        info += "\n🤖 This is a bot"
    
    return info


def extract_set_name(text: str) -> str:
    """
    Extract sticker set name from link or return as-is.
    
    Args:
        text: Sticker set link or name
        
    Returns:
        Cleaned sticker set name
    """
    if "addstickers/" in text:
        return text.split("addstickers/")[-1].split("?")[0].strip().lower()
    return text.strip().lower()