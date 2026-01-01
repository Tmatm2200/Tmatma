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


def normalize_text(text: str, remove_non_alnum: bool = True) -> str:
    """
    Normalize text for censoring/matching.

    Steps:
    - Lowercase
    - Remove diacritics
    - Map common leet characters to letters
    - Optionally remove non-alphanumeric characters
    - Collapse repeated characters

    Args:
        text: input text
        remove_non_alnum: if True, remove non-alphanumeric characters; if False, keep them

    Returns:
        Normalized string
    """
    import unicodedata
    import re

    # Lowercase
    s = (text or "").lower()

    # Remove diacritics
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))

    # Common leet substitutions
    # Include Arabic-Indic digits and common punctuation mappings used in obfuscation
    leet_map = {
        '0': 'o',
        '1': 'i',
        '3': 'e',
        '4': 'a',
        '5': 's',
        '6': '6',
        '7': 't',
        '@': 'a',
        '$': 's',
        '!': 'i',
        '|': 'i',
        '€': 'e',
        # Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) and Eastern Arabic-Indic (Persian) digits (۰۱۲۳۴۵۶۷۸۹)
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4', '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
        '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4', '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        # Common Arabic punctuation that might be used as separators will be removed by normalization
    }

    # If Arabic characters are present, prefer a mapping that does not
    # inject Latin letters between Arabic letters. Map Arabic-Indic digits, but
    # treat common symbol separators as separators (remove or convert to space).
    if re.search(r'[\u0600-\u06FF]', s):
        arabic_map = {}
        # Map Arabic-Indic / Persian digits to western digits
        for k, v in leet_map.items():
            if k in '٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹':
                arabic_map[k] = v
        # Treat common symbol separators as empty so they don't inject Latin letters
        separators = ['@', '$', '!', '|', '#', '%', '&', '*']
        for sep in separators:
            arabic_map[sep] = ''
        s = ''.join(arabic_map.get(ch, ch) for ch in s)
    else:
        s = ''.join(leet_map.get(ch, ch) for ch in s)

    # Optionally remove non-alphanumeric (keep them as separators if requested)
    # Allow Arabic letters (Unicode range \u0600-\u06FF) so Arabic words are preserved
    arabic_range = '\\u0600-\\u06FF'
    if remove_non_alnum:
        s = re.sub(rf'[^a-z0-9{arabic_range}]', '', s)
    else:
        # Replace runs of non-alnum with a single placeholder space (to simplify regex matching)
        s = re.sub(rf'[^a-z0-9{arabic_range}]+', ' ', s)

    # Collapse repeated characters (e.g., shiiit -> shit)
    # Collapse repeated characters (e.g., shiiit -> shit)
    s = re.sub(r'(.)\1+', r'\1', s)

    # If Arabic letters exist, also collapse repeated combining marks/spaces
    if re.search(r'[\u0600-\u06FF]', s):
        s = re.sub(r'\s+', ' ', s)

    s = s.strip()
    s = s.strip()
    return s