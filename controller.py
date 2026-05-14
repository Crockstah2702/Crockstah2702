"""
PS5 DualSense controller input handler with keyboard fallback.
"""
import pygame
import math


class PS5Controller:
    # DualSense axis indices (Linux hidraw / SDL2)
    AXIS_LEFT_X  = 0   # steering
    AXIS_LEFT_Y  = 1
    AXIS_RIGHT_X = 2
    AXIS_RIGHT_Y = 3
    AXIS_L2      = 4   # brake    (−1 released → +1 fully pressed)
    AXIS_R2      = 5   # throttle (−1 released → +1 fully pressed)

    BTN_CROSS     = 0
    BTN_CIRCLE    = 1
    BTN_SQUARE    = 2
    BTN_TRIANGLE  = 3
    BTN_L1        = 4
    BTN_R1        = 5
    BTN_L2        = 6
    BTN_R2        = 7
    BTN_SHARE     = 8
    BTN_OPTIONS   = 9
    BTN_L3        = 10
    BTN_R3        = 11
    BTN_PS        = 12
    BTN_TOUCHPAD  = 13

    DEADZONE = 0.06

    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.joystick: pygame.joystick.JoystickType | None = None
        self.connected = False
        self._prev_buttons: dict[int, bool] = {}
        self._find_controller()

    # ------------------------------------------------------------------
    def _find_controller(self):
        keywords = ("dualsense", "ps5", "wireless controller", "sony")
        for i in range(pygame.joystick.get_count()):
            js = pygame.joystick.Joystick(i)
            js.init()
            name = js.get_name().lower()
            if any(k in name for k in keywords):
                self.joystick = js
                self.connected = True
                print(f"[Controller] DualSense verbunden: {js.get_name()}")
                return
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.connected = True
            print(f"[Controller] Gamepad verbunden: {self.joystick.get_name()}")
        else:
            print("[Controller] Kein Controller gefunden – Tastatur aktiv.")

    # ------------------------------------------------------------------
    def update(self):
        """Call every frame to pump pygame events."""
        pygame.event.pump()

    # ------------------------------------------------------------------
    def _axis(self, idx: int, default: float = 0.0) -> float:
        if not self.connected:
            return default
        try:
            return self.joystick.get_axis(idx)
        except Exception:
            return default

    def _btn(self, idx: int) -> bool:
        if not self.connected:
            return False
        try:
            return bool(self.joystick.get_button(idx))
        except Exception:
            return False

    @staticmethod
    def _deadzone(val: float, dz: float = 0.06) -> float:
        if abs(val) < dz:
            return 0.0
        sign = 1.0 if val > 0 else -1.0
        return sign * (abs(val) - dz) / (1.0 - dz)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_steering(self) -> float:
        """−1.0 (full left) … +1.0 (full right)."""
        return self._deadzone(self._axis(self.AXIS_LEFT_X))

    def get_throttle(self) -> float:
        """0.0 … 1.0  (R2 trigger)."""
        raw = (self._axis(self.AXIS_R2, -1.0) + 1.0) / 2.0
        return max(0.0, min(1.0, raw))

    def get_brake(self) -> float:
        """0.0 … 1.0  (L2 trigger)."""
        raw = (self._axis(self.AXIS_L2, -1.0) + 1.0) / 2.0
        return max(0.0, min(1.0, raw))

    def get_handbrake(self) -> bool:
        return self._btn(self.BTN_CIRCLE)

    def get_shift_up(self) -> bool:
        return self._btn(self.BTN_R1)

    def get_shift_down(self) -> bool:
        return self._btn(self.BTN_L1)

    def get_reset(self) -> bool:
        return self._btn(self.BTN_TRIANGLE)

    def get_camera_toggle(self) -> bool:
        return self._btn(self.BTN_TOUCHPAD)

    def get_pause(self) -> bool:
        return self._btn(self.BTN_OPTIONS)

    def just_pressed(self, btn_idx: int) -> bool:
        """True only on the first frame the button is down."""
        current = self._btn(btn_idx)
        was = self._prev_buttons.get(btn_idx, False)
        self._prev_buttons[btn_idx] = current
        return current and not was

    def shift_up_just(self) -> bool:
        return self.just_pressed(self.BTN_R1)

    def shift_down_just(self) -> bool:
        return self.just_pressed(self.BTN_L1)

    def reset_just(self) -> bool:
        return self.just_pressed(self.BTN_TRIANGLE)

    def camera_just(self) -> bool:
        return self.just_pressed(self.BTN_TOUCHPAD)


class KeyboardController:
    """Fallback keyboard control using Panda3D's key-map."""

    def __init__(self, key_map: dict):
        # key_map is a dict[str, bool] maintained by the game
        self.km = key_map
        self._prev: dict[str, bool] = {}

    def update(self):
        pass

    def get_steering(self) -> float:
        left  = float(self.km.get("arrow_left",  False) or self.km.get("a", False))
        right = float(self.km.get("arrow_right", False) or self.km.get("d", False))
        return right - left

    def get_throttle(self) -> float:
        return float(self.km.get("arrow_up", False) or self.km.get("w", False))

    def get_brake(self) -> float:
        return float(self.km.get("arrow_down", False) or self.km.get("s", False))

    def get_handbrake(self) -> bool:
        return bool(self.km.get("space", False))

    def get_shift_up(self) -> bool:
        return bool(self.km.get("e", False))

    def get_shift_down(self) -> bool:
        return bool(self.km.get("q", False))

    def get_reset(self) -> bool:
        return bool(self.km.get("r", False))

    def get_camera_toggle(self) -> bool:
        return bool(self.km.get("c", False))

    def get_pause(self) -> bool:
        return bool(self.km.get("escape", False))

    def _just(self, key: str) -> bool:
        cur  = bool(self.km.get(key, False))
        prev = self._prev.get(key, False)
        self._prev[key] = cur
        return cur and not prev

    def shift_up_just(self) -> bool:
        return self._just("e")

    def shift_down_just(self) -> bool:
        return self._just("q")

    def reset_just(self) -> bool:
        return self._just("r")

    def camera_just(self) -> bool:
        return self._just("c")
