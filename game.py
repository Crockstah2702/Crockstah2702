"""
Main game class – wires together Bullet physics, vehicle, world, HUD,
camera system, PS5 controller, keyboard and mouse.

Camera modes  (cycle with Touchpad / C):
  0  Chase cam       – follows behind the car
  1  Hood cam        – sits just above the bonnet
  2  Cockpit cam     – driver's eye view
  3  Free orbit cam  – orbit with mouse drag (RMB) or PS5 right stick

Mouse support:
  RMB + drag        – orbit camera in all modes
  Scroll wheel      – zoom in/out (orbit mode)
  Middle click drag – pan orbit target height
"""
from __future__ import annotations

import math
import sys

from panda3d.core import (
    Vec3, Point3, LColor, WindowProperties,
    AmbientLight, DirectionalLight,
    ClockObject, BitMask32,
    ConfigVariableBool,
)
from panda3d.bullet import BulletWorld, BulletDebugNode
from direct.showbase.ShowBase import ShowBase
from direct.task import Task

from controller import PS5Controller, KeyboardController
from vehicle    import Vehicle
from world      import World
from hud        import HUD


# ---------------------------------------------------------------------------
# Camera offsets  (local to chassis)
# ---------------------------------------------------------------------------
CAM_CONFIGS = [
    # (name,         eye_offset,               look_offset,    fov)
    ("Chase",        Vec3(0, -8.5, 2.8),        Vec3(0, 3, 0),  75),
    ("Hood",         Vec3(0,  1.8, 1.0),        Vec3(0, 6, 0),  80),
    ("Cockpit",      Vec3(0.28, 0.9, 0.88),     Vec3(0, 5, 0),  90),
    ("Orbit",        Vec3(0, -12.0, 5.0),       Vec3(0, 0, 0),  70),
]

# Mouse sensitivity
MOUSE_ORBIT_SENS  = 0.25   # degrees per pixel
MOUSE_ZOOM_STEP   = 1.2    # multiplier per scroll tick


