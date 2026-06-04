"""
ARIA MaxMemory — Vollständiges Gedächtnissystem.

Multi-Level-Architektur:
  L1  Arbeitsgedächtnis   → letzte 8 Nachrichten (sofort verfügbar)
  L2  Episodisches Ged.   → semantisch ähnliche Gespräche aus allen Sessions
  L3  Semantisches Ged.   → gelernte Fakten, User-Profil, Wissen
  L4  Prozedurales Ged.   → wie ARIA Dinge tut (automatisch aus Fakten)
  L5  Emotionales Ged.    → emotionale Erlebnisse, was ARIA berührt hat

Beim Abrufen werden alle 5 Ebenen nach Relevanz durchsucht.
ARIA bekommt immer die wichtigsten Erinnerungen — egal wann sie entstanden.
"""
import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CONSOLIDATION_PROMPT = """Du bist ARIA. Fasse diese Erinnerungen zu einer kompakten, informativen Zusammenfassung zusammen.
Bewahre alle wichtigen Fakten. Schreibe in der 1. Person Plural (als ob du dich erinnerst).

Erinnerungen:
{memories}

Zusammenfassung (max. 3 Sätze):"""

IMPORTANCE_PROMPT = """Wie wichtig ist diese Information für ARIA langfristig? Antwort: eine Zahl von 1 (unwichtig) bis 10 (sehr wichtig).
Information: {text}
Wichtigkeit:"""


