"""Auto-learning system: extracts facts, preferences and knowledge from conversations."""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """Analysiere das folgende Gespräch und extrahiere wichtige Fakten, die du dir merken solltest.

Gespräch:
{conversation}

Extrahiere:
1. Fakten über den User (Name, Beruf, Vorlieben, etc.)
2. Wichtige Informationen die im Gespräch gelernt wurden
3. Präferenzen und Einstellungen des Users

Antworte NUR mit einem JSON-Array in diesem Format:
[
  {{"fact": "Der User heißt Max", "category": "user_profile"}},
  {{"fact": "Der User programmiert in Python", "category": "user_skills"}},
  {{"fact": "Der User mag keine langen Erklärungen", "category": "preferences"}}
]

Wenn keine interessanten Fakten vorhanden: []"""

SUMMARIZE_PROMPT = """Erstelle eine kurze Zusammenfassung dieses Gesprächs in 2-3 Sätzen.
Fokus auf: Was wurde besprochen? Was wurde erreicht? Wichtige Fakten.

Gespräch:
{conversation}

Zusammenfassung:"""


class Learner:
    def __init__(self, llm, episodic_memory, vector_memory):
        self.llm = llm
        self.episodic = episodic_memory
        self.vector = vector_memory
        self.interaction_count = 0
        self.learn_interval = 5  # Lerne alle 5 Interaktionen

    async def maybe_learn(self, session_id: str):
        """Triggered periodically to extract knowledge."""
        self.interaction_count += 1
        if self.interaction_count % self.learn_interval == 0:
            await self.extract_and_store(session_id)

    async def extract_and_store(self, session_id: str):
        """Extract facts from recent conversation and store them."""
        try:
            history = self.episodic.get_history(session_id, limit=10)
            if len(history) < 4:
                return

            conversation = "\n".join([
                f"{m['role'].upper()}: {m['content']}"
                for m in history[-10:]
            ])

            prompt = EXTRACT_PROMPT.format(conversation=conversation)
            response = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.llm.default_model
            )

            facts = self._parse_facts(response)
            stored = 0
            for item in facts:
                fact = item.get("fact", "")
                category = item.get("category", "general")
                if fact and len(fact) > 10:
                    self.episodic.save_fact(fact, category)
                    embedding = await self.llm.embed(fact)
                    if embedding:
                        self.vector.add_knowledge(fact, embedding, category, "auto_extracted")
                    stored += 1

                    # Update user profile for profile facts
                    if category == "user_profile":
                        key = self._extract_profile_key(fact)
                        if key:
                            self.episodic.update_profile(key, fact)

            if stored > 0:
                logger.info(f"Learned {stored} new facts from conversation")

        except Exception as e:
            logger.error(f"Learning error: {e}")

    async def summarize_session(self, session_id: str) -> str:
        """Generate a summary of the current session."""
        try:
            history = self.episodic.get_history(session_id, limit=20)
            if not history:
                return ""
            conversation = "\n".join([
                f"{m['role'].upper()}: {m['content'][:300]}"
                for m in history
            ])
            prompt = SUMMARIZE_PROMPT.format(conversation=conversation)
            summary = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.llm.default_model
            )
            self.episodic.save_summary(session_id, summary)
            return summary
        except Exception as e:
            logger.error(f"Summarization error: {e}")
            return ""

    def _parse_facts(self, response: str) -> list[dict]:
        """Parse JSON facts from LLM response."""
        try:
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                import json
                return json.loads(match.group())
        except Exception:
            pass
        return []

    def _extract_profile_key(self, fact: str) -> Optional[str]:
        """Extract a profile key from a fact string."""
        fact_lower = fact.lower()
        if "name" in fact_lower or "heißt" in fact_lower:
            return "name"
        if "beruf" in fact_lower or "arbeitet" in fact_lower or "job" in fact_lower:
            return "job"
        if "mag" in fact_lower or "liebt" in fact_lower or "vorliebe" in fact_lower:
            return "preference"
        if "programmier" in fact_lower or "sprache" in fact_lower:
            return "skills"
        return None
