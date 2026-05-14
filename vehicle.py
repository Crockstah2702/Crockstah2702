"""
Vehicle – integrates Bullet physics, engine simulation, and soft-body damage.

Chassis properties approximate a 2002 BMW M3 (E46):
  - Curb weight  : 1570 kg
  - Drive layout : RWD
  - Wheelbase    : 2.73 m
  - Track (front): 1.49 m
  - Track (rear) : 1.51 m
  - Wheel radius : 0.33 m
"""
from __future__ import annotations

import math
import numpy as np
from typing import TYPE_CHECKING

from panda3d.core import (
    NodePath, Vec3, Point3, LColor, Mat3, Mat4,
    TransformState, GeomNode,
)
from panda3d.bullet import (
    BulletWorld, BulletRigidBodyNode, BulletBoxShape,
    BulletCylinderShape, BulletVehicle, ZUp,
    BulletGhostNode, BulletSphereShape,
)

from engine_sim import EngineSim
from soft_body   import SoftBody

if TYPE_CHECKING:
    from direct.showbase.ShowBase import ShowBase


# ---------------------------------------------------------------------------
# Wheel geometry helper
# ---------------------------------------------------------------------------

def _make_wheel_np(render: NodePath, radius: float,
                   width: float, color: tuple) -> NodePath:
    from panda3d.core import (
        GeomVertexData, GeomVertexWriter, GeomVertexFormat,
        Geom, GeomTriangles, GeomNode,
    )
    SEG = 20
    fmt   = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData("wheel", fmt, Geom.UHStatic)
    v  = GeomVertexWriter(vdata, "vertex")
    n  = GeomVertexWriter(vdata, "normal")
    c  = GeomVertexWriter(vdata, "color")

    def add(x, y, z, nx=0, ny=0, nz=1):
        v.addData3(x, y, z)
        n.addData3(nx, ny, nz)
        c.addData4(*color)

    # Cylinder: two circles + side
    hw = width / 2
    for side, sign in ((0, -1), (1, 1)):
        cx, cy, cz = 0, 0, sign * hw
        add(cx, cy, cz, 0, 0, sign)
        for i in range(SEG):
            a = 2*math.pi * i / SEG
            add(radius*math.cos(a), radius*math.sin(a), sign*hw, 0, 0, sign)

    tris = GeomTriangles(Geom.UHStatic)
    # Disk faces
    for side in range(2):
        base = side * (SEG + 1)
        for i in range(SEG):
            i0 = base
            i1 = base + 1 + i
            i2 = base + 1 + (i+1) % SEG
            if side == 0:
                tris.addVertices(i0, i2, i1)
            else:
                tris.addVertices(i0, i1, i2)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    gn   = GeomNode("wheel_geom")
    gn.addGeom(geom)
    np_  = render.attachNewNode(gn)
    np_.setTwoSided(True)
    return np_


# ---------------------------------------------------------------------------
# Vehicle
# ---------------------------------------------------------------------------

