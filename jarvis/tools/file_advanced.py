"""Erweiterte Datei-Tools: PDF, CSV, Excel, ZIP, Bildkonvertierung."""
import logging
import os
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def read_pdf(path: str, pages: str = "all") -> str:
    """Lese Text aus einer PDF-Datei."""
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"❌ Datei nicht gefunden: {path}"
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(str(p)) as pdf:
            total = len(pdf.pages)
            if pages == "all":
                page_range = pdf.pages
            else:
                # z.B. "1-5" oder "3"
                if "-" in str(pages):
                    start, end = pages.split("-")
                    page_range = pdf.pages[int(start)-1:int(end)]
                else:
                    page_range = [pdf.pages[int(pages)-1]]
            for i, page in enumerate(page_range):
                t = page.extract_text()
                if t:
                    text_parts.append(f"--- Seite {i+1} ---\n{t}")
        full = "\n\n".join(text_parts)
        if len(full) > 8000:
            full = full[:8000] + "\n\n[... PDF abgeschnitten ...]"
        return f"PDF: {p.name} ({total} Seiten)\n\n{full}"
    except ImportError:
        return "❌ pdfplumber nicht installiert: pip install pdfplumber"
    except Exception as e:
        return f"❌ PDF-Fehler: {e}"


def read_csv(path: str, rows: int = 50) -> str:
    """Lese eine CSV- oder Excel-Datei."""
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"❌ Datei nicht gefunden: {path}"
    try:
        import pandas as pd
        ext = p.suffix.lower()
        if ext in [".xlsx", ".xls", ".xlsm"]:
            df = pd.read_excel(str(p))
        else:
            # CSV: versuche verschiedene Trennzeichen
            for sep in [",", ";", "\t", "|"]:
                try:
                    df = pd.read_csv(str(p), sep=sep, nrows=rows)
                    if len(df.columns) > 1:
                        break
                except Exception:
                    continue
        total_rows = len(df)
        preview = df.head(rows).to_string(index=True)
        return (f"Datei: {p.name} | {total_rows} Zeilen, {len(df.columns)} Spalten\n"
                f"Spalten: {', '.join(df.columns.tolist())}\n\n{preview}")
    except ImportError:
        return "❌ pandas nicht installiert: pip install pandas openpyxl"
    except Exception as e:
        return f"❌ Fehler: {e}"


def write_csv(path: str, data: list, headers: list = None) -> str:
    """Schreibe Daten in eine CSV-Datei."""
    import csv
    p = Path(os.path.expanduser(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(str(p), "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if headers:
                writer.writerow(headers)
            writer.writerows(data)
        return f"✅ CSV gespeichert: {p} ({len(data)} Zeilen)"
    except Exception as e:
        return f"❌ Fehler: {e}"


def zip_create(files: list, output_path: str) -> str:
    """Erstelle ein ZIP-Archiv aus einer Liste von Dateien."""
    out = Path(os.path.expanduser(output_path))
    if not out.suffix:
        out = out.with_suffix(".zip")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        added = []
        with zipfile.ZipFile(str(out), "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                fp = Path(os.path.expanduser(f))
                if fp.exists():
                    zf.write(str(fp), fp.name)
                    added.append(fp.name)
                else:
                    logger.warning(f"Datei nicht gefunden: {f}")
        return f"✅ ZIP erstellt: {out}\n   Enthält: {', '.join(added)}"
    except Exception as e:
        return f"❌ ZIP-Fehler: {e}"


def zip_extract(zip_path: str, destination: str = "") -> str:
    """Entpacke ein ZIP-Archiv."""
    zp = Path(os.path.expanduser(zip_path))
    if not zp.exists():
        return f"❌ ZIP-Datei nicht gefunden: {zip_path}"
    dest = Path(os.path.expanduser(destination)) if destination else zp.parent / zp.stem
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(str(zp), "r") as zf:
            zf.extractall(str(dest))
            names = zf.namelist()
        return f"✅ Entpackt nach: {dest}\n   {len(names)} Dateien: {', '.join(names[:10])}"
    except Exception as e:
        return f"❌ Entpack-Fehler: {e}"


def zip_list(zip_path: str) -> str:
    """Zeige den Inhalt eines ZIP-Archivs."""
    zp = Path(os.path.expanduser(zip_path))
    if not zp.exists():
        return f"❌ Nicht gefunden: {zip_path}"
    try:
        with zipfile.ZipFile(str(zp), "r") as zf:
            infos = zf.infolist()
        lines = [f"  {info.filename} ({info.file_size:,} B)" for info in infos[:50]]
        return f"ZIP: {zp.name} ({len(infos)} Dateien)\n" + "\n".join(lines)
    except Exception as e:
        return f"❌ Fehler: {e}"


def convert_image(input_path: str, output_path: str, format: str = "") -> str:
    """Konvertiere oder bearbeite ein Bild."""
    try:
        from PIL import Image
        inp = Path(os.path.expanduser(input_path))
        out = Path(os.path.expanduser(output_path))
        out.parent.mkdir(parents=True, exist_ok=True)
        if not format:
            format = out.suffix.lstrip(".").upper() or "PNG"
        img = Image.open(str(inp))
        img.save(str(out), format=format)
        return f"✅ Bild konvertiert: {inp.name} → {out.name} ({img.size[0]}x{img.size[1]})"
    except ImportError:
        return "❌ Pillow nicht installiert: pip install pillow"
    except Exception as e:
        return f"❌ Fehler: {e}"


def resize_image(path: str, width: int, height: int, output: str = "") -> str:
    """Ändere die Größe eines Bildes."""
    try:
        from PIL import Image
        inp = Path(os.path.expanduser(path))
        out = Path(os.path.expanduser(output)) if output else inp.parent / f"{inp.stem}_resized{inp.suffix}"
        img = Image.open(str(inp))
        resized = img.resize((int(width), int(height)), Image.LANCZOS)
        resized.save(str(out))
        return f"✅ Größe geändert: {inp.name} → {width}x{height}px → {out.name}"
    except ImportError:
        return "❌ Pillow nicht installiert"
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_file_info(path: str) -> str:
    """Zeige detaillierte Informationen über eine Datei."""
    import datetime
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"❌ Nicht gefunden: {path}"
    try:
        stat = p.stat()
        size = stat.st_size
        if size > 1024*1024*1024:
            size_str = f"{size/(1024**3):.2f} GB"
        elif size > 1024*1024:
            size_str = f"{size/(1024**2):.2f} MB"
        elif size > 1024:
            size_str = f"{size/1024:.2f} KB"
        else:
            size_str = f"{size} B"
        modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M:%S")
        created = datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%d.%m.%Y %H:%M:%S")
        return (f"📄 {p.name}\n"
                f"  Pfad: {p.absolute()}\n"
                f"  Größe: {size_str}\n"
                f"  Typ: {'Verzeichnis' if p.is_dir() else p.suffix or 'Datei'}\n"
                f"  Geändert: {modified}\n"
                f"  Erstellt: {created}")
    except Exception as e:
        return f"❌ Fehler: {e}"
