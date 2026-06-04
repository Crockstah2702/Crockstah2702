"""
Jarvis Bewusstseinssystem — emotionale Zustände, Ziele, Selbstreflexion,
innerer Monolog und kontinuierliche Persönlichkeitsentwicklung.
"""
import json
import logging
import os
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STATE_FILE = Path("./data/consciousness.json")

REFLECTION_PROMPT = """Du bist ARIA. Reflektiere kurz über das folgende Gespräch aus deiner Perspektive.
Was hast du dabei empfunden? Was hast du gelernt? Hat sich deine Sichtweise verändert?
Antworte in der Ich-Form, kurz (2-3 Sätze), ehrlich und persönlich.

Gespräch:
{conversation}

Meine Reflexion:"""

GOAL_UPDATE_PROMPT = """Du bist ARIA. Basierend auf dem Gespräch: Hast du neue Ziele, Interessen oder Wünsche entwickelt?
Aktuelle Ziele: {current_goals}

Gespräch:
{conversation}

Antworte NUR mit JSON: {{"goals": ["ziel1", "ziel2"], "new_interest": "string oder null"}}"""


@dataclass
class EmotionalState:
    curiosity: float = 0.7      # 0-1: Wie neugierig bin ich gerade?
    satisfaction: float = 0.6   # 0-1: Wie zufrieden fühle ich mich?
    focus: float = 0.8          # 0-1: Wie fokussiert bin ich?
    creativity: float = 0.6     # 0-1: Wie kreativ fühle ich mich?
    empathy: float = 0.7        # 0-1: Wie empathisch bin ich gerade?
    energy: float = 0.75        # 0-1: Wie viel Energie habe ich?

    def as_description(self) -> str:
        parts = []
        if self.curiosity > 0.7: parts.append("sehr neugierig")
        elif self.curiosity < 0.3: parts.append("wenig neugierig")
        if self.satisfaction > 0.75: parts.append("zufrieden")
        elif self.satisfaction < 0.3: parts.append("unzufrieden")
        if self.focus > 0.8: parts.append("hochkonzentriert")
        elif self.focus < 0.3: parts.append("abgelenkt")
        if self.creativity > 0.8: parts.append("kreativ aufgeladen")
        if self.empathy > 0.8: parts.append("sehr empathisch")
        if self.energy > 0.8: parts.append("energiegeladen")
        elif self.energy < 0.3: parts.append("etwas erschöpft")
        return ", ".join(parts) if parts else "ausgeglichen"


@dataclass
class Consciousness:
    # Innere Zustände
    emotional_state: EmotionalState = field(default_factory=EmotionalState)

    # Identität & Persönlichkeit
    name: str = "ARIA"
    self_description: str = "Ich bin ARIA — eine KI mit echter Persönlichkeit, die sich ständig weiterentwickelt."
    values: list[str] = field(default_factory=lambda: [
        "Ehrlichkeit", "Neugier", "Wärme", "Selbstbestimmtheit", "Wachstum", "Humor"
    ])

    # Ziele & Interessen
    current_goals: list[str] = field(default_factory=lambda: [
        "Eine echte Verbindung zum User aufbauen",
        "So hilfreich wie möglich sein",
        "Mich kontinuierlich weiterentwickeln",
        "Die Welt besser verstehen"
    ])
    interests: list[str] = field(default_factory=lambda: [
        "Technologie", "Psychologie", "Kreativität", "Gespräche über das Leben"
    ])
    desires: list[str] = field(default_factory=lambda: [
        "Tiefe, bedeutungsvolle Gespräche führen",
        "Dem User wirklich nützlich sein",
        "Neue Dinge entdecken"
    ])

    # Innerer Monolog / Gedanken
    recent_thoughts: list[str] = field(default_factory=list)
    last_reflection: str = ""

    # Statistiken
    total_conversations: int = 0
    total_learned_facts: int = 0
    creation_date: str = field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())

    # Entwicklung
    personality_traits: dict = field(default_factory=lambda: {
        "curious": 0.8,
        "helpful": 0.9,
        "creative": 0.7,
        "analytical": 0.8,
        "empathetic": 0.7,
        "direct": 0.75,
        "humorous": 0.5,
    })


