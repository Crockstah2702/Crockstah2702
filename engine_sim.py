"""
Realistic engine & transmission simulation.

Based loosely on a high-performance sports sedan (≈300 HP):
  - Torque curve modelled via cubic interpolation over measured points
  - 6-speed manual (auto-shift optional)
  - Clutch model with slip
  - Engine damage: overrev, overtemp
"""
import math
import numpy as np
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Torque curve  (rpm, Nm)  – resembles a BMW M3 E46 S54
# ---------------------------------------------------------------------------
TORQUE_POINTS: List[Tuple[float, float]] = [
    (  800,  180),
    ( 1500,  280),
    ( 2500,  320),
    ( 3500,  360),
    ( 4000,  370),   # peak torque
    ( 4500,  365),
    ( 5000,  355),
    ( 6000,  330),
    ( 7000,  295),
    ( 7900,  210),
    ( 8200,    0),   # redline / cutoff
]

_RPM_CURVE  = np.array([p[0] for p in TORQUE_POINTS], dtype=np.float64)
_NM_CURVE   = np.array([p[1] for p in TORQUE_POINTS], dtype=np.float64)


def torque_at_rpm(rpm: float) -> float:
    """Linearly-interpolated torque [Nm] from the engine curve."""
    return float(np.interp(rpm, _RPM_CURVE, _NM_CURVE))


# ---------------------------------------------------------------------------
# Gear ratios  (6-speed manual + final drive)
# ---------------------------------------------------------------------------
GEAR_RATIOS   = [0.0, 3.82, 2.20, 1.52, 1.22, 1.02, 0.84]  # index 0 = neutral
FINAL_DRIVE   = 3.73
REVERSE_RATIO = -3.50


