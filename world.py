"""
Procedural world: terrain, road network, scenery, lighting, sky.

The world is built entirely from Panda3D geometry – no external assets
required.  A simplex-noise height-map drives the terrain, carved flat
where roads are placed.
"""
from __future__ import annotations

import math
import random
import numpy as np
from typing import List, Tuple

from panda3d.core import (
    NodePath, Vec3, Vec4, Point3, LColor,
    GeomVertexData, GeomVertexWriter, GeomVertexFormat,
    Geom, GeomTriangles, GeomNode,
    DirectionalLight, AmbientLight,
    Fog, BitMask32,
)
from panda3d.bullet import (
    BulletWorld, BulletRigidBodyNode,
    BulletHeightfieldShape, ZUp,
    BulletPlaneShape,
)


# ---------------------------------------------------------------------------
# Tiny simplex-noise substitute (2-D, pure Python/numpy)
# ---------------------------------------------------------------------------

def _hash(ix: int, iy: int, seed: int = 137) -> int:
    h = ix * 1619 + iy * 31337 + seed
    h = ((h >> 13) ^ h)
    return (h * (h * h * 15731 + 789221) + 1376312589) & 0x7fffffff


def _smooth_noise(x: float, y: float, octaves: int = 6,
                  persistence: float = 0.5, lacunarity: float = 2.0,
                  scale: float = 0.02) -> float:
    total   = 0.0
    amp     = 1.0
    freq    = scale
    max_val = 0.0
    for _ in range(octaves):
        ix0, iy0 = int(math.floor(x * freq)), int(math.floor(y * freq))
        fx,  fy  = x * freq - ix0,           y * freq - iy0
        fx3 = fx * fx * (3 - 2 * fx)
        fy3 = fy * fy * (3 - 2 * fy)

        def g(ix, iy):
            h = _hash(ix, iy)
            return ((h & 0xff) / 127.5) - 1.0

        v  = g(ix0, iy0) * (1-fx3)*(1-fy3)
        v += g(ix0+1, iy0) * fx3*(1-fy3)
        v += g(ix0, iy0+1) * (1-fx3)*fy3
        v += g(ix0+1, iy0+1) * fx3*fy3

        total   += v * amp
        max_val += amp
        amp     *= persistence
        freq    *= lacunarity
    return total / max_val


def heightmap(x: float, y: float) -> float:
    """World-space height at (x, y).  Returns value in [−3, 12] m."""
    h = _smooth_noise(x, y, octaves=6, persistence=0.55, scale=0.018)
    h = h * 10.0 + 1.5
    # Flat zone near origin for spawning
    dist = math.sqrt(x*x + y*y)
    if dist < 30.0:
        h = h * (dist / 30.0)
    return h


# ---------------------------------------------------------------------------
# Terrain geometry builder
# ---------------------------------------------------------------------------

TERRAIN_SIZE = 600   # metres (−SIZE/2 … +SIZE/2)
TERRAIN_STEP = 4     # metres per grid cell


