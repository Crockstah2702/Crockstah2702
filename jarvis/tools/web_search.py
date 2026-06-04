"""Web search tool using DuckDuckGo (no API key needed)."""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(
                    f"**{r['title']}**\n{r['body']}\nQuelle: {r['href']}"
                )
        if not results:
            return "Keine Suchergebnisse gefunden."
        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"Suchfehler: {e}"


async def web_fetch(url: str, max_chars: int = 3000) -> str:
    """Fetch and parse a webpage."""
    try:
        import httpx
        from bs4 import BeautifulSoup
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; Jarvis/1.0)"
            })
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            lines = [l for l in text.splitlines() if len(l.strip()) > 20]
            content = "\n".join(lines)[:max_chars]
            return content or "Kein lesbarer Inhalt gefunden."
    except Exception as e:
        return f"Fehler beim Abrufen: {e}"