class DrivingGame(ShowBase):
    PHYSICS_SUBSTEPS = 3
    SOFT_BODY_HZ     = 120

    def __init__(self):
        ShowBase.__init__(self)

        self._configure_window()
        self._setup_physics()
        self._spawn_world()
        self._spawn_vehicle()
        self._setup_input()
        self._setup_hud()
        self._setup_camera()

        self._soft_body_acc = 0.0
        self._soft_body_dt  = 1.0 / self.SOFT_BODY_HZ
        self._paused        = False
        self._flip_timer    = 0.0

        self.taskMgr.add(self._update_task, "game_update")

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _configure_window(self):
        wp = WindowProperties()
        wp.setTitle("Realistisches Fahrspiel  –  PS5 · Tastatur · Maus")
        wp.setSize(1600, 900)
        self.win.requestProperties(wp)
        self.setBackgroundColor(0.52, 0.65, 0.80)
        self.disableMouse()   # manual camera control

    def _setup_physics(self):
        self.physics = BulletWorld()
        self.physics.setGravity(Vec3(0, 0, -9.81))

    def _spawn_world(self):
        self._world = World(self.physics, self.render)

    def _spawn_vehicle(self):
        spawn_z = self._world.get_height_at(0, 0) + 1.5
        self._vehicle = Vehicle(
            world=self.physics,
            render=self.render,
            spawn_pos=Vec3(0, 0, spawn_z),
        )

    def _setup_input(self):
        self._ps5 = PS5Controller()

        self._km: dict[str, bool] = {}
        self._kbd = KeyboardController(self._km)

        for key in ["arrow_up","arrow_down","arrow_left","arrow_right",
                    "w","a","s","d","space","e","q","r","c","escape","f1"]:
            self.accept(key,       self._km.__setitem__, [key, True])
            self.accept(key+"-up", self._km.__setitem__, [key, False])

        self.accept("f1",    self._toggle_debug)
        self.accept("f11",   self._toggle_fullscreen)
        self.accept("p",     self._toggle_pause)

        # ------ Mouse -------------------------------------------------------
        # Track right-mouse-button drag for camera orbit
        self._rmb_down      = False
        self._mouse_last_x  = 0
        self._mouse_last_y  = 0

        self.accept("mouse3",    self._on_rmb_down)
        self.accept("mouse3-up", self._on_rmb_up)

        # Middle mouse button drag for orbit height pan
        self._mmb_down = False
        self.accept("mouse2",    self._on_mmb_down)
        self.accept("mouse2-up", self._on_mmb_up)

        # Scroll wheel zoom
        self.accept("wheel_up",   self._on_scroll_up)
        self.accept("wheel_down", self._on_scroll_down)

    # ------ Mouse callbacks --------------------------------------------------

    def _on_rmb_down(self):
        self._rmb_down = True
        if self.mouseWatcherNode.hasMouse():
            p = self.win.getPointer(0)
            self._mouse_last_x = p.getX()
            self._mouse_last_y = p.getY()

    def _on_rmb_up(self):
        self._rmb_down = False

    def _on_mmb_down(self):
        self._mmb_down = True
        if self.mouseWatcherNode.hasMouse():
            p = self.win.getPointer(0)
            self._mouse_last_x = p.getX()
            self._mouse_last_y = p.getY()

    def _on_mmb_up(self):
        self._mmb_down = False

    def _on_scroll_up(self):
        self._cam_dist = max(2.0, self._cam_dist / MOUSE_ZOOM_STEP)

    def _on_scroll_down(self):
        self._cam_dist = min(120.0, self._cam_dist * MOUSE_ZOOM_STEP)

    # ------------------------------------------------------------------

    def _setup_hud(self):
        self._hud = HUD(self.aspect2d)

    def _setup_camera(self):
        self._cam_mode  = 0
        self._cam_yaw   = 180.0   # start looking from behind
        self._cam_pitch = 20.0
        self._cam_dist  = 12.0
        self._orbit_pos = Point3(0, 0, 0)
        self.camLens.setFov(CAM_CONFIGS[0][3])
        self.camLens.setNear(0.3)
        self.camLens.setFar(1200.0)

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    def _update_task(self, task: Task) -> int:
        dt = min(globalClock.getDt(), 0.05)

        if self._paused:
            return Task.cont

        self._ps5.update()
        self._kbd.update()

        # Input source: PS5 takes priority when connected
        if self._ps5.connected:
            throttle  = self._ps5.get_throttle()
            brake     = self._ps5.get_brake()
            steer     = self._ps5.get_steering()
            handbrake = self._ps5.get_handbrake()
            gear_up   = self._ps5.shift_up_just()
            gear_down = self._ps5.shift_down_just()
            reset     = self._ps5.reset_just()
            cam_tog   = self._ps5.camera_just()
        else:
            throttle  = self._kbd.get_throttle()
            brake     = self._kbd.get_brake()
            steer     = self._kbd.get_steering()
            handbrake = self._kbd.get_handbrake()
            gear_up   = self._kbd.shift_up_just()
            gear_down = self._kbd.shift_down_just()
            reset     = self._kbd.reset_just()
            cam_tog   = self._kbd.camera_just()

        # Reset
        if reset:
            spawn_z = self._world.get_height_at(
                self._vehicle.position.x,
                self._vehicle.position.y) + 1.5
            self._vehicle.reset(Vec3(
                self._vehicle.position.x,
                self._vehicle.position.y,
                spawn_z,
            ))
            self._hud.notify("Fahrzeug zurückgesetzt", 2.0)

        # Auto-flip
        if self._vehicle.is_upside_down:
            self._flip_timer += dt
            if self._flip_timer > 3.0:
                self._auto_flip()
                self._flip_timer = 0.0
        else:
            self._flip_timer = 0.0

        # Camera toggle
        if cam_tog:
            self._cam_mode = (self._cam_mode + 1) % len(CAM_CONFIGS)
            name = CAM_CONFIGS[self._cam_mode][0]
            self._hud.notify(f"Kamera: {name}", 1.5)
            self.camLens.setFov(CAM_CONFIGS[self._cam_mode][3])

        # Physics
        sub_dt = dt / self.PHYSICS_SUBSTEPS
        for _ in range(self.PHYSICS_SUBSTEPS):
            self.physics.doPhysics(sub_dt, 1, sub_dt)

        self._soft_body_acc += dt
        while self._soft_body_acc >= self._soft_body_dt:
            self._soft_body_acc -= self._soft_body_dt

        self._vehicle.update(dt, throttle, brake, steer, handbrake,
                             gear_up, gear_down)

        self._update_mouse_camera(dt)
        self._update_camera(dt)

        self._hud.update(dt, self._vehicle, self._vehicle.engine)

        return Task.cont

    # ------------------------------------------------------------------
    # Mouse camera delta processing
    # ------------------------------------------------------------------

    def _update_mouse_camera(self, dt: float):
        """Read mouse delta and update orbit yaw/pitch when RMB is held."""
        if not self.mouseWatcherNode.hasMouse():
            return

        p = self.win.getPointer(0)
        mx, my = p.getX(), p.getY()

        dx = mx - self._mouse_last_x
        dy = my - self._mouse_last_y

        if self._rmb_down and (dx != 0 or dy != 0):
            self._cam_yaw   += dx * MOUSE_ORBIT_SENS
            self._cam_pitch  = max(3.0, min(88.0,
                self._cam_pitch - dy * MOUSE_ORBIT_SENS))

        if self._mmb_down and dy != 0:
            # Middle drag: shift orbit target up/down
            pass   # reserved for future vertical pan

        self._mouse_last_x = mx
        self._mouse_last_y = my

        # PS5 right stick also drives orbit yaw/pitch
        if self._ps5.connected and self._cam_mode == 3:
            rx = self._ps5._axis(2)
            ry = self._ps5._axis(3)
            if abs(rx) > 0.06:
                self._cam_yaw   += rx * dt * 80
            if abs(ry) > 0.06:
                self._cam_pitch  = max(3.0, min(88.0,
                    self._cam_pitch - ry * dt * 60))

    # ------------------------------------------------------------------
    # Camera positioning
    # ------------------------------------------------------------------

    def _update_camera(self, dt: float):
        mode = self._cam_mode
        vpos = self._vehicle.chassis_np.getPos(self.render)
        vhpr = self._vehicle.chassis_np.getHpr(self.render)
        h_rad = math.radians(vhpr.x)

        def rot_offset(off: Vec3) -> Vec3:
            ex = off.x*math.cos(h_rad) - off.y*math.sin(h_rad)
            ey = off.x*math.sin(h_rad) + off.y*math.cos(h_rad)
            return Vec3(ex, ey, off.z)

        if mode == 0:   # Chase cam
            eye_off = CAM_CONFIGS[0][1]
            # When RMB held, allow user to orbit around car even in chase mode
            if self._rmb_down:
                eye = self._orbit_eye(vpos)
            else:
                eye = vpos + rot_offset(eye_off)
            self.camera.setPos(eye)
            self.camera.lookAt(vpos + Vec3(0, 0, 0.6))

        elif mode == 1:   # Hood cam
            off = CAM_CONFIGS[1][1]
            eye = vpos + rot_offset(off)
            fwd = Vec3(-math.sin(h_rad)*8, math.cos(h_rad)*8, 0)
            self.camera.setPos(eye)
            self.camera.lookAt(eye + fwd)

        elif mode == 2:   # Cockpit cam
            off = CAM_CONFIGS[2][1]
            eye = vpos + rot_offset(off)
            if self._rmb_down:
                # Mouse look: tilt gaze direction with yaw/pitch offset
                look_h = h_rad + math.radians(self._cam_yaw - 180)
                pitch_r = math.radians(self._cam_pitch - 20)
                fwd = Vec3(
                    -math.sin(look_h)*math.cos(pitch_r)*10,
                     math.cos(look_h)*math.cos(pitch_r)*10,
                     math.sin(pitch_r)*10,
                )
            else:
                fwd = Vec3(-math.sin(h_rad)*10, math.cos(h_rad)*10, 0)
            self.camera.setPos(eye)
            self.camera.lookAt(eye + fwd)

        elif mode == 3:   # Free orbit
            self._orbit_pos = vpos
            eye = self._orbit_eye(vpos)
            self.camera.setPos(eye)
            self.camera.lookAt(self._orbit_pos + Vec3(0, 0, 0.8))

    def _orbit_eye(self, target: Vec3) -> Vec3:
        yaw_r   = math.radians(self._cam_yaw)
        pitch_r = math.radians(self._cam_pitch)
        d       = self._cam_dist
        ex = target.x + d * math.cos(pitch_r) * math.sin(yaw_r)
        ey = target.y - d * math.cos(pitch_r) * math.cos(yaw_r)
        ez = target.z + d * math.sin(pitch_r)
        return Vec3(ex, ey, ez)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _auto_flip(self):
        pos = self._vehicle.chassis_np.getPos(self.render)
        pos.z += 1.0
        self._vehicle.reset(pos)
        self._hud.notify("Auto aufgerichtet!", 2.0)

    def _toggle_debug(self):
        pass

    def _toggle_fullscreen(self):
        wp = WindowProperties()
        wp.setFullscreen(not self.win.getProperties().getFullscreen())
        self.win.requestProperties(wp)

    def _toggle_pause(self):
        self._paused = not self._paused
        self._hud.notify("PAUSE" if self._paused else "Weiter", 1.0)
