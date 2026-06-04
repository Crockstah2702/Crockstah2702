"""
Multi-Language Code-Runner — Jarvis kann Code in allen Sprachen ausführen:
Python, JavaScript/Node, Bash, TypeScript, Go, Rust, C/C++, Java, PHP, Ruby, Perl, R...
"""
import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Welche Sprachen verfügbar sind (dynamisch erkannt)
LANGUAGE_CONFIG = {
    "python":     {"ext": ".py",   "cmd": ["python3", "{file}"]},
    "python3":    {"ext": ".py",   "cmd": ["python3", "{file}"]},
    "javascript": {"ext": ".js",   "cmd": ["node", "{file}"]},
    "js":         {"ext": ".js",   "cmd": ["node", "{file}"]},
    "typescript": {"ext": ".ts",   "cmd": ["ts-node", "{file}"]},
    "ts":         {"ext": ".ts",   "cmd": ["ts-node", "{file}"]},
    "bash":       {"ext": ".sh",   "cmd": ["bash", "{file}"]},
    "shell":      {"ext": ".sh",   "cmd": ["bash", "{file}"]},
    "sh":         {"ext": ".sh",   "cmd": ["bash", "{file}"]},
    "go":         {"ext": ".go",   "cmd": ["go", "run", "{file}"]},
    "rust":       {"ext": ".rs",   "compile": ["rustc", "{file}", "-o", "{out}"], "run": ["{out}"]},
    "c":          {"ext": ".c",    "compile": ["gcc", "{file}", "-o", "{out}"], "run": ["{out}"]},
    "cpp":        {"ext": ".cpp",  "compile": ["g++", "{file}", "-o", "{out}"], "run": ["{out}"]},
    "c++":        {"ext": ".cpp",  "compile": ["g++", "{file}", "-o", "{out}"], "run": ["{out}"]},
    "java":       {"ext": ".java", "compile": ["javac", "{file}"], "run": ["java", "-cp", "{dir}", "{classname}"]},
    "php":        {"ext": ".php",  "cmd": ["php", "{file}"]},
    "ruby":       {"ext": ".rb",   "cmd": ["ruby", "{file}"]},
    "perl":       {"ext": ".pl",   "cmd": ["perl", "{file}"]},
    "r":          {"ext": ".R",    "cmd": ["Rscript", "{file}"]},
    "lua":        {"ext": ".lua",  "cmd": ["lua", "{file}"]},
    "swift":      {"ext": ".swift","cmd": ["swift", "{file}"]},
    "kotlin":     {"ext": ".kts",  "cmd": ["kotlinc", "-script", "{file}"]},
    "powershell": {"ext": ".ps1",  "cmd": ["pwsh", "-File", "{file}"]},
    "ps1":        {"ext": ".ps1",  "cmd": ["pwsh", "-File", "{file}"]},
    "sql":        {"ext": ".sql",  "cmd": ["sqlite3", ":memory:", ".read", "{file}"]},
}


async def run_code(code: str, language: str = "python", timeout: int = 30) -> str:
    """Führe Code in einer beliebigen Programmiersprache aus."""
    lang = language.lower().strip()
    config = LANGUAGE_CONFIG.get(lang)

    if not config:
        supported = ", ".join(sorted(set(LANGUAGE_CONFIG.keys())))
        return f"❌ Sprache '{language}' nicht unterstützt.\nVerfügbar: {supported}"

    # Prüfe ob Compiler/Interpreter verfügbar ist
    if "cmd" in config:
        exe = config["cmd"][0]
    elif "compile" in config:
        exe = config["compile"][0]
    else:
        exe = None

    if exe and exe not in ["{file}", "{out}"] and not shutil.which(exe):
        return (f"❌ '{exe}' nicht installiert.\n"
                f"Installation: sudo apt install {exe} (Linux) oder choco install {exe} (Windows)")

    # Temporäre Datei erstellen
    ext = config["ext"]
    with tempfile.TemporaryDirectory() as tmpdir:
        src_file = os.path.join(tmpdir, f"jarvis_code{ext}")
        out_file = os.path.join(tmpdir, "jarvis_out")

        with open(src_file, "w", encoding="utf-8") as f:
            f.write(code)

        try:
            # Kompilieren wenn nötig
            if "compile" in config:
                compile_cmd = [
                    c.replace("{file}", src_file)
                     .replace("{out}", out_file)
                     .replace("{dir}", tmpdir)
                    for c in config["compile"]
                ]
                proc = await asyncio.create_subprocess_exec(
                    *compile_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                if proc.returncode != 0:
                    return f"❌ Kompilierfehler:\n{stderr.decode('utf-8', errors='replace')}"

                # Ausführen (kompiliertes Binary)
                run_cmd = config["run"]
                if lang == "java":
                    # Java: Klassenname aus Datei lesen
                    import re
                    classname = re.search(r'class\s+(\w+)', code)
                    classname = classname.group(1) if classname else "Main"
                    run_cmd = [c.replace("{classname}", classname).replace("{dir}", tmpdir) for c in run_cmd]
                else:
                    run_cmd = [c.replace("{out}", out_file) for c in run_cmd]

                proc = await asyncio.create_subprocess_exec(
                    *run_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
                # Direkt ausführen
                cmd = [
                    c.replace("{file}", src_file).replace("{dir}", tmpdir)
                    for c in config["cmd"]
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir
                )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip()

            if out and err:
                return f"Output:\n{out}\n\nWarnings/Fehler:\n{err}"
            return out or err or "(kein Output)"

        except asyncio.TimeoutError:
            return f"❌ Zeitüberschreitung nach {timeout}s"
        except Exception as e:
            return f"❌ Ausführungsfehler: {e}"


def list_available_languages() -> str:
    """Zeigt alle verfügbaren Programmiersprachen."""
    available = []
    unavailable = []
    seen = set()
    for lang, cfg in LANGUAGE_CONFIG.items():
        exe = cfg.get("cmd", cfg.get("compile", ["?"]))[0]
        if exe == "?" or exe in ["{file}", "{out}"]:
            continue
        key = (lang, exe)
        if key in seen:
            continue
        seen.add(key)
        if shutil.which(exe):
            available.append(f"✅ {lang} ({exe})")
        else:
            unavailable.append(f"❌ {lang} ({exe} nicht installiert)")

    result = "**Verfügbare Sprachen:**\n" + "\n".join(available)
    if unavailable:
        result += "\n\n**Nicht installiert:**\n" + "\n".join(unavailable[:10])
    return result
