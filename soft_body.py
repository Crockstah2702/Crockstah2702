"""
Simplified soft-body / node-beam damage system inspired by BeamNG.

Architecture
------------
* The car body is approximated as a grid of Nodes connected by Beams.
* Each physics tick, beam spring & damping forces are integrated with NumPy
  (fast enough at ~200 Hz in Python).
* When a beam's stress exceeds its yield limit it permanently deforms;
  when it exceeds its break limit it snaps.
* The Panda3D GeomNode vertex positions are updated every render frame to
  reflect the deformed node positions.

Zone mapping
------------
Damage is also tracked in six coarse zones for HUD / mechanical effects:
  FRONT, REAR, LEFT, RIGHT, ROOF, FLOOR
"""
from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Tuple

from panda3d.core import (
    GeomVertexData, GeomVertexWriter, GeomVertexReader,
    GeomVertexFormat, Geom, GeomNode, GeomTriangles,
    NodePath, Vec3, Point3, LColor,
)


# ---------------------------------------------------------------------------
# Damage zones
# ---------------------------------------------------------------------------

class Zone(IntEnum):
    FRONT = 0
    REAR  = 1
    LEFT  = 2
    RIGHT = 3
    ROOF  = 4
    FLOOR = 5


ZONE_NAMES = ["Front", "Rear", "Left", "Right", "Roof", "Floor"]


# ---------------------------------------------------------------------------
# Node & Beam
# ---------------------------------------------------------------------------

@dataclass
class SBNode:
    pos:    np.ndarray        # [x, y, z]  current position
    rest:   np.ndarray        # [x, y, z]  rest (undamaged) position (car-local)
    vel:    np.ndarray = field(default_factory=lambda: np.zeros(3))
    mass:   float = 2.0       # kg
    fixed:  bool  = False     # chassis anchor (mount point)


@dataclass
class SBBeam:
    a: int          # index into node list
    b: int
    rest_len:   float = 0.0
    spring_k:   float = 80_000.0   # N/m
    damping:    float = 800.0      # N·s/m
    yield_f:    float = 25_000.0   # force at which permanent deformation starts
    break_f:    float = 80_000.0   # force at which beam snaps
    deform:     float = 0.0        # cumulative permanent deformation ratio
    broken:     bool  = False


# ---------------------------------------------------------------------------
# SoftBody class
# ---------------------------------------------------------------------------

