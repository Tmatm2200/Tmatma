"""
Database operations for the bot.
Centralized database access with proper error handling.
"""
import aiosqlite
import logging
from typing import Optional, List, Tuple, Any
from contextlib import asynccontextmanager
from config import DB_PATH

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_db_connection():
    """Async context manager for database connections with proper cleanup."""
    conn = None
    try:
        conn = await aiosqlite.connect(DB_PATH, timeout=30)
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA synchronous=NORMAL;")
        yield conn
        await conn.commit()
    except Exception as e:
        if conn:
            await conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            await conn.close()


async def execute_query(
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
    import time
    query_start = time.time()
    try:
        async with get_db_connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute(query, params)

            if fetch_one:
                result = await cursor.fetchone()
            elif fetch_all:
                result = await cursor.fetchall()
            else:
                result = cursor.rowcount
        logger.debug(f"DB query took {time.time() - query_start:.3f}s: {query[:50]}...")
        return result
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        return None


class Database:
    """Database interface for bot operations."""
    
    @staticmethod
    async def init_tables() -> None:
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
                antispam_enabled INTEGER DEFAULT 0,
                spam_limit INTEGER DEFAULT 6,
                mute_penalty INTEGER DEFAULT 15
            )"""
        ]
        
        for query in queries:
            await execute_query(query)

        # Migration for new columns
        migration_queries = [
            "ALTER TABLE chat_settings ADD COLUMN ai_enabled INTEGER DEFAULT 0",
            "ALTER TABLE chat_settings ADD COLUMN ai_threshold REAL DEFAULT 60.0"
        ]
        for query in migration_queries:
            try:
                await execute_query(query)
            except Exception as e:
                logger.debug(f"Migration query failed (column may exist): {e}")

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
    async def is_set_blocked(chat_id: str, set_name: str) -> bool:
        """Check if a sticker set is blocked."""
        result = await execute_query(
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
    async def get_censored_words(chat_id: str) -> List[Tuple[str, bool]]:
        """Get all censored words for a chat."""
        result = await execute_query(
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
    async def is_admin_bypass_enabled(chat_id: str) -> bool:
        """Check if admin bypass is enabled."""
        result = await execute_query(
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
    async def is_antispam_enabled(chat_id: str) -> bool:
        """Check if antispam is enabled."""
        result = await execute_query(
            "SELECT antispam_enabled FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        return result[0] == 1 if result else False

    @staticmethod
    async def get_spam_limit(chat_id: str) -> int:
        """Get spam limit for a chat."""
        result = await execute_query(
            "SELECT spam_limit FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        return result[0] if result else 6

    @staticmethod
    def set_spam_limit(chat_id: str, limit: int) -> bool:
        """Set spam limit for a chat."""
        result = execute_query(
            "INSERT OR REPLACE INTO chat_settings (chat_id, spam_limit) VALUES (?, ?)",
            (chat_id, limit)
        )
        return result is not None

    @staticmethod
    async def get_mute_penalty(chat_id: str) -> int:
        """Get mute penalty minutes for a chat."""
        result = await execute_query(
            "SELECT mute_penalty FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        return result[0] if result else 15

    @staticmethod
    def set_mute_penalty(chat_id: str, penalty: int) -> bool:
        """Set mute penalty minutes for a chat."""
        result = execute_query(
            "INSERT OR REPLACE INTO chat_settings (chat_id, mute_penalty) VALUES (?, ?)",
            (chat_id, penalty)
        )
        return result is not None

    @staticmethod
    def set_ai_moderation(chat_id: str, enabled: bool) -> bool:
        """Set AI moderation enabled/disabled."""
        result = execute_query(
            "INSERT OR REPLACE INTO chat_settings (chat_id, ai_enabled) VALUES (?, ?)",
            (chat_id, 1 if enabled else 0)
        )
        return result is not None

    @staticmethod
    async def is_ai_moderation_enabled(chat_id: str) -> bool:
        """Check if AI moderation is enabled."""
        result = await execute_query(
            "SELECT ai_enabled FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        return result[0] == 1 if result else False

    @staticmethod
    async def get_ai_threshold(chat_id: str) -> float:
        """Get AI threshold for bad detection."""
        result = await execute_query(
            "SELECT ai_threshold FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
            fetch_one=True
        )
        return result[0] if result else 75.0

    @staticmethod
    def set_ai_threshold(chat_id: str, threshold: float) -> bool:
        """Set AI threshold."""
        result = execute_query(
            "INSERT OR REPLACE INTO chat_settings (chat_id, ai_threshold) VALUES (?, ?)",
            (chat_id, threshold)
        )
        return result is not None