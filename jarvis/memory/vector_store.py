"""ChromaDB vector store for semantic memory."""
import logging
import os
from datetime import datetime
from typing import Optional
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class VectorMemory:
    def __init__(self, db_path: str = "./data/chroma"):
        os.makedirs(db_path, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False)
        )
        self.conversations = self.client.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"}
        )
        self.knowledge = self.client.get_or_create_collection(
            name="knowledge",
            metadata={"hnsw:space": "cosine"}
        )
        self.notes = self.client.get_or_create_collection(
            name="notes",
            metadata={"hnsw:space": "cosine"}
        )

    def add_conversation(self, user_msg: str, assistant_msg: str,
                         embedding: list[float], session_id: str = "default"):
        doc_id = f"conv_{datetime.now().timestamp()}"
        combined = f"User: {user_msg}\nJarvis: {assistant_msg}"
        self.conversations.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[combined],
            metadatas=[{
                "timestamp": datetime.now().isoformat(),
                "session": session_id,
                "user_msg": user_msg[:500],
                "assistant_msg": assistant_msg[:500]
            }]
        )

    def search_conversations(self, query_embedding: list[float],
                              n_results: int = 5) -> list[dict]:
        try:
            results = self.conversations.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, self.conversations.count())
            )
            if not results["documents"][0]:
                return []
            items = []
            for i, doc in enumerate(results["documents"][0]):
                items.append({
                    "text": doc,
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i]
                })
            return items
        except Exception:
            return []

    def add_knowledge(self, fact: str, embedding: list[float],
                      category: str = "general", source: str = "learned"):
        doc_id = f"know_{datetime.now().timestamp()}"
        self.knowledge.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[fact],
            metadatas=[{
                "timestamp": datetime.now().isoformat(),
                "category": category,
                "source": source,
                "reinforced": 1
            }]
        )

    def search_knowledge(self, query_embedding: list[float],
                          n_results: int = 5) -> list[dict]:
        try:
            count = self.knowledge.count()
            if count == 0:
                return []
            results = self.knowledge.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, count)
            )
            if not results["documents"][0]:
                return []
            items = []
            for i, doc in enumerate(results["documents"][0]):
                items.append({
                    "fact": doc,
                    "metadata": results["metadatas"][0][i],
                    "relevance": 1 - results["distances"][0][i]
                })
            return items
        except Exception:
            return []

    def reinforce_knowledge(self, doc_id: str):
        """Increase reinforcement counter for a fact (spaced repetition)."""
        try:
            result = self.knowledge.get(ids=[doc_id])
            if result["metadatas"]:
                meta = result["metadatas"][0]
                meta["reinforced"] = meta.get("reinforced", 1) + 1
                self.knowledge.update(ids=[doc_id], metadatas=[meta])
        except Exception:
            pass

    def add_note(self, title: str, content: str, embedding: list[float],
                 tags: list[str] = None):
        doc_id = f"note_{datetime.now().timestamp()}"
        self.notes.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[f"{title}\n{content}"],
            metadatas=[{
                "title": title,
                "timestamp": datetime.now().isoformat(),
                "tags": ",".join(tags or [])
            }]
        )
        return doc_id

    def search_notes(self, query_embedding: list[float],
                     n_results: int = 5) -> list[dict]:
        try:
            count = self.notes.count()
            if count == 0:
                return []
            results = self.notes.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, count)
            )
            items = []
            for i, doc in enumerate(results["documents"][0]):
                items.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i]
                })
            return items
        except Exception:
            return []

    def stats(self) -> dict:
        return {
            "conversations": self.conversations.count(),
            "knowledge_facts": self.knowledge.count(),
            "notes": self.notes.count()
        }
