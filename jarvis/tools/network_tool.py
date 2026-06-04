"""Netzwerk-Tools: HTTP-Anfragen, Ping, IP-Infos, Port-Scan."""
import asyncio
import json
import logging
import socket
import subprocess
import platform

logger = logging.getLogger(__name__)


def http_get(url: str, headers: dict = None) -> str:
    """Führe eine HTTP GET-Anfrage durch."""
    try:
        import requests
        resp = requests.get(url, headers=headers or {}, timeout=15)
        ct = resp.headers.get("Content-Type", "")
        if "json" in ct:
            try:
                return json.dumps(resp.json(), ensure_ascii=False, indent=2)[:3000]
            except Exception:
                pass
        text = resp.text[:3000]
        return f"Status: {resp.status_code}\n{text}"
    except Exception as e:
        return f"❌ HTTP GET Fehler: {e}"


def http_post(url: str, data: dict = None, json_data: dict = None,
              headers: dict = None) -> str:
    """Führe eine HTTP POST-Anfrage durch."""
    try:
        import requests
        resp = requests.post(
            url,
            data=data,
            json=json_data,
            headers=headers or {},
            timeout=15
        )
        ct = resp.headers.get("Content-Type", "")
        if "json" in ct:
            try:
                return json.dumps(resp.json(), ensure_ascii=False, indent=2)[:3000]
            except Exception:
                pass
        return f"Status: {resp.status_code}\n{resp.text[:2000]}"
    except Exception as e:
        return f"❌ HTTP POST Fehler: {e}"


def ping_host(host: str, count: int = 4) -> str:
    """Pinge einen Host an."""
    sys_os = platform.system()
    try:
        if sys_os == "Windows":
            args = ["ping", "-n", str(count), host]
        else:
            args = ["ping", "-c", str(count), "-W", "2", host]
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        output = result.stdout or result.stderr
        if result.returncode == 0:
            return f"✅ Ping an {host}:\n{output}"
        return f"❌ Host nicht erreichbar: {host}\n{output}"
    except subprocess.TimeoutExpired:
        return f"❌ Timeout beim Ping an {host}"
    except Exception as e:
        return f"❌ Fehler: {e}"


def check_port(host: str, port: int, timeout: float = 3.0) -> str:
    """Prüfe ob ein Port auf einem Host offen ist."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        if result == 0:
            return f"✅ Port {port} auf {host} ist OFFEN"
        return f"❌ Port {port} auf {host} ist GESCHLOSSEN"
    except Exception as e:
        return f"❌ Fehler: {e}"


def get_network_info() -> str:
    """Zeige Netzwerk-Informationen: IP, DNS, aktive Verbindungen."""
    info_parts = []
    try:
        import psutil
        # Netzwerk-Interfaces
        interfaces = psutil.net_if_addrs()
        for name, addrs in interfaces.items():
            for addr in addrs:
                if addr.family == socket.AF_INET and addr.address != "127.0.0.1":
                    info_parts.append(f"  {name}: {addr.address}")

        # Öffentliche IP
        try:
            import requests
            resp = requests.get("https://api.ipify.org?format=json", timeout=5)
            public_ip = resp.json().get("ip", "unbekannt")
            info_parts.append(f"  Öffentliche IP: {public_ip}")
        except Exception:
            pass

        # Netzwerk-Statistiken
        stats = psutil.net_io_counters()
        info_parts.append(
            f"  Gesendet: {stats.bytes_sent/(1024**2):.1f} MB | "
            f"Empfangen: {stats.bytes_recv/(1024**2):.1f} MB"
        )
    except ImportError:
        # Fallback ohne psutil
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        info_parts.append(f"  Hostname: {hostname}")
        info_parts.append(f"  Lokale IP: {local_ip}")

    return "Netzwerk-Information:\n" + "\n".join(info_parts)


def get_public_ip() -> str:
    """Gibt die öffentliche IP-Adresse zurück."""
    try:
        import requests
        resp = requests.get("https://api.ipify.org?format=json", timeout=8)
        ip = resp.json().get("ip", "unbekannt")
        # Geo-Info
        geo = requests.get(f"https://ipapi.co/{ip}/json/", timeout=5).json()
        country = geo.get("country_name", "")
        city = geo.get("city", "")
        isp = geo.get("org", "")
        return f"Öffentliche IP: {ip}\nStandort: {city}, {country}\nProvider: {isp}"
    except Exception as e:
        return f"❌ Fehler: {e}"


def dns_lookup(hostname: str) -> str:
    """Führe eine DNS-Abfrage durch."""
    try:
        ip = socket.gethostbyname(hostname)
        # Reverse lookup
        try:
            reverse = socket.gethostbyaddr(ip)[0]
        except Exception:
            reverse = "(kein Reverse-DNS)"
        return f"DNS-Auflösung für {hostname}:\n  IP: {ip}\n  Reverse: {reverse}"
    except Exception as e:
        return f"❌ DNS-Fehler: {e}"


def scan_local_network(subnet: str = "") -> str:
    """Scanne das lokale Netzwerk nach aktiven Geräten (einfacher Ping-Scan)."""
    if not subnet:
        # Eigene IP herausfinden
        try:
            import psutil
            for name, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if hasattr(socket, 'AF_INET') and addr.family == socket.AF_INET:
                        if not addr.address.startswith("127."):
                            parts = addr.address.rsplit(".", 1)
                            subnet = parts[0]
                            break
                if subnet:
                    break
        except Exception:
            pass
        if not subnet:
            return "❌ Subnetz konnte nicht ermittelt werden. Gib es manuell an (z.B. '192.168.1')"

    active = []
    sys_os = platform.system()
    for i in range(1, 255):
        ip = f"{subnet}.{i}"
        if sys_os == "Windows":
            args = ["ping", "-n", "1", "-w", "100", ip]
        else:
            args = ["ping", "-c", "1", "-W", "1", ip]
        try:
            result = subprocess.run(args, capture_output=True, timeout=2)
            if result.returncode == 0:
                try:
                    name = socket.gethostbyaddr(ip)[0]
                except Exception:
                    name = "(kein Name)"
                active.append(f"  {ip} — {name}")
        except Exception:
            continue

    if active:
        return f"Aktive Geräte im Netzwerk ({subnet}.x):\n" + "\n".join(active)
    return f"Keine aktiven Geräte in {subnet}.x gefunden"