class SoftBody:
    """
    Manages the node-beam structure for one vehicle.

    Parameters
    ----------
    half_size : (hx, hy, hz)  half-extents of the car body box
    nx, ny, nz               : grid resolution (number of nodes per axis)
    """

    GRAVITY = np.array([0.0, 0.0, -9.81])

    def __init__(self,
                 half_size: Tuple[float, float, float] = (0.95, 2.1, 0.45),
                 nx: int = 3, ny: int = 5, nz: int = 2):
        self.hx, self.hy, self.hz = half_size
        self.nx, self.ny, self.nz = nx, ny, nz

        self.nodes:  List[SBNode]  = []
        self.beams:  List[SBBeam]  = []

        # Per-zone damage  0–1
        self.zone_damage: np.ndarray = np.zeros(6, dtype=np.float64)

        self._build_grid()
        self._connect_beams()

        # Panda3D render node (created lazily)
        self.geom_np: NodePath | None = None
        self._vdata:  GeomVertexData | None = None
        self._n_verts: int = 0

    # ------------------------------------------------------------------
    # Grid construction
    # ------------------------------------------------------------------

    def _build_grid(self):
        xs = np.linspace(-self.hx, self.hx, self.nx)
        ys = np.linspace(-self.hy, self.hy, self.ny)
        zs = np.linspace(-self.hz, self.hz, self.nz)
        for z in zs:
            for y in ys:
                for x in xs:
                    pos  = np.array([x, y, z], dtype=np.float64)
                    node = SBNode(pos=pos.copy(), rest=pos.copy())
                    # Corner nodes are heavier (structural)
                    if abs(x) == self.hx and abs(y) == self.hy:
                        node.mass = 5.0
                    self.nodes.append(node)

    def _node_idx(self, xi: int, yi: int, zi: int) -> int:
        return zi * (self.ny * self.nx) + yi * self.nx + xi

    def _connect_beams(self):
        """Connect adjacent nodes and diagonals."""
        def add(a: int, b: int, k: float = 80_000.0, yield_f: float = 25_000.0,
                break_f: float = 80_000.0):
            if a == b:
                return
            # Avoid duplicates
            for bm in self.beams:
                if (bm.a == a and bm.b == b) or (bm.a == b and bm.b == a):
                    return
            pa = self.nodes[a].pos
            pb = self.nodes[b].pos
            rl = float(np.linalg.norm(pb - pa))
            self.beams.append(SBBeam(a=a, b=b, rest_len=rl,
                                     spring_k=k, yield_f=yield_f, break_f=break_f))

        for zi in range(self.nz):
            for yi in range(self.ny):
                for xi in range(self.nx):
                    idx = self._node_idx(xi, yi, zi)
                    # structural axes
                    if xi + 1 < self.nx:
                        add(idx, self._node_idx(xi+1, yi, zi))
                    if yi + 1 < self.ny:
                        add(idx, self._node_idx(xi, yi+1, zi))
                    if zi + 1 < self.nz:
                        add(idx, self._node_idx(xi, yi, zi+1),
                            k=100_000.0, yield_f=30_000.0)
                    # face diagonals (shear)
                    if xi + 1 < self.nx and yi + 1 < self.ny:
                        add(idx, self._node_idx(xi+1, yi+1, zi), k=50_000.0)
                        add(self._node_idx(xi+1, yi, zi),
                            self._node_idx(xi, yi+1, zi), k=50_000.0)

    # ------------------------------------------------------------------
    # Simulation step  (call at high frequency, e.g. 200 Hz)
    # ------------------------------------------------------------------

    def step(self, dt: float, chassis_pos: np.ndarray, chassis_rot: np.ndarray):
        """
        chassis_pos  – world-space position of chassis origin [x,y,z]
        chassis_rot  – 3×3 rotation matrix (world-from-local)
        """
        n  = len(self.nodes)
        forces = np.zeros((n, 3), dtype=np.float64)

        # Gravity
        for i, nd in enumerate(self.nodes):
            forces[i] += self.GRAVITY * nd.mass

        # Beam spring + damping forces
        for bm in self.beams:
            if bm.broken:
                continue
            pa = self.nodes[bm.a].pos
            pb = self.nodes[bm.b].pos
            va = self.nodes[bm.a].vel
            vb = self.nodes[bm.b].vel

            diff = pb - pa
            dist = np.linalg.norm(diff)
            if dist < 1e-6:
                continue
            unit = diff / dist

            spring_f  = bm.spring_k * (dist - bm.rest_len)
            damp_f    = bm.damping  * np.dot(vb - va, unit)
            total_f   = spring_f + damp_f
            force_vec = total_f * unit

            forces[bm.a] += force_vec
            forces[bm.b] -= force_vec

            # Permanent deformation & breakage
            abs_f = abs(total_f)
            if abs_f > bm.yield_f:
                excess = (abs_f - bm.yield_f) / (bm.break_f - bm.yield_f + 1.0)
                bm.deform = min(1.0, bm.deform + excess * dt * 2.0)
                bm.rest_len += (dist - bm.rest_len) * excess * dt * 0.5
            if abs_f > bm.break_f:
                bm.broken = True

        # Integrate node positions
        for i, nd in enumerate(self.nodes):
            if nd.fixed:
                continue
            acc = forces[i] / nd.mass
            nd.vel += acc * dt
            nd.vel *= (1.0 - 0.08 * dt)   # damping
            nd.pos += nd.vel * dt

        # Keep nodes anchored to chassis (soft constraint)
        for nd in self.nodes:
            world_rest = chassis_pos + chassis_rot @ nd.rest
            drift = world_rest - nd.pos
            nd.pos += drift * min(1.0, 25.0 * dt)

        self._update_zone_damage()

    # ------------------------------------------------------------------
    # Impact impulse from Bullet collision callback
    # ------------------------------------------------------------------

    def apply_impact(self, world_point: np.ndarray, impulse_vec: np.ndarray,
                     chassis_pos: np.ndarray, chassis_rot: np.ndarray):
        """
        Called when a collision occurs.  Distributes impulse to nearby nodes.
        """
        impulse_mag = float(np.linalg.norm(impulse_vec))
        if impulse_mag < 500.0:   # ignore tiny bumps
            return

        # Transform hit point to local space
        local_hit = chassis_rot.T @ (world_point - chassis_pos)

        # Find nodes within influence radius
        radius = 0.8
        affected = 0
        for nd in self.nodes:
            d = np.linalg.norm(nd.rest - local_hit)
            if d < radius:
                weight = 1.0 - d / radius
                nd.vel += (impulse_vec / nd.mass) * weight * 0.3
                affected += 1

        # Update zone damage
        zone = self._point_to_zone(local_hit)
        dmg  = min(1.0, impulse_mag / 50_000.0)
        self.zone_damage[zone] = min(1.0, self.zone_damage[zone] + dmg * 0.4)

    def _point_to_zone(self, local: np.ndarray) -> Zone:
        x, y, z = local
        if z > self.hz * 0.5:
            return Zone.ROOF
        if z < -self.hz * 0.5:
            return Zone.FLOOR
        if y > self.hy * 0.4:
            return Zone.FRONT
        if y < -self.hy * 0.4:
            return Zone.REAR
        if x > 0:
            return Zone.RIGHT
        return Zone.LEFT

    def _update_zone_damage(self):
        broken_count = sum(1 for b in self.beams if b.broken)
        ratio = broken_count / max(1, len(self.beams))
        # Blend beam breakage into overall zones
        for z in range(6):
            self.zone_damage[z] = min(1.0, self.zone_damage[z] + ratio * 0.001)

    @property
    def total_damage(self) -> float:
        return float(np.mean(self.zone_damage))

    # ------------------------------------------------------------------
    # Panda3D geometry – deformable car body mesh
    # ------------------------------------------------------------------

    def build_geom(self, parent_np: NodePath, color=(0.18, 0.22, 0.55, 1.0)):
        """
        Create a Panda3D GeomNode from the soft-body nodes and attach it
        to parent_np.  Returns the NodePath.
        """
        fmt   = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("softbody", fmt, Geom.UHDynamic)
        self._vdata = vdata

        verts = GeomVertexWriter(vdata, "vertex")
        norms = GeomVertexWriter(vdata, "normal")
        cols  = GeomVertexWriter(vdata, "color")

        # Build a simple box face mesh from node grid
        # We render only the outer surface (nz layers → top/bottom + sides)
        faces = self._build_face_indices()

        # Collect unique vertex positions for the outer hull
        outer_nodes = self._outer_node_indices()
        idx_map = {old: new for new, old in enumerate(outer_nodes)}
        self._n_verts = len(outer_nodes)

        for ni in outer_nodes:
            nd = self.nodes[ni]
            verts.addData3(*nd.pos.tolist())
            norms.addData3(0, 0, 1)
            cols.addData4(*color)

        tris = GeomTriangles(Geom.UHStatic)
        for tri in faces:
            mapped = [idx_map.get(i) for i in tri]
            if None not in mapped:
                tris.addVertices(*mapped)

        geom = Geom(vdata)
        geom.addPrimitive(tris)

        gnode = GeomNode("car_body")
        gnode.addGeom(geom)

        self.geom_np = parent_np.attachNewNode(gnode)
        self._outer_nodes = outer_nodes
        return self.geom_np

    def _outer_node_indices(self) -> list:
        """Return indices of nodes on the outer surface of the grid."""
        indices = []
        for zi in range(self.nz):
            for yi in range(self.ny):
                for xi in range(self.nx):
                    if (xi == 0 or xi == self.nx-1 or
                            yi == 0 or yi == self.ny-1 or
                            zi == 0 or zi == self.nz-1):
                        indices.append(self._node_idx(xi, yi, zi))
        return sorted(set(indices))

    def _build_face_indices(self) -> list:
        """Build triangle indices for the outer surface."""
        tris = []
        # Top/bottom (z planes)
        for zi in (0, self.nz-1):
            for yi in range(self.ny-1):
                for xi in range(self.nx-1):
                    a = self._node_idx(xi,   yi,   zi)
                    b = self._node_idx(xi+1, yi,   zi)
                    c = self._node_idx(xi+1, yi+1, zi)
                    d = self._node_idx(xi,   yi+1, zi)
                    if zi == self.nz-1:
                        tris += [(a, b, c), (a, c, d)]
                    else:
                        tris += [(a, c, b), (a, d, c)]
        # Front/rear (y planes)
        for yi in (0, self.ny-1):
            for zi in range(self.nz-1):
                for xi in range(self.nx-1):
                    a = self._node_idx(xi,   yi, zi)
                    b = self._node_idx(xi+1, yi, zi)
                    c = self._node_idx(xi+1, yi, zi+1)
                    d = self._node_idx(xi,   yi, zi+1)
                    tris += [(a, b, c), (a, c, d)]
        # Left/right (x planes)
        for xi in (0, self.nx-1):
            for zi in range(self.nz-1):
                for yi in range(self.ny-1):
                    a = self._node_idx(xi, yi,   zi)
                    b = self._node_idx(xi, yi+1, zi)
                    c = self._node_idx(xi, yi+1, zi+1)
                    d = self._node_idx(xi, yi,   zi+1)
                    tris += [(a, b, c), (a, c, d)]
        return tris

    def update_geom(self):
        """Push current node positions to the GPU vertex buffer."""
        if self._vdata is None or self.geom_np is None:
            return
        writer = GeomVertexWriter(self._vdata, "vertex")
        col_w  = GeomVertexWriter(self._vdata, "color")
        for i, ni in enumerate(self._outer_nodes):
            nd = self.nodes[ni]
            writer.setRow(i)
            writer.setData3(*nd.pos.tolist())
            # Colour shift: white → red based on local damage
            zone = self._point_to_zone(nd.rest)
            dmg  = float(self.zone_damage[zone])
            col_w.setRow(i)
            col_w.setData4(0.18 + 0.82*dmg, 0.22*(1-dmg), 0.55*(1-dmg), 1.0)
