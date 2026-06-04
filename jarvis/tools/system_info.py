"""System information and monitoring tool."""
import logging
import os
import platform
from datetime import datetime

logger = logging.getLogger(__name__)


def get_system_info() -> str:
    """Get comprehensive system information."""
    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        disk_parts = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_parts.append(
                    f"  {part.mountpoint}: {usage.used/1e9:.1f}/{usage.total/1e9:.1f} GB "
                    f"({usage.percent}% genutzt)"
                )
            except Exception:
                pass

        net = psutil.net_io_counters()
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time

        info = [
            f"**System:** {platform.system()} {platform.release()} ({platform.machine()})",
            f"**CPU:** {cpu_percent}% Last | {cpu_count} Kerne",
            f"  Frequenz: {cpu_freq.current:.0f} MHz" if cpu_freq else "",
            f"**RAM:** {mem.used/1e9:.1f}/{mem.total/1e9:.1f} GB ({mem.percent}% genutzt)",
            f"**Swap:** {swap.used/1e9:.1f}/{swap.total/1e9:.1f} GB",
            f"**Festplatten:**",
            *disk_parts,
            f"**Netzwerk:** ↑{net.bytes_sent/1e6:.1f} MB | ↓{net.bytes_recv/1e6:.1f} MB",
            f"**Uptime:** {str(uptime).split('.')[0]}",
            f"**Python:** {platform.python_version()}",
        ]
        return "\n".join(l for l in info if l)

    except ImportError:
        return f"System: {platform.system()} {platform.release()}\npsutil nicht installiert."
    except Exception as e:
        return f"Fehler beim Lesen der Systeminfo: {e}"


def get_top_processes(n: int = 10) -> str:
    """Get top N processes by CPU usage."""
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except Exception:
                pass

        # Sort by CPU
        procs.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
        lines = [f"{'PID':>6} {'Name':<25} {'CPU%':>6} {'RAM%':>6}"]
        lines.append("-" * 48)
        for p in procs[:n]:
            lines.append(
                f"{p['pid']:>6} {(p['name'] or '?'):<25} "
                f"{p['cpu_percent']:>5.1f}% {p['memory_percent']:>5.1f}%"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Fehler: {e}"


def get_battery_status() -> str:
    """Get battery status if available."""
    try:
        import psutil
        battery = psutil.sensors_battery()
        if not battery:
            return "Keine Batterie erkannt (Desktop-PC)."
        status = "Wird geladen" if battery.power_plugged else "Im Akkubetrieb"
        secs_left = battery.secsleft
        if secs_left > 0:
            h, m = divmod(secs_left // 60, 60)
            time_str = f"{h}h {m}min verbleibend"
        else:
            time_str = "Wird geladen..."
        return f"Batterie: {battery.percent:.0f}% | {status} | {time_str}"
    except Exception as e:
        return f"Batteriestatus nicht verfügbar: {e}"
