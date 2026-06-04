# JARVIS — Lokaler KI-Assistent

Vollständig lokaler AI-Assistent — kein API-Key, kein Cloud-Dienst, alles auf deinem PC.

## Features

- **100% Lokal** — Läuft komplett auf deinem PC, keine externen APIs
- **Selbstlernend** — Merkt sich Fakten, Präferenzen und Wissen aus jedem Gespräch
- **Sprachsteuerung** — Mikrofon-Eingabe (Whisper) + Sprachausgabe (Edge-TTS)
- **15+ Tools** — Websuche, Code-Ausführung, Dateien, System, Wetter, Notizen, Todos
- **Modell-Wahl** — Nutze jedes Ollama-Modell (Llama 3, Mistral, Qwen, DeepSeek...)
- **Schönes Web-UI** — Jarvis-Interface im Browser auf Port 7860

## Schnellstart

```bash
cd jarvis
./setup.sh        # Einmalig: installiert alles
./start.sh        # Jarvis starten
```

Dann öffne: http://localhost:7860

## Modelle

| Modell | Größe | Eigenschaften |
|--------|-------|---------------|
| llama3.2:3b | 2GB | Standard, schnell |
| llama3.1:8b | 4.7GB | Besser, empfohlen |
| qwen2.5:7b | 4.4GB | Exzellentes Deutsch |
| mistral:7b | 4.1GB | Gut allgemein |
| deepseek-r1:7b | 4.7GB | Stark beim Denken |
| llama3.1:70b | 40GB | Bestes Modell |

Modell installieren: `ollama pull <modell-name>`

## Verfügbare Tools

| Tool | Beschreibung |
|------|-------------|
| web_search | DuckDuckGo-Suche (kein API-Key) |
| web_fetch | Webseiten abrufen und lesen |
| calculate | Mathematik, Gleichungen, Ableitungen |
| convert_units | Einheiten umrechnen |
| run_python | Python-Code ausführen |
| get_weather | Wetter abrufen (wttr.in) |
| read/write_file | Dateien lesen/schreiben |
| get_system_info | CPU, RAM, Festplatte |
| create_note | Notizen erstellen |
| add_todo | Todos verwalten |

## Selbst-Lernfähigkeit

Jarvis lernt automatisch aus jedem Gespräch:
- Extrahiert Fakten alle 5 Interaktionen
- Speichert Wissen in ChromaDB (Vektorspeicher)
- Ruft relevante Erinnerungen bei ähnlichen Fragen ab
- Merkt sich Profildaten (Name, Beruf, Vorlieben)
- Fasst lange Gespräche automatisch zusammen

## Konfiguration

Bearbeite `config.yaml`:

```yaml
jarvis:
  name: "Jarvis"
  language: "de"

llm:
  default_model: "llama3.2:3b"   # Schnelles Modell
  powerful_model: "llama3.1:8b"  # Für komplexe Aufgaben

voice:
  tts:
    enabled: true
    voice: "de-DE-KillianNeural"
  stt:
    enabled: true
    model: "base"  # tiny/base/small/medium
```

## Systemanforderungen

- **Minimum:** 8GB RAM, 10GB Speicher (llama3.2:3b)
- **Empfohlen:** 16GB RAM, 20GB Speicher (llama3.1:8b)
- **Optimal:** 32GB RAM + NVIDIA GPU (alle Modelle, sehr schnell)
- Python 3.10+, Ollama
