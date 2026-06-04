"""Episodic (conversation) memory with SQLite persistence."""
import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class EpisodicMemory:
    def __init__(self, db_path: str = "./data/memory.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                tokens INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                last_active TEXT NOT NULL,
                summary TEXT,
                message_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS learned_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                source TEXT DEFAULT 'conversation',
                confidence REAL DEFAULT 0.8,
                reinforced INTEGER DEFAULT 1,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_profile (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conv_session
                ON conversations(session_id);
            CREATE INDEX IF NOT EXISTS idx_facts_category
                ON learned_facts(category);
        """)
        conn.commit()
        conn.close()

    def create_session(self, session_id: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("""
            INSERT OR IGNORE INTO sessions (id, created_at, last_active)
            VALUES (?, ?, ?)
        """, (session_id, now, now))
        conn.commit()
        conn.close()

    def add_message(self, session_id: str, role: str, content: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now = datetime.now().isoformat()
        tokens = len(content.split())
        c.execute("""
            INSERT INTO conversations (session_id, role, content, timestamp, tokens)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, role, content, now, tokens))
        c.execute("""
            UPDATE sessions SET last_active = ?, message_count = message_count + 1
            WHERE id = ?
        """, (now, session_id))
        conn.commit()
        conn.close()

    def get_history(self, session_id: str, limit: int = 50) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT role, content, timestamp FROM conversations
            WHERE session_id = ?
            ORDER BY id DESC LIMIT ?
        """, (session_id, limit))
        rows = c.fetchall()
        conn.close()
        messages = [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]
        return messages

    def get_recent_messages(self, session_id: str, n: int = 10) -> list[dict]:
        msgs = self.get_history(session_id, limit=n)
        return [{"role": m["role"], "content": m["content"]} for m in msgs]

    def save_summary(self, session_id: str, summary: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE sessions SET summary = ? WHERE id = ?", (summary, session_id))
        conn.commit()
        conn.close()

    def get_session_summary(self, session_id: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT summary FROM sessions WHERE id = ?", (session_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row and row[0] else None

    def save_fact(self, fact: str, category: str = "general",
                  source: str = "conversation", confidence: float = 0.8):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO learned_facts (fact, category, source, confidence, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (fact, category, source, confidence, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_facts(self, category: Optional[str] = None, limit: int = 50) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if category:
            c.execute("""
                SELECT fact, category, confidence, reinforced, timestamp
                FROM learned_facts WHERE category = ?
                ORDER BY reinforced DESC, timestamp DESC LIMIT ?
            """, (category, limit))
        else:
            c.execute("""
                SELECT fact, category, confidence, reinforced, timestamp
                FROM learned_facts
                ORDER BY reinforced DESC, timestamp DESC LIMIT ?
            """, (limit,))
        rows = c.fetchall()
        conn.close()
        return [{"fact": r[0], "category": r[1], "confidence": r[2],
                 "reinforced": r[3], "timestamp": r[4]} for r in rows]

    def update_profile(self, key: str, value: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO user_profile (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, value, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_profile(self) -> dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT key, value FROM user_profile")
        rows = c.fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}

    def get_stats(self) -> dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM conversations")
        total_msgs = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM learned_facts")
        total_facts = c.fetchone()[0]
        conn.close()
        return {
            "total_messages": total_msgs,
            "total_sessions": total_sessions,
            "learned_facts": total_facts
        }
