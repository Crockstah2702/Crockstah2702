"""
HUD – on-screen instrument cluster rendered with Panda2D (DirectGui + canvas).

Displays:
  • Analogue speedometer (arc gauge)
  • Analogue tachometer / RPM gauge (arc gauge)
  • Gear indicator
  • Damage silhouette (6-zone colour map)
  • Engine temperature & status
  • Mini-map placeholder
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from panda3d.core import (
    NodePath, Vec3, Vec4, LColor,
    CardMaker, TextNode,
    TransparencyAttrib,
)
from direct.gui.DirectGui import (
    DirectFrame, DirectLabel,
)
from direct.gui.OnscreenText import OnscreenText

if TYPE_CHECKING:
    from vehicle import Vehicle
    from engine_sim import EngineSim


# ---------------------------------------------------------------------------
# Arc gauge helper
# ---------------------------------------------------------------------------

def _arc_positions(cx: float, cy: float, radius: float,
                   val: float, lo: float, hi: float,
                   start_deg: float = 220.0, sweep_deg: float = -260.0):
    """Return (tip_x, tip_y) for a gauge needle."""
    t     = (val - lo) / max(hi - lo, 1e-6)
    t     = max(0.0, min(1.0, t))
    angle = math.radians(start_deg + sweep_deg * t)
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


# ---------------------------------------------------------------------------
# OnscreenCanvas arc gauge
# ---------------------------------------------------------------------------

class ArcGauge:
    """Simple arc gauge drawn with OnscreenText ticks + needle."""

    def __init__(self, aspect2d: NodePath,
                 pos: tuple, size: float,
                 lo: float, hi: float,
                 label: str,
                 ticks: list,
                 color: tuple = (1, 1, 1, 1),
                 redline: float | None = None):
        self.lo, self.hi = lo, hi
        self.cx, self.cy = pos
        self.r = size
        self.redline = redline
        self._aspect2d = aspect2d

        # Background circle label
        self._label = OnscreenText(
            text=label, pos=(self.cx, self.cy - size*1.15),
            scale=size*0.22, fg=color, align=TextNode.ACenter,
            parent=aspect2d, mayChange=False,
        )

        # Tick marks
        self._ticks_text = []
        for val, txt in ticks:
            tx, ty = _arc_positions(self.cx, self.cy, size*0.75, val, lo, hi)
            t = OnscreenText(
                text=txt, pos=(tx, ty),
                scale=size*0.13, fg=(0.8, 0.8, 0.8, 1.0),
                align=TextNode.ACenter,
                parent=aspect2d, mayChange=False,
            )
            self._ticks_text.append(t)

        # Value display (digital readout inside gauge)
        self._value_text = OnscreenText(
            text="0", pos=(self.cx, self.cy - size*0.3),
            scale=size*0.18, fg=(0.9, 1.0, 0.9, 1.0),
            align=TextNode.ACenter,
            parent=aspect2d, mayChange=True,
        )

        # Needle (thin card that we rotate)
        cm = CardMaker("needle")
        cm.setFrame(-size*0.04, size*0.04, 0, size*0.68)
        self._needle_np = aspect2d.attachNewNode(cm.generate())
        self._needle_np.setPos(self.cx, 0, self.cy)
        self._needle_np.setColor(*color)
        self._needle_np.setTransparency(TransparencyAttrib.MAlpha)
        self._needle_np.setAlphaScale(0.9)

        self.update(lo)

    def update(self, val: float):
        t     = (val - self.lo) / max(self.hi - self.lo, 1e-6)
        t     = max(0.0, min(1.0, t))
        angle = 220.0 - 260.0 * t     # degrees  (Panda2D: -H rotates)
        self._needle_np.setR(-angle)

        self._value_text.setText(f"{val:.0f}")

        # Red tint near redline
        if self.redline and val > self.redline:
            frac = min(1.0, (val - self.redline) / (self.hi - self.redline))
            self._needle_np.setColor(1.0, 1.0*(1-frac), 1.0*(1-frac), 0.9)
        else:
            self._needle_np.setColor(1.0, 1.0, 1.0, 0.9)


# ---------------------------------------------------------------------------
# Damage display (car silhouette, 6 zones)
# ---------------------------------------------------------------------------

class DamageDisplay:
    ZONE_LABELS = ["Front", "Rear", "Left", "Right", "Roof", "Floor"]

    def __init__(self, aspect2d: NodePath, pos: tuple):
        self.cx, self.cy = pos
        self._texts = []
        for i, lbl in enumerate(self.ZONE_LABELS):
            # Layout in 2 columns
            col  = i % 2
            row  = i // 2
            tx   = self.cx + (-0.12 + col*0.24)
            ty   = self.cy + (0.08  - row*0.065)
            t    = OnscreenText(
                text=f"{lbl}: 0%", pos=(tx, ty),
                scale=0.038, fg=(0.2, 1.0, 0.2, 1.0),
                align=TextNode.ALeft,
                parent=aspect2d, mayChange=True,
            )
            self._texts.append(t)

        OnscreenText(
            text="DAMAGE", pos=(self.cx, self.cy + 0.13),
            scale=0.05, fg=(1.0, 0.6, 0.0, 1.0),
            align=TextNode.ACenter,
            parent=aspect2d, mayChange=False,
        )

    def update(self, zone_damage):
        for i, (t, lbl) in enumerate(zip(self._texts, self.ZONE_LABELS)):
            d    = float(zone_damage[i])
            pct  = int(d * 100)
            if d < 0.25:
                col = (0.2, 1.0, 0.2, 1.0)
            elif d < 0.6:
                col = (1.0, 0.8, 0.0, 1.0)
            else:
                col = (1.0, 0.15, 0.15, 1.0)
            t.setText(f"{lbl}: {pct}%")
            t.setFg(col)


# ---------------------------------------------------------------------------
# Main HUD
# ---------------------------------------------------------------------------

class HUD:
    def __init__(self, aspect2d: NodePath):
        self._a2d = aspect2d

        # ---- Speedometer  (bottom left) -----------------------------------
        spd_ticks = [(v, str(v)) for v in range(0, 281, 40)]
        self.speedo = ArcGauge(
            aspect2d, pos=(-1.35, -0.55), size=0.30,
            lo=0, hi=280, label="km/h",
            ticks=spd_ticks,
            color=(0.9, 0.95, 1.0, 1.0),
        )

        # ---- Tachometer  (bottom right) -----------------------------------
        rpm_ticks = [(v*1000, str(v)) for v in range(0, 9)]
        self.tacho = ArcGauge(
            aspect2d, pos=(1.35, -0.55), size=0.30,
            lo=0, hi=8200, label="x1000 RPM",
            ticks=rpm_ticks,
            color=(1.0, 0.85, 0.7, 1.0),
            redline=7500,
        )

        # ---- Gear indicator  (center bottom) ------------------------------
        self._gear_text = OnscreenText(
            text="1", pos=(0.0, -0.72),
            scale=0.15, fg=(1.0, 1.0, 0.0, 1.0),
            shadow=(0, 0, 0, 0.8), shadowOffset=(0.005, 0.005),
            align=TextNode.ACenter,
            parent=aspect2d, mayChange=True,
        )
        OnscreenText(
            text="GEAR", pos=(0.0, -0.58),
            scale=0.04, fg=(0.7, 0.7, 0.7, 1.0),
            align=TextNode.ACenter,
            parent=aspect2d, mayChange=False,
        )

        # ---- Engine info  (top left) -------------------------------------
        self._engine_text = OnscreenText(
            text="", pos=(-1.6, 0.88),
            scale=0.040, fg=(0.85, 0.95, 0.85, 1.0),
            align=TextNode.ALeft,
            parent=aspect2d, mayChange=True,
        )

        # ---- Damage display  (top right) ----------------------------------
        self.damage_display = DamageDisplay(aspect2d, pos=(1.42, 0.72))

        # ---- Speed numeric  (center top) ----------------------------------
        self._speed_num = OnscreenText(
            text="0 km/h", pos=(0, 0.88),
            scale=0.065, fg=(1.0, 1.0, 1.0, 1.0),
            shadow=(0, 0, 0, 0.7), shadowOffset=(0.003, 0.003),
            align=TextNode.ACenter,
            parent=aspect2d, mayChange=True,
        )

        # ---- Notification text  (center middle) ---------------------------
        self._notif_text = OnscreenText(
            text="", pos=(0, 0.2),
            scale=0.07, fg=(1.0, 0.9, 0.0, 1.0),
            shadow=(0, 0, 0, 0.8), shadowOffset=(0.004, 0.004),
            align=TextNode.ACenter,
            parent=aspect2d, mayChange=True,
        )
        self._notif_timer = 0.0

        # ---- Controls help  (small, bottom center) -----------------------
        OnscreenText(
            text="PS5: [R2] Gas  [L2] Bremse  [L-Stick] Lenken  [R1/L1] Gang  [[^]] Reset  [Touchpad] Kamera"
                 "    |    Tastatur: W/S Gas/Bremse  A/D Lenken  E/Q Gang  R Reset  C Kamera"
                 "    |    Maus: RMB = Kamera-Orbit  Scroll = Zoom",
            pos=(0, -0.95), scale=0.027,
            fg=(0.50, 0.50, 0.50, 1.0),
            align=TextNode.ACenter,
            parent=aspect2d, mayChange=False,
        )

    # ------------------------------------------------------------------
    def update(self, dt: float, vehicle, engine):
        speed_kmh = vehicle.get_speed_kmh()
        self.speedo.update(speed_kmh)
        self.tacho.update(engine.rpm)

        # Gear
        gear = engine.gear
        gear_str = str(gear) if gear > 0 else ("R" if gear == -1 else "N")
        self._gear_text.setText(gear_str)

        # Speed numeric
        self._speed_num.setText(f"{speed_kmh:.0f} km/h")

        # Engine info
        lines = [
            f"RPM  : {engine.rpm:5.0f}",
            f"Temp : {engine.temperature:.0f}°C",
            f"Dmg  : {engine.damage*100:.0f}%",
            f"Gear : {gear_str}",
        ]
        if engine.damage > 0.5:
            lines.append("(!) ENGINE DAMAGE")
        if engine.temperature > 105:
            lines.append("(!) OVERHEATING")
        self._engine_text.setText("\n".join(lines))

        # Damage zones
        self.damage_display.update(vehicle.soft.zone_damage)

        # Notification countdown
        if self._notif_timer > 0:
            self._notif_timer -= dt
            if self._notif_timer <= 0:
                self._notif_text.setText("")

    def notify(self, msg: str, duration: float = 2.5):
        self._notif_text.setText(msg)
        self._notif_timer = duration
