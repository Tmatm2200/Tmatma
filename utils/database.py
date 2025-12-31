"""
Database operations for the bot.
Centralized database access with proper error handling.
"""
import sqlite3
import logging
from typing import Optional, List, Tuple, Any
from contextlib import contextmanager
from config import DB_PATH

logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection():
    """Context manager for database connections with proper cleanup."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()


def execute_query(
    query: str,
    params: Tuple = (),
    fetch_one: bool = False,
    fetch_all: bool = False
) -> Optional[Any]:
    """
    Execute a database query with parameters.
    
    Args:
        query: SQL query string
        params: Query parameters
        fetch_one: Return single row
        fetch_all: Return all rows
        
    Returns:
        Query result or None on error
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                return cursor.fetchall()
            else:
                return cursor.rowcount
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        return None


class Database:
    """Database interface for bot operations."""
    
    @staticmethod
    def init_tables() -> None:
        """Initialize all database tables."""
        queries = [
            """CREATE TABLE IF NOT EXISTS blocked_sets (
                chat_id TEXT NOT NULL,
                set_name TEXT NOT NULL,
                UNIQUE(chat_id, set_name)
            )""",
            """CREATE TABLE IF NOT EXISTS censored_words (
                chat_id TEXT NOT NULL,
                word TEXT NOT NULL,
                is_strict INTEGER DEFAULT 0,
                UNIQUE(chat_id, word)
            )""",
            """CREATE TABLE IF NOT EXISTS admin_perms (
                chat_id TEXT PRIMARY KEY,
                admins_allowed INTEGER DEFAULT 1
            )""",
            """CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id TEXT PRIMARY KEY,
                antispam_enabled INTEGER DEFAULT 0
            )"""
        ]
        
        for query in queries:
            execute_query(query)
        
        logger.info("Database initialized successfully")
    
    # --- Blocked Stickers ---
    @staticmethod
    def add_blocked_set(chat_id: str, set_name: str) -> bool:
        """Add a blocked sticker set."""
        result = execute_query(
            "INSERT OR REPLACE INTO blocked_sets (chat_id, set_name) VALUES (?, ?)",
            (chat_id, set_name)
        )
        return result is not None and result > 0
    
    @staticmethod
    def remove_blocked_set(chat_id: str, set_name: str) -> bool:
        """Remove a blocked sticker set."""
        result = execute_query(
            "DELETE FROM blocked_sets WHERE chat_id = ? AND set_name = ?",
            (chat_id, set_name)
        )
        return result is not None and result > 0
    
    @staticmethod
    def get_blocked_sets(chat_id: str) -> List[str]:
        """Get all blocked sets for a chat."""
        result = execute_query(
            "SELECT set_name FROM blocked_sets WHERE chat_id = ?",
            (chat_id,),
            fetch_all=True
        )
        return [row[0] for row in result] if result else []
    
    @staticmethod
    def is_set_blocked(chat_id: str, set_name: str) -> bool:
        """Check if a sticker set is blocked."""
        result = execute_query(
            "SELECT 1 FROM blocked_sets WHERE chat_id = ? AND set_name = ? LIMIT 1",
            (chat_id, set_name),
            fetch_one=True
        )
        return result is not None
    
    @staticmethod
    def clear_all_blocked_sets(chat_id: str) -> bool:
        """Remove all blocked sticker sets for a chat."""
        result = execute_query(
            "DELETE FROM blocked_sets WHERE chat_id = ?",
            (chat_id,)
        )
        return result is not None and result > 0
    
    # --- Censored Words ---
    @staticmethod
    def add_censored_word(chat_id: str, word: str, is_strict: bool = False) -> bool:
        """Add a censored word."""
        result = execute_query(
            "INSERT OR REPLACE INTO censored_words (chat_id, word, is_strict) VALUES (?, ?, ?)",
            (chat_id, word, 1 if is_strict else 0)
        )
        return result is not None and result > 0
    
    @staticmethod
    def remove_censored_word(chat_id: str, word: str) -> bool:
        """Remove a censored word."""
        result = execute_query(
            "DELETE FROM censored_words WHERE chat_id = ? AND word = ?",
            (chat_id, word)
        )
        return result is not None and result > 0
    
    @staticmethod
    def get_censored_words(chat_id: str) -> List[Tuple[str, bool]]:
        """Get all censored words for a chat."""
        result = execute_query(
            "SELECT word, is_strict FROM censored_words WHERE chat_id = ?",
            (chat_id,),
            fetch_all=True
        )
        return [(row[0], bool(row[1])) for row in result] if result else []
    
    @staticmethod
    def clear_all_censored_words(chat_id: str) -> bool:
        """Remove all censored words for a chat."""
        result = execute_query(
            "DELETE FROM censored_words WHERE chat_id = ?",
            (chat_id,)
        )
        return result is not None and result > 0
    
    # --- Settings ---
    @staticmethod
    def set_admin_bypass(chat_id: str, enabled: bool) -> bool:
        """Set admin bypass setting."""
        result = execute_query(
            "INSERT OR REPLACE INTO admin_perms (chat_id, admins_allowed) VALUES (?, ?)",
            (chat_id, 1 if enabled else 0)
        )
        return result is not None
    
    @staticmethod
    def is_admin_bypass_enabled(chat_id: str) -> bool:
        """Check if admin bypass is enabled."""
        result = execute_query(
            "SELECT admins_allowed FROM admin_perms WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        return result[0] == 1 if result else True
    
    @staticmethod
    def set_antispam(chat_id: str, enabled: bool) -> bool:
        """Set antispam setting."""
        result = execute_query(
            "INSERT OR REPLACE INTO chat_settings (chat_id, antispam_enabled) VALUES (?, ?)",
            (chat_id, 1 if enabled else 0)
        )
        return result is not None
    
    @staticmethod
    def is_antispam_enabled(chat_id: str) -> bool:
        """Check if antispam is enabled."""
        result = execute_query(
            "SELECT antispam_enabled FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        return result[0] == 1 if result else False