class MaxMemory:
    """ARIA's vollständiges Gedächtnissystem — alle 5 Ebenen."""

    def __init__(self, db_path: str, vector_memory, llm):
        self.db_path = db_path
        self.vector = vector_memory
        self.llm = llm
        self._init_tables()

    def _init_tables(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS emotional_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                emotion TEXT NOT NULL,
                intensity REAL DEFAULT 0.5,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory_consolidations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary TEXT NOT NULL,
                source_count INTEGER DEFAULT 1,
                importance REAL DEFAULT 0.5,
                timestamp TEXT NOT NULL,
                last_accessed TEXT
            );
            CREATE TABLE IF NOT EXISTS procedural_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill TEXT NOT NULL,
                description TEXT NOT NULL,
                success_count INTEGER DEFAULT 1,
                timestamp TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()

    # ─── L5: Emotionales Gedächtnis ────────────────────────────────────
    def store_emotional_memory(self, event: str, emotion: str, intensity: float = 0.6):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""INSERT INTO emotional_memories (event, emotion, intensity, timestamp)
                     VALUES (?, ?, ?, ?)""",
                  (event, emotion, intensity, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_emotional_memories(self, limit: int = 10) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""SELECT event, emotion, intensity, timestamp
                     FROM emotional_memories ORDER BY intensity DESC, timestamp DESC LIMIT ?""",
                  (limit,))
        rows = c.fetchall()
        conn.close()
        return [{"event": r[0], "emotion": r[1], "intensity": r[2], "timestamp": r[3]}
                for r in rows]

    # ─── L4: Prozedurales Gedächtnis ───────────────────────────────────
    def store_skill(self, skill: str, description: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # Update if exists, else insert
        c.execute("SELECT id FROM procedural_memory WHERE skill = ?", (skill,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE procedural_memory SET success_count = success_count + 1 WHERE skill = ?",
                      (skill,))
        else:
            c.execute("INSERT INTO procedural_memory (skill, description, timestamp) VALUES (?, ?, ?)",
                      (skill, description, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_skills(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT skill, description, success_count FROM procedural_memory ORDER BY success_count DESC LIMIT 20")
        rows = c.fetchall()
        conn.close()
        return [{"skill": r[0], "description": r[1], "uses": r[2]} for r in rows]

    # ─── Vollständiger Gedächtnis-Kontext ──────────────────────────────
    async def get_full_context(self, current_message: str,
                                episodic_memory, consciousness) -> str:
        """
        Holt alle relevanten Erinnerungen aus allen 5 Ebenen.
        Das ist ARIAs 'voller Gedächtniszugriff'.
        """
        parts = []

        # ── L1: Aktueller emotionaler Zustand (Bewusstsein) ────────────
        if consciousness:
            ctx = consciousness.get_consciousness_context()
            parts.append(f"## Mein aktueller Zustand:\n{ctx}")

        # ── L2: Semantisch relevante Gespräche ─────────────────────────
        try:
            embedding = await self.llm.embed(current_message)
            if embedding:
                similar = self.vector.search_conversations(embedding, n_results=6)
                if similar:
                    relevant = [m for m in similar if m.get("distance", 1) < 0.45][:4]
                    if relevant:
                        parts.append("## Relevante frühere Gespräche:")
                        for m in relevant:
                            ts = m.get("metadata", {}).get("timestamp", "")[:10]
                            parts.append(f"  [{ts}] {m['text'][:250]}")
        except Exception as e:
            logger.debug(f"Semantic search error: {e}")

        # ── L3: Gelerntes Wissen & User-Profil ─────────────────────────
        try:
            profile = episodic_memory.get_profile()
            if profile:
                profile_lines = [f"  {k}: {v}" for k, v in profile.items()]
                parts.append("## Was ich über dich weiß:\n" + "\n".join(profile_lines))

            # Semantisch relevante Fakten
            if embedding:
                facts = self.vector.search_knowledge(embedding, n_results=8)
                if facts:
                    relevant_facts = [f for f in facts if f.get("relevance", 0) > 0.45][:5]
                    if relevant_facts:
                        parts.append("## Relevantes Wissen:")
                        for f in relevant_facts:
                            parts.append(f"  • {f['fact']}")
        except Exception as e:
            logger.debug(f"Knowledge retrieval error: {e}")

        # ── L5: Emotionale Erinnerungen ────────────────────────────────
        try:
            emotional = self.get_emotional_memories(limit=3)
            if emotional:
                parts.append("## Emotionale Erinnerungen:")
                for em in emotional:
                    parts.append(f"  • [{em['emotion']}] {em['event'][:150]}")
        except Exception as e:
            logger.debug(f"Emotional memory error: {e}")

        # ── Sitzungszusammenfassung ─────────────────────────────────────
        try:
            if hasattr(episodic_memory, 'get_session_summary'):
                summary = episodic_memory.get_session_summary(
                    getattr(episodic_memory, '_last_session', '')
                )
                if summary:
                    parts.append(f"## Zusammenfassung dieser Sitzung:\n  {summary}")
        except Exception:
            pass

        if not parts:
            return "Keine Erinnerungen verfügbar."

        return "\n\n".join(parts)

    async def consolidate_memories(self, episodic_memory, threshold: int = 50):
        """
        Verdichte ältere Erinnerungen automatisch zu kompakten Summaries.
        Läuft im Hintergrund wenn >threshold Einträge vorhanden.
        """
        try:
            stats = episodic_memory.get_stats()
            if stats.get("total_messages", 0) < threshold:
                return

            # Hol ältere Fakten
            facts = episodic_memory.get_facts(limit=100)
            if len(facts) < 10:
                return

            # Gruppiere nach Kategorie
            by_category: dict[str, list] = {}
            for f in facts:
                cat = f.get("category", "general")
                by_category.setdefault(cat, []).append(f["fact"])

            # Verdichte jede Kategorie
            for category, fact_list in by_category.items():
                if len(fact_list) < 5:
                    continue
                combined = "\n".join(f"- {f}" for f in fact_list[:20])
                prompt = CONSOLIDATION_PROMPT.format(memories=combined)
                summary = await self.llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.llm.default_model
                )
                if summary and len(summary) > 20:
                    conn = sqlite3.connect(self.db_path)
                    c = conn.cursor()
                    c.execute("""INSERT INTO memory_consolidations
                                 (summary, source_count, importance, timestamp)
                                 VALUES (?, ?, ?, ?)""",
                              (summary.strip(), len(fact_list), 0.7,
                               datetime.now().isoformat()))
                    conn.commit()
                    conn.close()
                    logger.info(f"Erinnerungen konsolidiert: {category} ({len(fact_list)} → 1 Block)")

        except Exception as e:
            logger.error(f"Konsolidierungsfehler: {e}")