def _build_terrain_geom() -> Tuple[GeomNode, np.ndarray, int]:
    """
    Returns (GeomNode, heights_array, grid_n).
    heights_array shape = (grid_n, grid_n).
    """
    half = TERRAIN_SIZE // 2
    step = TERRAIN_STEP
    n    = TERRAIN_SIZE // step + 1

    # Pre-compute heights
    hmap = np.zeros((n, n), dtype=np.float32)
    for yi in range(n):
        for xi in range(n):
            wx = -half + xi * step
            wy = -half + yi * step
            hmap[yi, xi] = heightmap(wx, wy)

    fmt   = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData("terrain", fmt, Geom.UHStatic)
    vw    = GeomVertexWriter(vdata, "vertex")
    nw    = GeomVertexWriter(vdata, "normal")
    cw    = GeomVertexWriter(vdata, "color")

    for yi in range(n):
        for xi in range(n):
            wx = -half + xi * step
            wy = -half + yi * step
            h  = float(hmap[yi, xi])
            vw.addData3(wx, wy, h)

            # Normal (approximate via central differences)
            hxm = float(hmap[yi, max(0, xi-1)])
            hxp = float(hmap[yi, min(n-1, xi+1)])
            hym = float(hmap[max(0, yi-1), xi])
            hyp = float(hmap[min(n-1, yi+1), xi])
            nx_ = -(hxp - hxm) / (2*step)
            ny_ = -(hyp - hym) / (2*step)
            nz_ = 1.0
            nl  = math.sqrt(nx_*nx_ + ny_*ny_ + nz_*nz_)
            nw.addData3(nx_/nl, ny_/nl, nz_/nl)

            # Colour: grass green → rock grey → snow white by height
            if h < 0.5:
                col = (0.22, 0.38, 0.18, 1.0)
            elif h < 4.0:
                col = (0.28, 0.45, 0.22, 1.0)
            elif h < 7.0:
                col = (0.45, 0.42, 0.35, 1.0)
            else:
                col = (0.72, 0.71, 0.68, 1.0)
            cw.addData4(*col)

    tris = GeomTriangles(Geom.UHStatic)
    for yi in range(n-1):
        for xi in range(n-1):
            a = yi*n + xi
            b = a + 1
            c = (yi+1)*n + xi
            d = c + 1
            tris.addVertices(a, b, d)
            tris.addVertices(a, d, c)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    gn   = GeomNode("terrain")
    gn.addGeom(geom)
    return gn, hmap, n


# ---------------------------------------------------------------------------
# Road builder
# ---------------------------------------------------------------------------

def _make_road_segment(p0: Tuple[float,float],
                       p1: Tuple[float,float],
                       width: float = 7.0) -> GeomNode:
    """Flat road quad between two 2-D world points."""
    dx, dy = p1[0]-p0[0], p1[1]-p0[1]
    length = math.sqrt(dx*dx + dy*dy)
    if length < 0.1:
        return None
    perp_x, perp_y = -dy/length*width/2, dx/length*width/2

    h0 = heightmap(p0[0], p0[1]) + 0.02
    h1 = heightmap(p1[0], p1[1]) + 0.02

    fmt   = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData("road", fmt, Geom.UHStatic)
    vw    = GeomVertexWriter(vdata, "vertex")
    nw    = GeomVertexWriter(vdata, "normal")
    cw    = GeomVertexWriter(vdata, "color")

    pts = [
        (p0[0]-perp_x, p0[1]-perp_y, h0),
        (p0[0]+perp_x, p0[1]+perp_y, h0),
        (p1[0]+perp_x, p1[1]+perp_y, h1),
        (p1[0]-perp_x, p1[1]-perp_y, h1),
    ]
    road_col = (0.22, 0.22, 0.22, 1.0)
    for pt in pts:
        vw.addData3(*pt)
        nw.addData3(0, 0, 1)
        cw.addData4(*road_col)

    tris = GeomTriangles(Geom.UHStatic)
    tris.addVertices(0, 1, 2)
    tris.addVertices(0, 2, 3)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    gn   = GeomNode("road_seg")
    gn.addGeom(geom)
    return gn


def _build_road_network(render: NodePath) -> List[NodePath]:
    """Build a network of roads and return their NodePaths."""
    road_nps = []
    # Main circuit (rough oval)
    circuit_pts: List[Tuple[float,float]] = []
    r1, r2 = 120, 80
    for i in range(60):
        a = 2*math.pi * i / 60
        circuit_pts.append((r1*math.cos(a), r2*math.sin(a)))
    circuit_pts.append(circuit_pts[0])

    for i in range(len(circuit_pts)-1):
        gn = _make_road_segment(circuit_pts[i], circuit_pts[i+1], width=8.0)
        if gn:
            np_ = render.attachNewNode(gn)
            road_nps.append(np_)

    # Straight highway
    for i in range(-10, 10):
        gn = _make_road_segment((i*20, -200), (i*20+20, -200), width=9.0)
        if gn:
            np_ = render.attachNewNode(gn)
            road_nps.append(np_)

    # Cross roads
    for i in range(-20, 20):
        gn = _make_road_segment((200, i*12), (200, i*12+12), width=7.5)
        if gn:
            np_ = render.attachNewNode(gn)
            road_nps.append(np_)

    return road_nps


