"""
Main game class – wires together Bullet physics, vehicle, world, HUD,
camera system, and the PS5 controller.

Camera modes  (cycle with Touchpad / C):
  0  Chase cam       – follows behind the car
  1  Hood cam        – sits just above the bonnet
  2  Cockpit cam     – driver's eye view
  3  Free orbit cam  – orbit around last position with right stick / mouse
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


class DrivingGame(ShowBase):
    PHYSICS_SUBSTEPS = 3     # substeps per render frame for stability
    SOFT_BODY_HZ     = 120   # soft-body integration frequency

    def __init__(self):
        ShowBase.__init__(self)

        self._configure_window()
        self._setup_physics()
        self._spawn_world()
        self._spawn_vehicle()
        self._setup_input()
        self._setup_hud()
        self._setup_camera()

        # Timing
        self._soft_body_acc = 0.0
        self._soft_body_dt  = 1.0 / self.SOFT_BODY_HZ

        # Paused state
        self._paused = False

        # Register main update task
        self.taskMgr.add(self._update_task, "game_update")

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _configure_window(self):
        wp = WindowProperties()
        wp.setTitle("Realistisches Fahrspiel  –  PS5 Controller Support")
        wp.setSize(1600, 900)
        self.win.requestProperties(wp)
        self.setBackgroundColor(0.52, 0.65, 0.80)
        self.disableMouse()   # we control the camera manually

    def _setup_physics(self):
        self.physics = BulletWorld()
        self.physics.setGravity(Vec3(0, 0, -9.81))

        # Uncomment to see collision shapes:
        # debug_node = BulletDebugNode("debug")
        # debug_node.showWireframe(True)
        # debug_np = self.render.attachNewNode(debug_node)
        # debug_np.show()
        # self.physics.setDebugNode(debug_node)

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
        # PS5 controller (primary)
        self._ps5 = PS5Controller()

        # Keyboard map (fallback)
        self._km: dict[str, bool] = {}
        self._kbd = KeyboardController(self._km)

        for key in ["arrow_up","arrow_down","arrow_left","arrow_right",
                    "w","a","s","d","space","e","q","r","c","escape","f1"]:
            self.accept(key,       self._km.__setitem__, [key, True])
            self.accept(key+"-up", self._km.__setitem__, [key, False])

        # One-shot key bindings
        self.accept("f1",    self._toggle_debug)
        self.accept("f11",   self._toggle_fullscreen)
        self.accept("p",     self._toggle_pause)

    def _setup_hud(self):
        self._hud = HUD(self.aspect2d)

    def _setup_camera(self):
        self._cam_mode   = 0   # chase
        self._cam_yaw    = 0.0
        self._cam_pitch  = 20.0
        self._cam_dist   = 10.0
        self._orbit_pos  = Point3(0, 0, 0)
        self.camLens.setFov(CAM_CONFIGS[0][3])
        self.camLens.setNear(0.3)
        self.camLens.setFar(1200.0)

    # ------------------------------------------------------------------
    # Main update task
    # ------------------------------------------------------------------

    def _update_task(self, task: Task) -> int:
        dt = min(globalClock.getDt(), 0.05)

        if self._paused:
            return Task.cont

        # Gather input
        self._ps5.update()
        self._kbd.update()

        ctrl = self._ps5 if self._ps5.connected else self._kbd

        throttle  = ctrl.get_throttle()
        brake     = ctrl.get_brake()
        steer     = ctrl.get_steering()
        handbrake = ctrl.get_handbrake()
        gear_up   = ctrl.shift_up_just()
        gear_down = ctrl.shift_down_just()

        # Keyboard modifiers when no controller connected
        if not self._ps5.connected:
            throttle  = self._kbd.get_throttle()
            brake     = self._kbd.get_brake()
            steer     = self._kbd.get_steering()
            handbrake = self._kbd.get_handbrake()
            gear_up   = self._kbd.shift_up_just()
            gear_down = self._kbd.shift_down_just()

        # Reset vehicle
        if ctrl.reset_just():
            spawn_z = self._world.get_height_at(
                self._vehicle.position.x,
                self._vehicle.position.y) + 1.5
            self._vehicle.reset(Vec3(
                self._vehicle.position.x,
                self._vehicle.position.y,
                spawn_z,
            ))
            self._hud.notify("Fahrzeug zurückgesetzt", 2.0)

        # Auto-flip if upside down for >3 s
        if not hasattr(self, "_flip_timer"):
            self._flip_timer = 0.0
        if self._vehicle.is_upside_down:
            self._flip_timer += dt
            if self._flip_timer > 3.0:
                self._auto_flip()
                self._flip_timer = 0.0
        else:
            self._flip_timer = 0.0

        # Camera toggle
        if ctrl.camera_just():
            self._cam_mode = (self._cam_mode + 1) % len(CAM_CONFIGS)
            name = CAM_CONFIGS[self._cam_mode][0]
            self._hud.notify(f"Kamera: {name}", 1.5)
            self.camLens.setFov(CAM_CONFIGS[self._cam_mode][3])

        # Physics step  (substeps for stability)
        sub_dt = dt / self.PHYSICS_SUBSTEPS
        for _ in range(self.PHYSICS_SUBSTEPS):
            self.physics.doPhysics(sub_dt, 1, sub_dt)

        # Soft body runs at its own frequency
        self._soft_body_acc += dt
        while self._soft_body_acc >= self._soft_body_dt:
            # (soft body is called inside vehicle.update; this just controls rate)
            self._soft_body_acc -= self._soft_body_dt

        # Vehicle update
        self._vehicle.update(dt, throttle, brake, steer, handbrake,
                             gear_up, gear_down)

        # Camera
        self._update_camera(dt, ctrl)

        # HUD
        self._hud.update(dt, self._vehicle, self._vehicle.engine)

        return Task.cont

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def _update_camera(self, dt: float, ctrl):
        mode = self._cam_mode
        vpos = self._vehicle.chassis_np.getPos(self.render)
        vhpr = self._vehicle.chassis_np.getHpr(self.render)

        if mode == 0:   # Chase cam
            eye_off = CAM_CONFIGS[0][1]
            tgt_off = CAM_CONFIGS[0][2]
            # Rotate offset by vehicle heading
            h_rad = math.radians(vhpr.x)
            ex = eye_off.x*math.cos(h_rad) - eye_off.y*math.sin(h_rad)
            ey = eye_off.x*math.sin(h_rad) + eye_off.y*math.cos(h_rad)
            eye = vpos + Vec3(ex, ey, eye_off.z)
            tgt = vpos + tgt_off
            self.camera.setPos(eye)
            self.camera.lookAt(tgt)

        elif mode == 1:   # Hood cam
            off = CAM_CONFIGS[1][1]
            h_rad = math.radians(vhpr.x)
            ex = off.x*math.cos(h_rad) - off.y*math.sin(h_rad)
            ey = off.x*math.sin(h_rad) + off.y*math.cos(h_rad)
            eye = vpos + Vec3(ex, ey, off.z)
            fwd_off = Vec3(
                -math.sin(h_rad)*8, math.cos(h_rad)*8, 0)
            self.camera.setPos(eye)
            self.camera.lookAt(eye + fwd_off)

        elif mode == 2:   # Cockpit cam
            off = CAM_CONFIGS[2][1]
            h_rad = math.radians(vhpr.x)
            ex = off.x*math.cos(h_rad) - off.y*math.sin(h_rad)
            ey = off.x*math.sin(h_rad) + off.y*math.cos(h_rad)
            eye = vpos + Vec3(ex, ey, off.z)
            fwd_off = Vec3(
                -math.sin(h_rad)*10, math.cos(h_rad)*10, 0)
            self.camera.setPos(eye)
            self.camera.lookAt(eye + fwd_off)

        elif mode == 3:   # Free orbit
            # Right stick / mouse for orbit
            if self._ps5.connected:
                rx = self._ps5._axis(2)
                ry = self._ps5._axis(3)
                self._cam_yaw   += rx * dt * 80
                self._cam_pitch  = max(5, min(85,
                    self._cam_pitch - ry * dt * 60))
            self._orbit_pos = vpos
            yaw_r   = math.radians(self._cam_yaw)
            pitch_r = math.radians(self._cam_pitch)
            d = self._cam_dist
            ex = self._orbit_pos.x + d*math.cos(pitch_r)*math.sin(yaw_r)
            ey = self._orbit_pos.y - d*math.cos(pitch_r)*math.cos(yaw_r)
            ez = self._orbit_pos.z + d*math.sin(pitch_r)
            self.camera.setPos(ex, ey, ez)
            self.camera.lookAt(self._orbit_pos + Vec3(0,0,1))

    # ------------------------------------------------------------------
    # Misc actions
    # ------------------------------------------------------------------

    def _auto_flip(self):
        pos = self._vehicle.chassis_np.getPos(self.render)
        pos.z += 1.0
        self._vehicle.reset(pos)
        self._hud.notify("Auto aufgerichtet!", 2.0)

    def _toggle_debug(self):
        pass   # reserved

    def _toggle_fullscreen(self):
        wp = WindowProperties()
        wp.setFullscreen(not self.win.getProperties().getFullscreen())
        self.win.requestProperties(wp)

    def _toggle_pause(self):
        self._paused = not self._paused
        self._hud.notify("PAUSE" if self._paused else "Weiter", 1.0)