class Vehicle:
    # Physical dimensions
    CHASSIS_HALF  = Vec3(0.92, 2.10, 0.38)   # m  (half-extents)
    MASS          = 1570.0                     # kg
    WHEEL_RADIUS  = 0.33                       # m
    WHEEL_WIDTH   = 0.24                       # m
    COM_OFFSET    = Vec3(0, 0.1, -0.15)       # centre-of-mass offset

    # Wheel mount positions (local)
    WHEEL_POS = [
        Vec3( 0.80,  1.30, -0.20),   # 0 front-right
        Vec3(-0.80,  1.30, -0.20),   # 1 front-left
        Vec3( 0.81, -1.43, -0.20),   # 2 rear-right
        Vec3(-0.81, -1.43, -0.20),   # 3 rear-left
    ]
    FRONT_WHEEL = (True, True, False, False)

    # Suspension
    SUSP_STIFFNESS    = 38.0
    SUSP_DAMPING_REL  = 2.6
    SUSP_DAMPING_COMP = 4.2
    SUSP_TRAVEL_CM    = 12.0
    SUSP_REST_LEN     = 0.45

    # Friction (high for road tyres)
    FRICTION_SLIP = 12.0

    def __init__(self, world: BulletWorld, render: NodePath, spawn_pos: Vec3):
        self.world  = world
        self.render = render

        self.engine = EngineSim()
        self.soft   = SoftBody(
            half_size=(self.CHASSIS_HALF.x,
                       self.CHASSIS_HALF.y,
                       self.CHASSIS_HALF.z + 0.3),
            nx=3, ny=5, nz=2,
        )

        # State
        self.steering_angle: float = 0.0   # radians
        self.handbrake:       bool  = False
        self.auto_trans:      bool  = False

        # Wheel visual nodes
        self._wheel_nps: list[NodePath] = []

        # Suspension damage (per wheel, 0–1)
        self.wheel_damage = [0.0, 0.0, 0.0, 0.0]

        self._setup_bullet(spawn_pos)
        self._setup_visuals()

    # ------------------------------------------------------------------
    # Bullet physics setup
    # ------------------------------------------------------------------

    def _setup_bullet(self, spawn_pos: Vec3):
        shape  = BulletBoxShape(self.CHASSIS_HALF)
        node   = BulletRigidBodyNode("vehicle_chassis")
        node.setMass(self.MASS)
        node.addShape(shape, TransformState.makePos(self.COM_OFFSET))
        node.setDeactivationEnabled(False)
        node.setLinearSleepThreshold(0.0)
        node.setAngularSleepThreshold(0.0)
        node.setFriction(0.5)

        self.chassis_np = self.render.attachNewNode(node)
        self.chassis_np.setPos(spawn_pos)
        self.world.attachRigidBody(node)

        self.vehicle = BulletVehicle(self.world, node)
        self.vehicle.setCoordinateSystem(ZUp)
        self.world.attachVehicle(self.vehicle)

        for i, wpos in enumerate(self.WHEEL_POS):
            w = self.vehicle.createWheel()
            w.setChassisConnectionPointCs(wpos)
            w.setFrontWheel(self.FRONT_WHEEL[i])
            w.setWheelDirectionCs(Vec3(0, 0, -1))
            w.setWheelAxleCs(Vec3(1, 0, 0))
            w.setWheelRadius(self.WHEEL_RADIUS)
            w.setMaxSuspensionTravelCm(self.SUSP_TRAVEL_CM)
            w.setMaxSuspensionForce(40_000.0)
            w.setSuspensionStiffness(self.SUSP_STIFFNESS)
            w.setWheelsDampingRelaxation(self.SUSP_DAMPING_REL)
            w.setWheelsDampingCompression(self.SUSP_DAMPING_COMP)
            w.setFrictionSlip(self.FRICTION_SLIP)
            w.setRollInfluence(0.08)
            w.setMaxSuspensionForce(60_000.0)

    # ------------------------------------------------------------------
    # Visual geometry (procedural)
    # ------------------------------------------------------------------

    def _setup_visuals(self):
        # Main body via soft-body geometry
        body_color = (0.10, 0.18, 0.62, 1.0)   # deep blue
        self.soft.build_geom(self.chassis_np, color=body_color)

        # Roof structure (box)
        self._add_box(self.chassis_np, Vec3(0.78, 1.3, 0.35),
                      Point3(0, 0.1, 0.76),
                      (0.08, 0.14, 0.52, 1.0), "roof")

        # Windshield (dark tinted box)
        self._add_box(self.chassis_np, Vec3(0.73, 0.05, 0.3),
                      Point3(0, 1.3, 0.56),
                      (0.1, 0.15, 0.25, 0.7), "windshield")

        # Spoiler (rear)
        self._add_box(self.chassis_np, Vec3(0.85, 0.06, 0.06),
                      Point3(0, -2.05, 0.5),
                      (0.06, 0.06, 0.06, 1.0), "spoiler")

        # Headlights
        for sx in (-1, 1):
            self._add_box(self.chassis_np, Vec3(0.18, 0.04, 0.08),
                          Point3(sx*0.6, 2.1, 0.15),
                          (1.0, 0.97, 0.85, 1.0), f"headlight_{sx}")

        # Tail lights
        for sx in (-1, 1):
            self._add_box(self.chassis_np, Vec3(0.22, 0.04, 0.1),
                          Point3(sx*0.65, -2.1, 0.1),
                          (0.9, 0.05, 0.05, 1.0), f"taillight_{sx}")

        # Wheels
        colors = [(0.12, 0.12, 0.12, 1.0)] * 4   # dark rubber
        for i, wpos in enumerate(self.WHEEL_POS):
            wheel_np = _make_wheel_np(self.chassis_np,
                                      self.WHEEL_RADIUS,
                                      self.WHEEL_WIDTH,
                                      colors[i])
            wheel_np.setPos(wpos)
            self._wheel_nps.append(wheel_np)

    @staticmethod
    def _add_box(parent: NodePath, half: Vec3, pos: Point3,
                 color: tuple, name: str) -> NodePath:
        from panda3d.core import (
            GeomVertexData, GeomVertexWriter, GeomVertexFormat,
            Geom, GeomTriangles, GeomNode,
        )
        fmt   = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData(name, fmt, Geom.UHStatic)
        vw    = GeomVertexWriter(vdata, "vertex")
        nw    = GeomVertexWriter(vdata, "normal")
        cw    = GeomVertexWriter(vdata, "color")

        hx, hy, hz = half.x, half.y, half.z
        # 8 corners
        corners = [
            (-hx,-hy,-hz), ( hx,-hy,-hz), ( hx, hy,-hz), (-hx, hy,-hz),
            (-hx,-hy, hz), ( hx,-hy, hz), ( hx, hy, hz), (-hx, hy, hz),
        ]
        # 6 faces × 4 verts
        faces = [
            (0,1,2,3,  0, 0,-1), (4,7,6,5,  0, 0, 1),
            (0,4,5,1,  0,-1, 0), (2,6,7,3,  0, 1, 0),
            (0,3,7,4, -1, 0, 0), (1,5,6,2,  1, 0, 0),
        ]
        tris = GeomTriangles(Geom.UHStatic)
        vi = 0
        for f in faces:
            idxs, nx, ny, nz = f[:4], f[4], f[5], f[6]
            for ci in idxs:
                vw.addData3(*corners[ci])
                nw.addData3(nx, ny, nz)
                cw.addData4(*color)
            tris.addVertices(vi,   vi+1, vi+2)
            tris.addVertices(vi,   vi+2, vi+3)
            vi += 4

        geom = Geom(vdata)
        geom.addPrimitive(tris)
        gn   = GeomNode(name)
        gn.addGeom(geom)
        np_  = parent.attachNewNode(gn)
        np_.setPos(pos)
        np_.setTwoSided(True)
        return np_

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self, dt: float, throttle: float, brake: float,
               steer: float, handbrake: bool, gear_up: bool, gear_down: bool):

        self.engine.throttle = throttle
        self.handbrake        = handbrake

        # Steering smoothing (rate-limited)
        target_steer = steer * 0.55   # max steer angle radians
        steer_rate   = 3.5 * dt
        if abs(target_steer - self.steering_angle) < steer_rate:
            self.steering_angle = target_steer
        else:
            self.steering_angle += math.copysign(steer_rate,
                                                  target_steer - self.steering_angle)

        # Gear changes
        if gear_up:
            self.engine.shift_up()
        if gear_down:
            self.engine.shift_down()

        # Speed for auto-shift
        speed_ms  = self.get_speed_ms()
        speed_kmh = speed_ms * 3.6
        if self.auto_trans:
            self.engine.auto_shift(speed_kmh)

        # Wheel angular velocity (rear average for RWD)
        w2 = self.vehicle.getWheel(2)
        w3 = self.vehicle.getWheel(3)
        wheel_av = (w2.getDeltaRotation() + w3.getDeltaRotation()) / 2.0 / max(dt, 1e-4)

        self.engine.update(dt, wheel_av)

        # Apply forces to Bullet vehicle
        engine_torque  = self.engine.get_wheel_torque()
        brake_torque   = brake * 6000.0 * (1.0 - self.soft.zone_damage[0] * 0.4)
        hbrake_torque  = 8000.0 if handbrake else 0.0

        for i in range(4):
            w = self.vehicle.getWheel(i)
            # Steering (front wheels only)
            if self.FRONT_WHEEL[i]:
                w.setSteeringValue(math.degrees(self.steering_angle))
                w.setEngineForce(0.0)
                w.setBrake(brake_torque * 1.1)
            else:
                w.setSteeringValue(0.0)
                w.setEngineForce(engine_torque / 2.0)
                w.setBrake(brake_torque + hbrake_torque)
                if handbrake:
                    w.setEngineForce(0.0)

            # Reduce friction if wheel is damaged
            if self.wheel_damage[i] > 0.5:
                w.setFrictionSlip(self.FRICTION_SLIP * (1.0 - self.wheel_damage[i] * 0.6))

        # Soft-body update
        chassis_node = self.chassis_np.node()
        pos3 = self.chassis_np.getPos(self.render)
        pos  = np.array([pos3.x, pos3.y, pos3.z])
        rot  = self._panda_rot_matrix()
        self.soft.step(dt, pos, rot)
        self.soft.update_geom()

        # Sync wheel visual positions with Bullet wheel state
        for i, wnp in enumerate(self._wheel_nps):
            w = self.vehicle.getWheel(i)
            wp = w.getWorldTransform().getPos()
            wnp.setPos(self.chassis_np, wp - self.chassis_np.getPos(self.render))

    def _panda_rot_matrix(self) -> np.ndarray:
        """Extract 3×3 rotation matrix from chassis NodePath."""
        m = self.chassis_np.getMat(self.render)
        return np.array([
            [m[0][0], m[1][0], m[2][0]],
            [m[0][1], m[1][1], m[2][1]],
            [m[0][2], m[1][2], m[2][2]],
        ])

    # ------------------------------------------------------------------
    # Collision callback
    # ------------------------------------------------------------------

    def on_collision(self, world_pt: Vec3, impulse_vec: Vec3):
        pt  = np.array([world_pt.x,   world_pt.y,   world_pt.z])
        imp = np.array([impulse_vec.x, impulse_vec.y, impulse_vec.z])
        pos = self.chassis_np.getPos(self.render)
        pos_np = np.array([pos.x, pos.y, pos.z])
        rot    = self._panda_rot_matrix()
        self.soft.apply_impact(pt, imp, pos_np, rot)

        # Check wheel proximity for suspension damage
        for i, wpos_l in enumerate(self.WHEEL_POS):
            local_hit = rot.T @ (pt - pos_np)
            wl = np.array([wpos_l.x, wpos_l.y, wpos_l.z])
            dist = np.linalg.norm(local_hit - wl)
            if dist < 0.7:
                dmg = min(1.0, np.linalg.norm(imp) / 30_000.0)
                self.wheel_damage[i] = min(1.0, self.wheel_damage[i] + dmg * 0.3)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_speed_ms(self) -> float:
        v = self.chassis_np.node().getLinearVelocity()
        return math.sqrt(v.x**2 + v.y**2 + v.z**2)

    def get_speed_kmh(self) -> float:
        return self.get_speed_ms() * 3.6

    def reset(self, pos: Vec3):
        node = self.chassis_np.node()
        node.setLinearVelocity(Vec3(0))
        node.setAngularVelocity(Vec3(0))
        self.chassis_np.setPos(pos)
        self.chassis_np.setHpr(0, 0, 0)
        self.engine.rpm = self.engine.IDLE_RPM
        self.steering_angle = 0.0

    @property
    def position(self) -> Vec3:
        return self.chassis_np.getPos(self.render)

    @property
    def is_upside_down(self) -> bool:
        up = self.chassis_np.getRelativeVector(self.render, Vec3(0, 0, 1))
        return up.z < -0.5

    @property
    def damage_summary(self) -> str:
        zd = self.soft.zone_damage
        names = ["F", "R", "L", "Ri", "Ro", "Fl"]
        parts = [f"{n}:{v:.0%}" for n, v in zip(names, zd)]
        return "  ".join(parts)