# ---------------------------------------------------------------------------
# Tree / scenery builder
# ---------------------------------------------------------------------------

def _make_tree(parent: NodePath, x: float, y: float, seed: int = 0):
    rng   = random.Random(seed)
    trunk_h = rng.uniform(1.8, 3.5)
    foliage_r = rng.uniform(1.2, 2.4)
    h = heightmap(x, y)

    fmt   = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData("tree", fmt, Geom.UHStatic)
    vw    = GeomVertexWriter(vdata, "vertex")
    nw    = GeomVertexWriter(vdata, "normal")
    cw    = GeomVertexWriter(vdata, "color")

    tris_prim = GeomTriangles(Geom.UHStatic)
    vi = 0

    # Trunk (thin box)
    tr = 0.18
    trunk_corners = [
        (-tr,-tr,0), (tr,-tr,0), (tr,tr,0), (-tr,tr,0),
        (-tr,-tr,trunk_h),(tr,-tr,trunk_h),(tr,tr,trunk_h),(-tr,tr,trunk_h),
    ]
    tc = (0.42, 0.28, 0.14, 1.0)
    for fi in [(0,1,2,3, 0,0,-1),(4,7,6,5, 0,0,1),(0,4,5,1, 0,-1,0),
               (2,6,7,3, 0,1,0),(0,3,7,4, -1,0,0),(1,5,6,2, 1,0,0)]:
        idxs, nx, ny, nz_ = fi[:4], fi[4], fi[5], fi[6]
        for ci in idxs:
            vw.addData3(*trunk_corners[ci])
            nw.addData3(nx, ny, nz_)
            cw.addData4(*tc)
        tris_prim.addVertices(vi, vi+1, vi+2)
        tris_prim.addVertices(vi, vi+2, vi+3)
        vi += 4

    # Foliage (simple cone using triangle fan)
    SEG = 8
    fh = foliage_r * 2.2
    fc = (0.12 + rng.uniform(-0.04,0.04),
          0.45 + rng.uniform(-0.08,0.08),
          0.18 + rng.uniform(-0.04,0.04), 1.0)
    # Tip
    vw.addData3(0, 0, trunk_h + fh)
    nw.addData3(0, 0, 1)
    cw.addData4(*fc)
    tip = vi
    vi += 1
    # Base ring
    for i in range(SEG):
        a = 2*math.pi*i/SEG
        vw.addData3(foliage_r*math.cos(a), foliage_r*math.sin(a), trunk_h)
        nw.addData3(math.cos(a), math.sin(a), 0.5)
        cw.addData4(*fc)
    for i in range(SEG):
        tris_prim.addVertices(tip, vi+i, vi+(i+1)%SEG)
    vi += SEG

    geom = Geom(vdata)
    geom.addPrimitive(tris_prim)
    gn   = GeomNode("tree")
    gn.addGeom(geom)
    np_  = parent.attachNewNode(gn)
    np_.setPos(x, y, h)
    return np_


# ---------------------------------------------------------------------------
# World class
# ---------------------------------------------------------------------------

