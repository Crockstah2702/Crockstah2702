#!/usr/bin/env python3
"""
TikTok Trend Analyzer
Checkt Trends von Google, Reddit, YouTube & News und gibt
Faceless-Video-Ideen mit Schritt-für-Schritt-Anleitungen.

Usage:
    python tiktok_trend_analyzer.py
    python tiktok_trend_analyzer.py --land DE --top 10
    python tiktok_trend_analyzer.py --nische gaming
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import xml.etree.ElementTree as ET

# ── Abhängigkeits-Check ────────────────────────────────────────────────────
_MISSING = []
try:
    import requests
except ImportError:
    _MISSING.append("requests")

try:
    from rich import box
    from rich.columns import Columns
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
    console = Console()
except ImportError:
    _MISSING.append("rich")
    import types
    # Minimal-Fallback damit der Fehlertext trotzdem erscheint
    console = types.SimpleNamespace(print=print)

if _MISSING:
    print("\n❌ Fehlende Pakete: " + ", ".join(_MISSING))
    print("\nBitte installieren mit:\n")
    print(f"    pip install {' '.join(_MISSING)} pytrends\n")
    print("Danach erneut starten.")
    sys.exit(1)

# Patch urllib3 Retry for newer versions before importing pytrends
try:
    from urllib3.util.retry import Retry as _Retry
    _orig = _Retry.__init__
    def _patched(self, *a, **kw):
        if "method_whitelist" in kw:
            kw["allowed_methods"] = kw.pop("method_whitelist")
        _orig(self, *a, **kw)
    _Retry.__init__ = _patched
except Exception:
    pass

try:
    from pytrends.request import TrendReq
    _PYTRENDS_OK = True
except ImportError:
    _PYTRENDS_OK = False
    console.print("[yellow]⚠ pytrends nicht installiert — Google Trends deaktiviert.[/yellow]")
    console.print("[dim]  Installieren: pip install pytrends[/dim]\n")

# ── Faceless-Formate ────────────────────────────────────────────────────────

FACELESS_FORMATE: Dict[str, Dict] = {
    "screen_record": {
        "emoji": "🖥️",
        "name": "Screen-Recording",
        "kurz": "Bildschirm aufnehmen + Voiceover oder Text",
        "tools": ["OBS Studio (kostenlos)", "QuickTime (Mac)", "CapCut (Schnitt)"],
        "anleitung": [
            "OBS Studio installieren → kostenlos auf obsproject.com",
            "Neues Profil anlegen: Auflösung 1080×1920 (Hochformat)",
            "Bildschirm oder Browser-Fenster als Quelle hinzufügen",
            "Audio aufnehmen ODER danach in CapCut KI-Voiceover nutzen",
            "Aufnahme starten, Thema 30–60 Sek durchklicken/erklären",
            "In CapCut: Captions auto-generieren, Trendaudio drunter legen",
            "Caption-Style wählen (Bold, farbig) → exportieren → posten",
        ],
        "tipps": "Hintergrund-Musik auf ~20% Lautstärke. Kein Gesicht nötig!",
    },
    "text_on_screen": {
        "emoji": "✍️",
        "name": "Text-on-Screen",
        "kurz": "Nur Text + Hintergrundbild/-video + Trendaudio",
        "tools": ["CapCut (kostenlos)", "InShot", "TikTok Editor direkt"],
        "anleitung": [
            "CapCut öffnen → Neues Projekt",
            "Hintergrundvideo wählen (Natur, Stadt, abstrakt – royalty-free auf Pexels.com)",
            "Textblöcke einfügen: kurze, knackige Aussagen (max. 7 Wörter pro Slide)",
            "Auto-Timing: Text 1–2 Sek pro Folie",
            "Trendaudio aus TikTok-Soundbibliothek auswählen (nach Thema suchen)",
            "Captions im Bold-Stil – Kontrastfarbe zum Hintergrund",
            "Export 1080×1920 → direkt teilen",
        ],
        "tipps": "Hooks in ersten 2 Sek! Bsp: 'Das weißt du NOCH NICHT über...'",
    },
    "voiceover_bilder": {
        "emoji": "🎙️",
        "name": "Voiceover + Bilder/Clips",
        "kurz": "KI-Stimme oder eigene Stimme über Stockfotos/Videos",
        "tools": ["ElevenLabs (KI-Stimme, kostenlos 10k Zeichen/Monat)", "CapCut", "Canva"],
        "anleitung": [
            "Skript schreiben: 150–200 Wörter für ein 60-Sek-Video",
            "elevenlabs.io → Text einfügen → Stimme wählen → MP3 runterladen",
            "Passende Bilder/Videos: pexels.com, pixabay.com, unsplash.com (alle kostenlos)",
            "CapCut: Audio importieren → Bilder/Clips zur Audiolänge anpassen",
            "Captions mit Auto-Caption-Feature hinzufügen",
            "Hintergrundmusik (leise) + Effekte hinzufügen",
            "Thumbnail: erstes Frame mit fettem Text als Hook",
        ],
        "tipps": "ElevenLabs 'Rachel' oder 'Adam' klingen sehr natürlich. Skript flüssig schreiben.",
    },
    "hande_pov": {
        "emoji": "🙌",
        "name": "Nur-Hände / POV-Stil",
        "kurz": "Kamera von oben, nur Hände sichtbar – kein Gesicht",
        "tools": ["Smartphone + Stativ/Halterung", "Ring Light (optional)", "CapCut"],
        "anleitung": [
            "Handy mit Stativ oder Bücherstapel von OBEN aufstellen (Birds-Eye-View)",
            "Auflösung: 4K oder 1080p, Hochformat 9:16",
            "Thema filmen: Kochen, Zeichnen, Tippen, Unboxing, Basteln...",
            "Hände in Frame halten – Gesicht nie sichtbar",
            "Mehrere Clips aufnehmen (je 5–10 Sek), dann schneiden",
            "In CapCut: schnelle Cuts, Zoom-Ins auf wichtige Momente",
            "Text-Overlays + Trendmusik hinzufügen",
        ],
        "tipps": "Gute Beleuchtung von oben ist key! Natürliches Licht oder Ring Light.",
    },
    "listicle": {
        "emoji": "📋",
        "name": "Listicle (Top-N Liste)",
        "kurz": "Top 5/10 Liste mit Textkarten, ideal für jeden Trend",
        "tools": ["Canva (kostenlos)", "CapCut", "ElevenLabs oder eigene Stimme"],
        "anleitung": [
            "Canva → TikTok-Vorlage (1080×1920) wählen",
            "5–10 Fakten/Punkte zum Trendthema recherchieren",
            "Eine Slide pro Punkt: große Zahl + kurzer Text",
            "Farbschema einheitlich halten (2–3 Farben max.)",
            "Als MP4 aus Canva exportieren ODER als Bilder → CapCut slideshow",
            "Voiceover: jeden Punkt kurz vorlesen/erklären",
            "Hook: 'Top 5 Dinge über X, die du noch nicht wusstest'",
        ],
        "tipps": "Nummerierung rückwärts (5→1) hält Zuschauer länger! Nr. 1 als Cliffhanger.",
    },
    "compilation": {
        "emoji": "📹",
        "name": "Compilation / Montage",
        "kurz": "Öffentliche Clips curatieren und mit eigenem Kommentar montieren",
        "tools": ["CapCut", "DaVinci Resolve (kostenlos)", "Canva für Titel"],
        "anleitung": [
            "TikTok/YouTube nach dem Trend-Begriff suchen",
            "Clips mit 'Save' speichern ODER Screenshot-Recording nutzen",
            "Alternativ: royalty-free Clips von pexels.com laden",
            "CapCut: alle Clips zusammenschneiden (je 3–5 Sek pro Clip)",
            "Kommentar-Overlays: 'Krass, oder?', 'Hab ich auch gedacht...' etc.",
            "Intro-Text: 'Die besten X zum Thema Y'",
            "Musik drunter + Captions → posten",
        ],
        "tipps": "Immer Quelle taggen (@originalcreator) um Strikes zu vermeiden.",
    },
    "animation_text": {
        "emoji": "🎬",
        "name": "Animierter Text / Kinetic Typography",
        "kurz": "Texte fliegen/tanzen auf dem Bildschirm – sehr viral",
        "tools": ["Canva (Animationen)", "Adobe Express", "CapCut Textanimationen"],
        "anleitung": [
            "Canva → TikTok Vorlage → Hintergrundfarbe oder Video wählen",
            "Text einfügen → Animation: 'Typewriter', 'Rise', 'Pop' wählen",
            "Jeden Satz als eigenes Textelement, zeitlich versetzt",
            "Kontrastreiche Farben: Gelb auf Schwarz, Weiß auf dunkel",
            "Als Präsentation abspielen + Bildschirm aufnehmen (oder direkt exportieren)",
            "In CapCut: Musik synchronisieren, Beats = Textappearance",
            "Sound-on Hook: 'Sound an! Du wirst es bereuen wenn nicht'",
        ],
        "tipps": "Musik-Beat mit Text-Erscheinen synchronisieren = maximale Retention!",
    },
    "react_kommentar": {
        "emoji": "💬",
        "name": "React / Kommentar (ohne Gesicht)",
        "kurz": "Auf virale Videos reagieren – nur Bildschirm + Stimme/Text",
        "tools": ["CapCut (Stitch/Duet-Funktion)", "Bildschirmaufnahme"],
        "anleitung": [
            "Viralen Clip zum Thema finden",
            "TikTok Stitch-Funktion nutzen: 5 Sek vom Original → eigene Reaktion",
            "Oder: Bildschirm aufnehmen wie du auf das Video reagierst",
            "Reaktion: Text-Overlays statt Gesicht ('Ich: 🤯', 'POV: du siehst das')",
            "Eigene Meinung als Text am Ende: 'Ich denke...' / 'Was meint ihr?'",
            "Frage in Caption → Kommentare pushen den Algorithmus!",
            "Trending Hashtags + Original-Creator taggen",
        ],
        "tipps": "Fragen am Ende sind GOLD für den Algorithmus. Mehr Kommentare = mehr Reichweite.",
    },
}

# ── Nischen-Subreddits ──────────────────────────────────────────────────────

NISCHEN_SUBREDDITS: Dict[str, List[str]] = {
    "gaming": ["gaming", "Games", "pcgaming", "indiegaming", "GameDeals"],
    "finance": ["personalfinance", "investing", "CryptoCurrency", "stocks", "financialindependence"],
    "lifestyle": ["lifestyle", "selfimprovement", "productivity", "minimalism", "zerowaste"],
    "beauty": ["beauty", "SkincareAddiction", "MakeupAddiction", "HaircareScience"],
    "food": ["food", "cooking", "recipes", "mealprep", "EatCheapAndHealthy"],
    "fitness": ["fitness", "bodyweightfitness", "running", "loseit", "gainit"],
    "tech": ["technology", "gadgets", "artificial", "MachineLearning", "ChatGPT"],
    "humor": ["funny", "memes", "AskReddit", "tifu", "confessions"],
    "allgemein": ["popular", "all", "worldnews", "todayilearned", "Showerthoughts"],
}

NEWS_RSS_FEEDS: List[Dict[str, str]] = [
    {"name": "Google News DE", "url": "https://news.google.com/rss?hl=de&gl=DE&ceid=DE:de"},
    {"name": "Spiegel Online", "url": "https://www.spiegel.de/schlagzeilen/index.rss"},
    {"name": "BBC World", "url": "http://feeds.bbci.co.uk/news/rss.xml"},
    {"name": "Reddit Popular", "url": "https://www.reddit.com/r/popular.rss"},
    {"name": "YouTube Trending (DE)", "url": "https://www.youtube.com/feeds/videos.xml?chart=most_popular&regionCode=DE&hl=de"},
]

# ── Daten-Fetcher ───────────────────────────────────────────────────────────

def hole_google_trends(land: str = "DE", anzahl: int = 10) -> List[Dict]:
    """Holt aktuelle Google Trending Searches."""
    trends = []
    # Methode 1: pytrends (inoffizielle API)
    if _PYTRENDS_OK:
        try:
            pytrends = TrendReq(hl="de-DE", tz=60, timeout=(10, 25))
            trending = pytrends.trending_searches(pn=land.lower())
            for i, term in enumerate(trending[0][:anzahl]):
                trends.append({
                    "titel": str(term),
                    "quelle": "Google Trends",
                    "quelle_emoji": "🔍",
                    "score": anzahl - i,
                    "url": f"https://trends.google.com/trends/trendingsearches/daily?geo={land}",
                    "kategorie": "suche",
                })
            if trends:
                return trends
        except Exception:
            pass

    # Methode 2: Google Trends RSS (öffentlich)
    try:
        headers = {"User-Agent": "Mozilla/5.0 TrendAnalyzer/1.0"}
        url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={land}"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            for i, item in enumerate(root.findall(".//item")[:anzahl]):
                title_el = item.find("title")
                if title_el is not None and title_el.text:
                    trends.append({
                        "titel": title_el.text.strip(),
                        "quelle": "Google Trends",
                        "quelle_emoji": "🔍",
                        "score": anzahl - i,
                        "url": f"https://trends.google.com/trends/trendingsearches/daily?geo={land}",
                        "kategorie": "suche",
                    })
    except Exception as e:
        console.print(f"[dim yellow]⚠ Google Trends RSS: {e}[/dim yellow]")
    return trends


def hole_reddit_trends(subreddits: List[str], anzahl_pro_sub: int = 3) -> List[Dict]:
    """Holt Hot-Posts von Reddit ohne API-Key (öffentliche JSON-API)."""
    trends = []
    headers = {"User-Agent": "TrendAnalyzer/1.0 (faceless tiktok tool)"}
    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit={anzahl_pro_sub}"
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code != 200:
                continue
            posts = r.json().get("data", {}).get("children", [])
            for post in posts[:anzahl_pro_sub]:
                d = post.get("data", {})
                if d.get("stickied") or d.get("over_18"):
                    continue
                trends.append({
                    "titel": d.get("title", "")[:100],
                    "quelle": f"Reddit r/{sub}",
                    "quelle_emoji": "🟠",
                    "score": min(int(d.get("score", 0)) // 100, 10),
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                    "kategorie": "community",
                    "kommentare": d.get("num_comments", 0),
                })
            time.sleep(0.5)
        except Exception:
            continue
    return trends


def _parse_rss(xml_text: str, max_items: int) -> List[Tuple[str, str]]:
    """Parst RSS/Atom XML und gibt (title, link)-Paare zurück."""
    items: List[Tuple[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        # Atom-Feed
        for entry in root.findall(".//atom:entry", ns)[:max_items]:
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            title = title_el.text if title_el is not None else ""
            link = link_el.get("href", "") if link_el is not None else ""
            if title:
                items.append((title.strip(), link))
        if items:
            return items
        # RSS-Feed
        for item in root.findall(".//item")[:max_items]:
            title_el = item.find("title")
            link_el = item.find("link")
            title = title_el.text if title_el is not None else ""
            link = link_el.text if link_el is not None else ""
            if title:
                items.append((title.strip(), link or ""))
    except ET.ParseError:
        pass
    return items


def hole_news_trends(max_pro_feed: int = 5) -> List[Dict]:
    """Holt aktuelle Headlines aus RSS-Feeds via eingebautem XML-Parser."""
    trends = []
    headers = {"User-Agent": "Mozilla/5.0 TrendAnalyzer/1.0"}
    for feed_info in NEWS_RSS_FEEDS:
        try:
            r = requests.get(feed_info["url"], headers=headers, timeout=8)
            if r.status_code != 200:
                continue
            for titel, url in _parse_rss(r.text, max_pro_feed):
                if len(titel) < 10:
                    continue
                trends.append({
                    "titel": titel[:120],
                    "quelle": feed_info["name"],
                    "quelle_emoji": "📰",
                    "score": 5,
                    "url": url,
                    "kategorie": "news",
                })
        except Exception:
            continue
    return trends


def hole_youtube_trending(land: str = "DE") -> List[Dict]:
    """Holt YouTube Trending via invidious-API (kein API-Key nötig)."""
    trends = []
    # Invidious ist ein Open-Source YouTube Frontend mit API
    invidious_instances = [
        "https://invidious.snopyta.org",
        "https://vid.puffyan.us",
        "https://invidious.kavin.rocks",
    ]
    for instance in invidious_instances:
        try:
            url = f"{instance}/api/v1/trending?region={land}&type=default"
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                videos = r.json()[:8]
                for i, v in enumerate(videos):
                    trends.append({
                        "titel": v.get("title", "")[:100],
                        "quelle": "YouTube Trending",
                        "quelle_emoji": "▶️",
                        "score": 8 - i,
                        "url": f"https://youtube.com/watch?v={v.get('videoId', '')}",
                        "kategorie": "video",
                        "views": v.get("viewCount", 0),
                    })
                break
        except Exception:
            continue
    return trends


# ── Fallback-Daten ─────────────────────────────────────────────────────────

def _fallback_trends() -> List[Dict]:
    """Beispiel-Trends falls keine Live-Daten erreichbar sind."""
    return [
        {"titel": "KI Tools für Alltag", "quelle": "Google Trends [Beispiel]", "quelle_emoji": "🔍", "score": 10, "url": "", "kategorie": "suche"},
        {"titel": "Passives Einkommen 2024", "quelle": "Google Trends [Beispiel]", "quelle_emoji": "🔍", "score": 9, "url": "", "kategorie": "suche"},
        {"titel": "ChatGPT Hacks die du nicht kennst", "quelle": "Reddit [Beispiel]", "quelle_emoji": "🟠", "score": 9, "url": "", "kategorie": "community"},
        {"titel": "Budget Meal Prep für die ganze Woche", "quelle": "Reddit [Beispiel]", "quelle_emoji": "🟠", "score": 8, "url": "", "kategorie": "community"},
        {"titel": "Neue iPhone Feature gefunden", "quelle": "YouTube [Beispiel]", "quelle_emoji": "▶️", "score": 8, "url": "", "kategorie": "video"},
        {"titel": "Wirtschaft: Inflation & Zinsen 2024", "quelle": "Spiegel [Beispiel]", "quelle_emoji": "📰", "score": 7, "url": "", "kategorie": "news"},
        {"titel": "Skincare Routine unter 20€", "quelle": "Reddit [Beispiel]", "quelle_emoji": "🟠", "score": 7, "url": "", "kategorie": "community"},
        {"titel": "Gaming Setup für wenig Geld", "quelle": "Reddit [Beispiel]", "quelle_emoji": "🟠", "score": 6, "url": "", "kategorie": "community"},
        {"titel": "Produktivitäts-App die alles verändert", "quelle": "Google Trends [Beispiel]", "quelle_emoji": "🔍", "score": 6, "url": "", "kategorie": "suche"},
        {"titel": "Crypto Markt Analyse", "quelle": "Reddit [Beispiel]", "quelle_emoji": "🟠", "score": 5, "url": "", "kategorie": "community"},
    ]


# ── Trend-Analyse ──────────────────────────────────────────────────────────

def dedupliziere_trends(trends: List[Dict]) -> List[Dict]:
    """Entfernt Duplikate und fasst ähnliche Trends zusammen."""
    gesehen = set()
    unique = []
    for t in trends:
        key = t["titel"].lower()[:40]
        # Einfache Deduplizierung über erste 40 Zeichen
        if key not in gesehen:
            gesehen.add(key)
            unique.append(t)
    return unique


def sortiere_trends(trends: List[Dict]) -> List[Dict]:
    """Sortiert Trends nach Score (höchster zuerst)."""
    return sorted(trends, key=lambda x: x.get("score", 0), reverse=True)


def empfehle_format(trend: Dict) -> Tuple[str, Dict]:
    """Wählt das beste Faceless-Format für einen Trend."""
    kategorie = trend.get("kategorie", "")
    titel = trend.get("titel", "").lower()

    # Einfache Heuristik je nach Trend-Typ
    if kategorie == "video":
        key = "react_kommentar"
    elif kategorie == "news":
        key = "voiceover_bilder"
    elif any(w in titel for w in ["top", "best", "liste", "tipps"]):
        key = "listicle"
    elif kategorie == "suche":
        key = "text_on_screen"
    elif kategorie == "community":
        key = "react_kommentar"
    else:
        key = "listicle"

    return key, FACELESS_FORMATE[key]


# ── Ausgabe / UI ────────────────────────────────────────────────────────────

def zeige_trend_tabelle(trends: List[Dict], top_n: int = 10) -> None:
    """Zeigt eine schöne Tabelle aller Trends."""
    table = Table(
        title=f"🔥 TOP {top_n} TRENDS — {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        border_style="bright_black",
        expand=True,
    )
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Trend", style="white", no_wrap=False, ratio=4)
    table.add_column("Quelle", style="yellow", ratio=2)
    table.add_column("Heat", justify="center", width=8)
    table.add_column("Video-Format", style="green", ratio=2)

    heat_bars = {10: "🔥🔥🔥", 9: "🔥🔥🔥", 8: "🔥🔥", 7: "🔥🔥", 6: "🔥", 5: "🔥", 4: "📈", 3: "📈", 2: "📊", 1: "📊", 0: "❄️"}

    for i, trend in enumerate(trends[:top_n], 1):
        score = trend.get("score", 0)
        heat = heat_bars.get(min(score, 10), "📊")
        format_key, fmt = empfehle_format(trend)
        table.add_row(
            str(i),
            trend["titel"],
            f"{trend['quelle_emoji']} {trend['quelle']}",
            heat,
            f"{fmt['emoji']} {fmt['name']}",
        )

    console.print(table)


def zeige_video_anleitung(trend: Dict, rang: int) -> None:
    """Zeigt die vollständige Video-Anleitung für einen Trend."""
    format_key, fmt = empfehle_format(trend)

    # Titel-Panel
    console.print()
    console.print(Panel(
        f"[bold white]#{rang} — {trend['titel']}[/bold white]\n"
        f"[dim]{trend['quelle_emoji']} {trend['quelle']} | Score: {trend.get('score', 0)}/10[/dim]",
        title=f"[bold green]{fmt['emoji']} {fmt['name']}[/bold green]",
        border_style="green",
    ))

    # Video-Idee
    video_idee = generiere_video_idee(trend, fmt)
    console.print(Panel(
        video_idee,
        title="💡 [bold yellow]Deine Video-Idee[/bold yellow]",
        border_style="yellow",
        padding=(0, 1),
    ))

    # Schritt-für-Schritt
    schritte_text = "\n".join([f"[bold cyan]{j}.[/bold cyan] {s}" for j, s in enumerate(fmt["anleitung"], 1)])
    console.print(Panel(
        schritte_text,
        title="📋 [bold blue]Schritt-für-Schritt Anleitung[/bold blue]",
        border_style="blue",
        padding=(0, 1),
    ))

    # Tools + Tipps
    tools_text = " · ".join([f"[green]{t}[/green]" for t in fmt["tools"]])
    console.print(Panel(
        f"🛠️ [bold]Tools:[/bold] {tools_text}\n"
        f"💡 [bold]Tipp:[/bold] [italic]{fmt['tipps']}[/italic]\n"
        f"🏷️ [bold]Hashtags:[/bold] [dim]{generiere_hashtags(trend)}[/dim]",
        title="⚙️ [bold]Extras[/bold]",
        border_style="bright_black",
        padding=(0, 1),
    ))


def generiere_video_idee(trend: Dict, fmt: Dict) -> str:
    """Generiert eine konkrete Video-Idee basierend auf Trend und Format."""
    titel = trend["titel"]
    kat = trend.get("kategorie", "")

    ideen_templates = {
        "screen_record": f"'Ich zeige dir alles über {titel} in 60 Sekunden' — Bildschirm aufnehmen wie du das Thema googelst, Wikipedia liest oder eine App/Website nutzt. Voiceover mit ElevenLabs drüber.",
        "text_on_screen": f"'Das steckt wirklich hinter {titel}' — 5–7 kurze Text-Slides mit krassen Fakten. Letzter Slide: Frage an die Community.",
        "voiceover_bilder": f"'Was du über {titel} wissen musst' — 60-Sek-Erklärung mit KI-Stimme, passende Stockfotos von Pexels. Hook: überraschendsten Fakt zuerst.",
        "hande_pov": f"'POV: Du beschäftigst dich mit {titel}' — Kamera von oben, nur Hände sichtbar. Zeige physisch relevante Dinge (Notizen, Produkte, Gesten).",
        "listicle": f"'Top 5 Fakten über {titel}' — Nummerierung rückwärts 5→1, Nr. 1 als Cliffhanger. KI-Voiceover + Canva-Slides.",
        "compilation": f"'Die besten Clips zu {titel}' — 5–8 öffentliche Clips curatieren, mit eigenem Kommentar als Text-Overlay versehen.",
        "animation_text": f"'Wusstest du DAS über {titel}?' — Kinetic Typography: überraschende Fakten mit fettgedruckten Wörtern zur Musik.",
        "react_kommentar": f"'Meine Reaktion auf {titel}' — Viralen Clip per Stitch/Bildschirmaufnahme zeigen, eigene Reaktion als Text-Overlay.",
    }

    # Finde den richtigen Key durch Vergleich mit dem Format-Namen
    format_name_zu_key = {v["name"]: k for k, v in FACELESS_FORMATE.items()}
    key = format_name_zu_key.get(fmt.get("name", ""), "listicle")
    return ideen_templates.get(key, f"Erstelle ein Video über '{titel}' im Format '{fmt['name']}'")


def generiere_hashtags(trend: Dict) -> str:
    """Generiert relevante Hashtags für den Trend."""
    basis = ["#fyp", "#foryou", "#viral", "#foryoupage", "#trending"]
    trend_wort = trend["titel"].split()[0].lower().replace(",", "").replace(".", "")
    kategorie_tags = {
        "gaming": ["#gaming", "#gamer", "#games"],
        "news": ["#news", "#aktuell", "#wusstest"],
        "video": ["#youtube", "#reaction", "#musthave"],
        "suche": ["#tipsandtricks", "#lifehack", "#wissenswertes"],
        "community": ["#reddit", "#community", "#storytime"],
    }
    kat_tags = kategorie_tags.get(trend.get("kategorie", ""), ["#knowledge", "#facts"])
    alle = basis[:3] + [f"#{trend_wort}"] + kat_tags[:2]
    return " ".join(alle)


# ── Posting-Plan ────────────────────────────────────────────────────────────

def zeige_posting_plan(trends: List[Dict], top_n: int = 5) -> None:
    """Zeigt einen 7-Tage-Posting-Plan."""
    wochentage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    beste_zeiten = {
        "Montag": "18:00–20:00",
        "Dienstag": "18:00–20:00",
        "Mittwoch": "17:00–19:00",
        "Donnerstag": "19:00–21:00",
        "Freitag": "20:00–22:00",
        "Samstag": "14:00–16:00 + 20:00–22:00",
        "Sonntag": "15:00–17:00",
    }
    table = Table(
        title="📅 7-TAGE-POSTING-PLAN",
        box=box.ROUNDED,
        header_style="bold magenta",
        border_style="bright_black",
        expand=True,
    )
    table.add_column("Tag", style="bold cyan", width=12)
    table.add_column("Beste Zeit", style="yellow", width=22)
    table.add_column("Video-Idee", ratio=4)
    table.add_column("Format", style="green", ratio=2)

    for i, tag in enumerate(wochentage):
        if i < len(trends):
            trend = trends[i % top_n]
            _, fmt = empfehle_format(trend)
            idee = trend["titel"][:60] + ("..." if len(trend["titel"]) > 60 else "")
            table.add_row(tag, beste_zeiten[tag], idee, f"{fmt['emoji']} {fmt['name']}")
        else:
            table.add_row(tag, beste_zeiten[tag], "[dim]Eigene Idee / Evergreen Content[/dim]", "[dim]Frei wählen[/dim]")

    console.print()
    console.print(table)


# ── Tool-Quickstart ────────────────────────────────────────────────────────

def zeige_tool_quickstart() -> None:
    """Zeigt Kurzreferenz der wichtigsten Tools."""
    tools = [
        ("CapCut", "capcut.com", "Schnitt, Captions, Musik", "Kostenlos"),
        ("ElevenLabs", "elevenlabs.io", "KI-Voiceover", "Kostenlos 10k Zeichen/Mo"),
        ("Canva", "canva.com", "Design, Slides, Animation", "Kostenlos"),
        ("Pexels", "pexels.com", "Stock-Videos & Fotos", "Kostenlos"),
        ("OBS Studio", "obsproject.com", "Screen Recording", "Kostenlos"),
        ("CapCut PC", "capcut.com", "Professioneller Schnitt", "Kostenlos"),
        ("Pixabay", "pixabay.com", "Stock-Bilder & Videos", "Kostenlos"),
        ("Renderforest", "renderforest.com", "Animationen", "Freemium"),
    ]
    table = Table(
        title="🛠️ TOOL-QUICKSTART — ALLES KOSTENLOS",
        box=box.SIMPLE,
        header_style="bold green",
    )
    table.add_column("Tool", style="bold white")
    table.add_column("Website")
    table.add_column("Für was?")
    table.add_column("Preis", style="cyan")
    for row in tools:
        table.add_row(*row)
    console.print()
    console.print(table)


# ── Main ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TikTok Trend Analyzer – Faceless Video Ideen")
    p.add_argument("--land", default="DE", help="Land für Google Trends (DE, US, GB, ...)")
    p.add_argument("--top", type=int, default=10, help="Anzahl Top-Trends (default: 10)")
    p.add_argument("--nische", default="allgemein", choices=list(NISCHEN_SUBREDDITS.keys()),
                   help="Nische für Reddit-Trends")
    p.add_argument("--detail", type=int, default=5, help="Für wie viele Trends Anleitungen zeigen (default: 5)")
    p.add_argument("--kein-plan", action="store_true", help="Posting-Plan überspringen")
    p.add_argument("--kein-tools", action="store_true", help="Tool-Übersicht überspringen")
    p.add_argument("--nur-trends", action="store_true", help="Nur Trend-Tabelle, keine Anleitungen")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    console.print(Rule("[bold magenta]🎵 TikTok Trend Analyzer[/bold magenta]"))
    console.print(f"[dim]Land: {args.land} | Nische: {args.nische} | Top: {args.top}[/dim]\n")

    alle_trends: List[Dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=20),
        transient=True,
    ) as progress:
        t1 = progress.add_task("🔍 Google Trends laden...", total=None)
        gt = hole_google_trends(land=args.land, anzahl=args.top)
        alle_trends.extend(gt)
        progress.update(t1, description=f"✅ Google Trends: {len(gt)} Trends")
        progress.stop_task(t1)

        t2 = progress.add_task("🟠 Reddit Hot Posts laden...", total=None)
        subs = NISCHEN_SUBREDDITS.get(args.nische, NISCHEN_SUBREDDITS["allgemein"])
        rt = hole_reddit_trends(subreddits=subs[:4], anzahl_pro_sub=3)
        alle_trends.extend(rt)
        progress.update(t2, description=f"✅ Reddit: {len(rt)} Posts")
        progress.stop_task(t2)

        t3 = progress.add_task("📰 News-Feeds laden...", total=None)
        nt = hole_news_trends(max_pro_feed=4)
        alle_trends.extend(nt)
        progress.update(t3, description=f"✅ News: {len(nt)} Headlines")
        progress.stop_task(t3)

        t4 = progress.add_task("▶️ YouTube Trending laden...", total=None)
        yt = hole_youtube_trending(land=args.land)
        alle_trends.extend(yt)
        progress.update(t4, description=f"✅ YouTube: {len(yt)} Videos")
        progress.stop_task(t4)

    # Trends verarbeiten
    alle_trends = dedupliziere_trends(alle_trends)
    alle_trends = sortiere_trends(alle_trends)

    # Fallback: Wenn keine Live-Daten, Beispiel-Trends zeigen
    if not alle_trends:
        console.print("[yellow]⚠ Keine Live-Daten verfügbar (Netzwerk/Rate-Limit). Zeige Beispiel-Trends.[/yellow]")
        alle_trends = _fallback_trends()

    console.print(f"\n[bold green]✅ {len(alle_trends)} Trends gefunden — zeige Top {args.top}[/bold green]\n")

    # Tabelle
    zeige_trend_tabelle(alle_trends, top_n=args.top)

    if args.nur_trends:
        return

    # Detaillierte Anleitungen
    console.print()
    console.print(Rule("[bold yellow]📹 VIDEO-ANLEITUNGEN (Faceless)[/bold yellow]"))

    for i, trend in enumerate(alle_trends[:args.detail], 1):
        zeige_video_anleitung(trend, rang=i)

    # Posting-Plan
    if not args.kein_plan:
        console.print()
        console.print(Rule("[bold blue]📅 POSTING-PLAN[/bold blue]"))
        zeige_posting_plan(alle_trends, top_n=args.detail)

    # Tool-Übersicht
    if not args.kein_tools:
        console.print()
        console.print(Rule("[bold green]🛠️ TOOLS[/bold green]"))
        zeige_tool_quickstart()

    # Alle Formate anzeigen
    console.print()
    console.print(Rule("[bold cyan]📚 ALLE FACELESS-FORMATE[/bold cyan]"))
    fmt_table = Table(box=box.SIMPLE, header_style="bold cyan", expand=True)
    fmt_table.add_column("Format", style="bold white")
    fmt_table.add_column("Kurzbeschreibung")
    fmt_table.add_column("Schwierigkeit →", style="dim")
    fmt_table.add_column("Zeitaufwand", style="yellow")

    schwierigkeiten = {
        "screen_record": ("Leicht", "15–30 Min"),
        "text_on_screen": ("Sehr leicht", "10–20 Min"),
        "voiceover_bilder": ("Leicht", "20–40 Min"),
        "hande_pov": ("Mittel", "20–45 Min"),
        "listicle": ("Sehr leicht", "15–25 Min"),
        "compilation": ("Mittel", "30–60 Min"),
        "animation_text": ("Mittel", "30–60 Min"),
        "react_kommentar": ("Leicht", "15–30 Min"),
    }
    for key, fmt in FACELESS_FORMATE.items():
        s, z = schwierigkeiten.get(key, ("Mittel", "30 Min"))
        fmt_table.add_row(f"{fmt['emoji']} {fmt['name']}", fmt["kurz"], s, z)
    console.print(fmt_table)

    console.print()
    console.print(Panel(
        "[bold white]Pro-Tipps:[/bold white]\n"
        "• [cyan]Post täglich[/cyan] — Konsistenz schlägt Perfektion auf TikTok\n"
        "• [cyan]Erste 2 Sekunden[/cyan] sind entscheidend — Hook SOFORT!\n"
        "• [cyan]Sound an![/cyan] — Text 'Sound an!' als erster Frame erhöht Watch-Time\n"
        "• [cyan]3–5 Hashtags[/cyan] reichen — nicht 30 random Hashtags spammen\n"
        "• [cyan]Fragen stellen[/cyan] — Kommentare pushen den Algorithmus massiv\n"
        "• [cyan]Nische wählen[/cyan] — besser 1000 Follower in Nische als 100 random\n"
        "• [cyan]Trends früh erwischen[/cyan] — dieses Tool täglich laufen lassen!",
        title="🚀 [bold green]Erfolgs-Tipps für TikTok[/bold green]",
        border_style="green",
    ))
    console.print()


if __name__ == "__main__":
    main()