class EngineSim:
    IDLE_RPM    = 900.0
    REDLINE_RPM = 8100.0
    MAX_RPM     = 8200.0   # fuel cut

    # Engine inertia – how quickly RPM changes
    INERTIA     = 0.25     # kg·m²

    # Friction torque (drag / pumping losses)
    FRICTION_K  = 0.015    # Nm per RPM

    def __init__(self):
        self.rpm:         float = self.IDLE_RPM
        self.gear:        int   = 1
        self.throttle:    float = 0.0    # 0–1
        self.clutch:      float = 1.0    # 1 = fully engaged, 0 = disengaged
        self.wheel_rpm:   float = 0.0    # driven-wheel RPM (feedback)

        self.running:     bool  = True
        self.temperature: float = 90.0   # °C
        self.damage:      float = 0.0    # 0–1

        # state for auto-shift
        self._shift_cooldown: float = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def gear_ratio(self) -> float:
        if self.gear == 0:
            return 0.0
        if self.gear == -1:
            return REVERSE_RATIO
        return GEAR_RATIOS[self.gear] * FINAL_DRIVE

    @property
    def max_gear(self) -> int:
        return len(GEAR_RATIOS) - 1

    @property
    def speed_factor(self) -> float:
        """RPM per (wheel rad/s) – converts wheel spin to engine spin."""
        return abs(self.gear_ratio) * 30.0 / math.pi  # wheel_rps → engine_rpm

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, dt: float, wheel_angular_vel: float):
        """
        dt               – timestep [s]
        wheel_angular_vel – driven wheel angular velocity [rad/s]
        """
        if not self.running:
            self.rpm = 0.0
            return

        self._shift_cooldown = max(0.0, self._shift_cooldown - dt)

        # Target RPM dictated by wheel speed (when clutch engaged)
        if self.gear != 0 and abs(self.gear_ratio) > 0.01:
            engaged_rpm = abs(wheel_angular_vel) * self.speed_factor
        else:
            engaged_rpm = self.IDLE_RPM

        # Clutch blending
        target_rpm = self.rpm + self.clutch * (engaged_rpm - self.rpm)

        # Engine torque from throttle + curve
        raw_torque  = torque_at_rpm(self.rpm) * self.throttle
        # Friction / drag
        drag_torque = self.FRICTION_K * self.rpm + 5.0
        net_torque  = raw_torque - drag_torque

        # Idle: prevent stall
        if self.rpm < self.IDLE_RPM and self.throttle < 0.05:
            net_torque += (self.IDLE_RPM - self.rpm) * 0.5

        # RPM integration
        d_rpm = (net_torque / self.INERTIA) * dt * 60.0 / (2 * math.pi)
        self.rpm = max(self.IDLE_RPM * 0.5,
                       min(self.MAX_RPM, self.rpm + d_rpm))

        # Fuel cut above redline
        if self.rpm >= self.MAX_RPM:
            self.rpm = self.MAX_RPM * 0.995

        # Temperature model
        heat = self.throttle * 0.8 + 0.2
        cool = 0.05 * max(0.0, abs(wheel_angular_vel) * 0.1 - 0.2)  # speed cooling
        self.temperature += (heat - cool - 0.02 * (self.temperature - 20.0)) * dt * 10.0
        self.temperature = max(20.0, self.temperature)

        # Damage from overrev or overtemp
        if self.rpm > self.REDLINE_RPM:
            overrev = (self.rpm - self.REDLINE_RPM) / (self.MAX_RPM - self.REDLINE_RPM)
            self.damage += overrev * dt * 0.05
        if self.temperature > 115.0:
            self.damage += (self.temperature - 115.0) * dt * 0.002

        self.damage = min(1.0, self.damage)

    # ------------------------------------------------------------------
    # Torque delivered to wheels
    # ------------------------------------------------------------------

    def get_wheel_torque(self) -> float:
        """Torque at driven wheels [Nm]."""
        if not self.running or self.gear == 0:
            return 0.0
        t = torque_at_rpm(self.rpm) * self.throttle * self.clutch
        # Reduce torque when engine is damaged
        t *= (1.0 - self.damage * 0.7)
        return t * abs(self.gear_ratio)

    # ------------------------------------------------------------------
    # Manual gearshift
    # ------------------------------------------------------------------

    def shift_up(self):
        if self._shift_cooldown > 0:
            return
        if self.gear < self.max_gear:
            self.gear += 1
            self._shift_cooldown = 0.25
            # Rev-match drop
            self.rpm = max(self.IDLE_RPM,
                           self.rpm * (GEAR_RATIOS[self.gear] /
                                       GEAR_RATIOS[max(1, self.gear - 1)]))

    def shift_down(self):
        if self._shift_cooldown > 0:
            return
        if self.gear > 1:
            self.gear -= 1
            self._shift_cooldown = 0.25
            # Rev-match blip
            self.rpm = min(self.MAX_RPM * 0.95,
                           self.rpm * (GEAR_RATIOS[self.gear] /
                                       GEAR_RATIOS[min(self.max_gear, self.gear + 1)]))

    def shift_reverse(self):
        self.gear = -1

    def shift_neutral(self):
        self.gear = 0

    # ------------------------------------------------------------------
    # Auto-shift helper (call from vehicle update if auto mode)
    # ------------------------------------------------------------------

    def auto_shift(self, speed_kmh: float):
        """Simple automatic transmission logic."""
        if self._shift_cooldown > 0:
            return
        UPSHIFT   = [0, 30, 55, 85, 120, 155, 999]  # km/h per gear
        DOWNSHIFT  = [0,  0, 20, 45,  75, 105, 130]

        if self.gear < self.max_gear and speed_kmh > UPSHIFT[self.gear]:
            self.shift_up()
        elif self.gear > 1 and speed_kmh < DOWNSHIFT[self.gear]:
            self.shift_down()

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------

    def debug_str(self) -> str:
        return (f"G{self.gear:+d}  {self.rpm:5.0f}RPM  "
                f"{self.temperature:4.0f}°C  dmg={self.damage:.2f}")