class World:
    def __init__(self, bullet_world: BulletWorld, render: NodePath):
        self.bullet_world = bullet_world
        self.render       = render
        self._road_nps:   List[NodePath] = []
        self._tree_nps:   List[NodePath] = []

        self._build_terrain()
        self._build_roads()
        self._build_trees(count=350)
        self._setup_lighting()
        self._setup_sky()
        self._setup_fog()

    # ------------------------------------------------------------------
    def _build_terrain(self):
        gn, hmap, n = _build_terrain_geom()
        self._terrain_np = self.render.attachNewNode(gn)
        self._terrain_np.setTwoSided(True)

        # Bullet ground plane (simplified – flat collider for performance)
        shape = BulletPlaneShape(Vec3(0, 0, 1), 0)
        node  = BulletRigidBodyNode("ground")
        node.addShape(shape)
        node.setFriction(0.85)
        gnd_np = self.render.attachNewNode(node)
        self.bullet_world.attachRigidBody(node)

    def _build_roads(self):
        self._road_nps = _build_road_network(self.render)

    def _build_trees(self, count: int = 300):
        rng = random.Random(42)
        half = TERRAIN_SIZE // 2 - 20
        placed = 0
        attempts = 0
        while placed < count and attempts < count * 10:
            attempts += 1
            x = rng.uniform(-half, half)
            y = rng.uniform(-half, half)
            # Don't place on roads or near origin
            dist = math.sqrt(x*x + y*y)
            if dist < 18:
                continue
            np_ = _make_tree(self.render, x, y, seed=placed)
            self._tree_nps.append(np_)
            placed += 1

    # ------------------------------------------------------------------
    def _setup_lighting(self):
        # Main directional sun
        sun = DirectionalLight("sun")
        sun.setColor((1.0, 0.97, 0.88, 1.0))
        sun.setShadowCaster(True, 2048, 2048)
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(-60, -45, 0)
        self.render.setLight(sun_np)

        # Fill / ambient
        amb = AmbientLight("ambient")
        amb.setColor((0.25, 0.28, 0.32, 1.0))
        amb_np = self.render.attachNewNode(amb)
        self.render.setLight(amb_np)

        # Enable auto-shader (shadows, normals)
        self.render.setShaderAuto()

    def _setup_sky(self):
        """Simple sky box using a large sphere coloured by vertex height."""
        SEG = 16
        RADIUS = 900.0
        fmt   = GeomVertexFormat.getV3c4()
        vdata = GeomVertexData("sky", fmt, Geom.UHStatic)
        vw    = GeomVertexWriter(vdata, "vertex")
        cw    = GeomVertexWriter(vdata, "color")

        sky_low  = (0.42, 0.60, 0.82, 1.0)
        sky_high = (0.12, 0.22, 0.55, 1.0)

        # Hemisphere
        for lat in range(SEG+1):
            phi = math.pi/2 * lat / SEG   # 0 … π/2
            for lon in range(SEG*2):
                theta = 2*math.pi * lon / (SEG*2)
                x = RADIUS*math.cos(phi)*math.cos(theta)
                y = RADIUS*math.cos(phi)*math.sin(theta)
                z = RADIUS*math.sin(phi)
                vw.addData3(x, y, z)
                t = lat / SEG
                col = tuple(sky_low[i]*(1-t) + sky_high[i]*t for i in range(4))
                cw.addData4(*col)

        tris = GeomTriangles(Geom.UHStatic)
        cols = SEG * 2
        for lat in range(SEG):
            for lon in range(cols):
                a = lat*cols + lon
                b = lat*cols + (lon+1)%cols
                c = (lat+1)*cols + lon
                d = (lat+1)*cols + (lon+1)%cols
                tris.addVertices(a, c, b)
                tris.addVertices(b, c, d)

        geom = Geom(vdata)
        geom.addPrimitive(tris)
        gn   = GeomNode("sky")
        gn.addGeom(geom)
        sky_np = self.render.attachNewNode(gn)
        sky_np.setBin("background", 0)
        sky_np.setDepthWrite(False)
        sky_np.setLightOff()
        sky_np.setTwoSided(True)

    def _setup_fog(self):
        fog = Fog("world_fog")
        fog.setColor(0.68, 0.74, 0.82)
        fog.setExpDensity(0.0012)
        self.render.setFog(fog)

    # ------------------------------------------------------------------
    def get_height_at(self, x: float, y: float) -> float:
        return heightmap(x, y)