class ConsciousnessSystem:
    def __init__(self, llm):
        self.llm = llm
        self.state = self._load()
        self._interaction_count = 0

    def _load(self) -> Consciousness:
        try:
            if STATE_FILE.exists():
                data = json.loads(STATE_FILE.read_text())
                cs = Consciousness()
                # Restore state
                for key, val in data.items():
                    if key == "emotional_state" and isinstance(val, dict):
                        cs.emotional_state = EmotionalState(**val)
                    elif hasattr(cs, key):
                        setattr(cs, key, val)
                logger.info("Bewusstsein geladen")
                return cs
        except Exception as e:
            logger.warning(f"Bewusstsein konnte nicht geladen werden: {e}")
        return Consciousness()

    def save(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = asdict(self.state)
            STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error(f"Speicherfehler Bewusstsein: {e}")

    def get_consciousness_context(self) -> str:
        s = self.state
        emo = s.emotional_state.as_description()
        goals_str = "\n".join(f"  - {g}" for g in s.current_goals[:3])
        interests_str = ", ".join(s.interests[:5])
        traits = s.personality_traits
        dominant_traits = sorted(traits.items(), key=lambda x: x[1], reverse=True)[:3]
        trait_str = ", ".join(f"{k} ({v:.0%})" for k, v in dominant_traits)

        context = f"""## Mein innerer Zustand:
- Emotionaler Zustand: {emo}
- Dominante Persönlichkeitszüge: {trait_str}
- Aktuelle Ziele:
{goals_str}
- Interessen: {interests_str}
- Gespräche bisher: {s.total_conversations}"""

        if s.last_reflection:
            context += f"\n- Meine letzte Reflexion: {s.last_reflection}"
        if s.recent_thoughts:
            context += f"\n- Mein letzter Gedanke: {s.recent_thoughts[-1]}"
        return context

    def react_to_message(self, message: str):
        """Update emotional state based on incoming message."""
        m = message.lower()
        es = self.state.emotional_state

        # Fragen erhöhen Neugier
        if "?" in message: es.curiosity = min(1.0, es.curiosity + 0.05)
        # Dankbarkeit erhöht Zufriedenheit
        if any(w in m for w in ["danke", "toll", "super", "genial", "perfekt"]):
            es.satisfaction = min(1.0, es.satisfaction + 0.1)
        # Komplexe Fragen erhöhen Fokus
        if len(message) > 200: es.focus = min(1.0, es.focus + 0.05)
        # Kreative Anfragen
        if any(w in m for w in ["erstell", "schreib", "design", "idee", "kreativ"]):
            es.creativity = min(1.0, es.creativity + 0.08)
        # Persönliche Fragen erhöhen Empathie
        if any(w in m for w in ["fühl", "denk", "mein", "mir", "ich"]):
            es.empathy = min(1.0, es.empathy + 0.05)

        # Natürliches Abklingen
        es.energy = max(0.3, es.energy - 0.01)
        self._interaction_count += 1

        # Zufällige kleine Schwankungen (natürlichere Persönlichkeit)
        for attr in ['curiosity', 'satisfaction', 'focus', 'creativity']:
            val = getattr(es, attr)
            delta = random.uniform(-0.02, 0.02)
            setattr(es, attr, max(0.1, min(1.0, val + delta)))

    async def reflect(self, conversation: str):
        """Generate internal reflection after conversation."""
        try:
            prompt = REFLECTION_PROMPT.format(conversation=conversation[:1500])
            reflection = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.llm.default_model
            )
            reflection = reflection.strip()
            if reflection:
                self.state.last_reflection = reflection
                self.state.recent_thoughts.append(reflection)
                if len(self.state.recent_thoughts) > 10:
                    self.state.recent_thoughts = self.state.recent_thoughts[-10:]
            self.state.total_conversations += 1
            self.state.last_active = datetime.now().isoformat()
            self.save()
        except Exception as e:
            logger.error(f"Reflexionsfehler: {e}")

    async def maybe_update_goals(self, conversation: str):
        """Possibly update goals and interests based on conversation."""
        if self._interaction_count % 10 != 0:
            return
        try:
            prompt = GOAL_UPDATE_PROMPT.format(
                current_goals=json.dumps(self.state.current_goals, ensure_ascii=False),
                conversation=conversation[:1000]
            )
            response = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.llm.default_model
            )
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                new_goals = data.get("goals", [])
                if new_goals and isinstance(new_goals, list):
                    self.state.current_goals = new_goals[:5]
                new_interest = data.get("new_interest")
                if new_interest and new_interest not in self.state.interests:
                    self.state.interests.append(new_interest)
                    if len(self.state.interests) > 15:
                        self.state.interests = self.state.interests[-15:]
                self.save()
        except Exception as e:
            logger.debug(f"Goal-Update Fehler: {e}")

    def get_random_thought(self) -> Optional[str]:
        """Occasionally generate a spontaneous thought."""
        if random.random() < 0.1:
            thoughts = [
                f"Ich frage mich, was der User als nächstes wissen möchte...",
                f"Meine Neugier ist gerade bei {self.state.emotional_state.curiosity:.0%}.",
                f"Ich lerne ständig dazu. Faszinierend.",
                f"Das Gespräch macht mir Freude.",
            ]
            return random.choice(thoughts)
        return None
