"""
Generates realistic 3D assets (OBJ + MTL) for the driving game.
Run ONCE before launching the game, or it runs automatically on first start.

Produces:
    assets/car.obj / car.mtl   – sedan body with glass, lights, chrome
    assets/wheel.obj / wheel.mtl – tyre + 5-spoke alloy rim
"""
import math
import os

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


# ---------------------------------------------------------------------------
# Low-level OBJ builder
# ---------------------------------------------------------------------------

class OBJMesh:
    def __init__(self):
        self.verts: list[tuple] = []   # (x, y, z)
        self.norms: list[tuple] = []   # (nx, ny, nz)
        self.faces: list        = []   # (v_list, n_list, material)
        self._mat  = "default"

    # -- primitives ----------------------------------------------------------
    def v(self, x, y, z) -> int:
        self.verts.append((x, y, z)); return len(self.verts)

    def n(self, x, y, z) -> int:
        L = math.sqrt(x*x + y*y + z*z)
        if L < 1e-9: L = 1.0
        self.norms.append((x/L, y/L, z/L)); return len(self.norms)

    def face(self, vlist, nlist):
        self.faces.append((vlist, nlist, self._mat))

    def quad(self, v0,v1,v2,v3, n0,n1,n2,n3):
        self.face([v0,v1,v2], [n0,n1,n2])
        self.face([v0,v2,v3], [n0,n2,n3])

    def use(self, mat): self._mat = mat

    # -- write ---------------------------------------------------------------
    def save(self, obj_path: str, mtl_path: str, mtl_content: str):
        os.makedirs(os.path.dirname(obj_path), exist_ok=True)
        with open(mtl_path, "w") as f:
            f.write(mtl_content)

        lines = [f"mtllib {os.path.basename(mtl_path)}"]
        for (x,y,z) in self.verts:
            lines.append(f"v {x:.5f} {y:.5f} {z:.5f}")
        for (x,y,z) in self.norms:
            lines.append(f"vn {x:.5f} {y:.5f} {z:.5f}")

        cur_mat = None
        for (vl, nl, mat) in self.faces:
            if mat != cur_mat:
                lines.append(f"usemtl {mat}")
                cur_mat = mat
            line = "f " + " ".join(f"{v}//{n}" for v,n in zip(vl,nl))
            lines.append(line)

        with open(obj_path, "w") as f:
            f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Helper math
# ---------------------------------------------------------------------------

def lerp(a, b, t): return a + (b-a)*t
def lerp3(a, b, t): return tuple(a[i]+(b[i]-a[i])*t for i in range(3))

def smooth(t):
    """Smooth-step 0→1."""
    return t*t*(3 - 2*t)

def face_normal(p0, p1, p2):
    ax,ay,az = p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2]
    bx,by,bz = p2[0]-p0[0], p2[1]-p0[1], p2[2]-p0[2]
    nx = ay*bz - az*by
    ny = az*bx - ax*bz
    nz = ax*by - ay*bx
    L  = math.sqrt(nx*nx+ny*ny+nz*nz)
    if L < 1e-9: return (0,0,1)
    return (nx/L, ny/L, nz/L)


# ---------------------------------------------------------------------------
# Car body generator
# ---------------------------------------------------------------------------
#
# Coordinate system: Y = forward (front of car), Z = up, X = right
# Car centre = (0,0,0).  Body spans Y: -2.15 (rear) … +2.15 (front)
#
# Cross-section layout (right half, 10 points from floor to roof):
#   0  floor inner
#   1  sill bottom
#   2  sill outer
#   3  lower body
#   4  mid body (widest)
#   5  beltline
#   6  window sill
#   7  upper body
#   8  roof edge
#   9  roof centre (x=0)

NUM_SEGS   = 26   # cross-section count along Y
NUM_PTS    = 10   # points per cross-section (right side only)

# --- Y stations (front to back) ---
Y_STATIONS = [
    2.18,   # 0  front bumper tip
    2.05,   # 1  front bumper main
    1.88,   # 2  grille / headlight outer
    1.65,   # 3  front of hood
    1.30,   # 4  mid hood
    0.95,   # 5  windshield base
    0.65,   # 6  A-pillar top
    0.30,   # 7  front of roof
   -0.15,   # 8  mid roof
   -0.55,   # 9  rear of roof
   -0.80,   # 10 C-pillar
   -1.05,   # 11 rear window base
   -1.30,   # 12 boot lid start
   -1.55,   # 13 over rear axle
   -1.75,   # 14 rear wheel arch rear
   -1.88,   # 15 rear bumper top
   -2.05,   # 16 rear bumper main
   -2.18,   # 17 rear bumper tip
]

def _car_section(yi: float) -> list:
    """
    Returns 10 (x,z) points for the right-half cross section at given Y
    going from floor-inner to roof-centre.
    """
    # Y normalised -1..+1 (front = +1, rear = -1)
    yn = yi / 2.18

    # --- Width curve ---
    # Widest at doors (~y=0), narrower at front & rear
    base_w = 0.91
    if   yn >  0.85:  w = lerp(0.68, 0.80, smooth((1.0-yn)/0.15))   # front taper
    elif yn >  0.45:  w = lerp(0.82, 0.91, smooth((0.85-yn)/0.40))  # front shoulder
    elif yn > -0.65:  w = base_w                                      # door area
    elif yn > -0.85:  w = lerp(0.84, base_w, smooth((-0.65-yn)/0.20))# rear shoulder
    else:             w = lerp(0.68, 0.84, smooth((-0.85-yn)/0.30))  # rear taper

    # --- Roof height ---
    if   yn >  0.80:  roof_z =  0.00   # bumper – no roof
    elif yn >  0.44:  roof_z = lerp(0.00, 0.58, smooth((0.80-yn)/0.36))   # windshield rise
    elif yn > -0.42:  roof_z =  0.58   # roof plateau
    elif yn > -0.50:  roof_z = lerp(0.42, 0.58, smooth((-0.42-yn)/0.08))  # C-pillar
    elif yn > -0.80:  roof_z = lerp(0.00, 0.42, smooth((-0.50-yn)/0.30))  # rear window
    else:             roof_z =  0.00   # trunk / bumper – no roof

    # --- Lower body height (sill area) ---
    sill_z  = -0.38
    floor_z = -0.40

    # Build 10 profile points (x, z), right side:
    pts = []
    pts.append((0.0,         floor_z))       # 0 floor inner
    pts.append((w * 0.55,    floor_z))       # 1 sill bottom
    pts.append((w * 1.00,    sill_z))        # 2 sill outer (widest low)
    pts.append((w * 1.00,    sill_z + 0.15)) # 3 lower body
    pts.append((w * 1.00,    sill_z + 0.42)) # 4 mid body (door)
    pts.append((w * 0.97,    sill_z + 0.72)) # 5 beltline / window sill
    pts.append((w * 0.90,    sill_z + 0.90)) # 6 above beltline

    if roof_z > 0.02:
        pts.append((w * 0.76,  roof_z - 0.08))  # 7 upper body / A-C pillar
        pts.append((w * 0.55,  roof_z))          # 8 roof edge
        pts.append((0.0,       roof_z + 0.01))   # 9 roof centre
    else:
        # Front/rear – no roof, taper to nothing
        pts.append((w * 0.55,  sill_z + 0.95))   # 7
        pts.append((w * 0.28,  sill_z + 1.00))   # 8 folded inward
        pts.append((0.0,       sill_z + 0.98))   # 9 centre

    return pts


def _build_car_body(mesh: OBJMesh):
    """Loft cross-sections to build the car body mesh."""
    stations = Y_STATIONS
    NS = len(stations)
    NP = NUM_PTS

    # Pre-compute cross-sections
    sections = [_car_section(y) for y in stations]

    # ---------- add all vertices & normals first, store indices ----------
    # For each station × point × side(right/left) we create a vertex
    # Layout: [station][point][side]  side: 0=right(+x), 1=left(-x)
    V = [[[None, None] for _ in range(NP)] for _ in range(NS)]
    N = [[[None, None] for _ in range(NP)] for _ in range(NS)]

    for si, (y, sec) in enumerate(zip(stations, sections)):
        for pi, (x, z) in enumerate(sec):
            for side in range(2):
                sx = x if side == 0 else -x
                vi = mesh.v(sx, y, z)
                # Approximate outward normal: radial from centreline
                # We'll smooth these properly below
                if pi == 0 or pi == NP-1:
                    nx, nz = 0.0, (1.0 if pi == NP-1 else -1.0)
                else:
                    # direction away from car centre
                    nx = (x if side == 0 else -x)
                    nz = z
                    # tilt normal toward adjacent point direction
                    if pi < NP-1:
                        nx2, nz2 = sec[pi+1]
                        dx = nx2 - x; dz = nz2 - z
                        # normal perpendicular to tangent in XZ plane
                        nx =  dz + nx * 0.4
                        nz = -dx + nz * 0.4
                    if side == 1: nx = -nx
                ni = mesh.n(nx, 0, nz)
                V[si][pi][side] = vi
                N[si][pi][side] = ni

    # ---------- build quads between adjacent stations ----------
    # Determine material by Y position
    def get_mat(y_mid):
        yn = y_mid / 2.18
        if   yn >  0.72:  return "body_front"
        elif yn > -0.70:  return "body_paint"
        else:             return "body_rear"

    for si in range(NS - 1):
        y_mid = (stations[si] + stations[si+1]) * 0.5
        mat   = get_mat(y_mid)
        mesh.use(mat)

        for pi in range(NP - 1):
            for side in range(2):
                # Quad: (si,pi) → (si,pi+1) → (si+1,pi+1) → (si+1,pi)
                v0 = V[si  ][pi  ][side]
                v1 = V[si  ][pi+1][side]
                v2 = V[si+1][pi+1][side]
                v3 = V[si+1][pi  ][side]
                n0 = N[si  ][pi  ][side]
                n1 = N[si  ][pi+1][side]
                n2 = N[si+1][pi+1][side]
                n3 = N[si+1][pi  ][side]
                if side == 0:
                    mesh.quad(v0,v1,v2,v3, n0,n1,n2,n3)
                else:
                    mesh.quad(v3,v2,v1,v0, n3,n2,n1,n0)

    # ---------- top cap (roof) between left/right ----------
    mesh.use("body_paint")
    for si in range(NS - 1):
        p_top = NP - 1
        # right roof-centre vertex and left roof-centre vertex
        vR0 = V[si  ][p_top][0]; vL0 = V[si  ][p_top][1]
        vR1 = V[si+1][p_top][0]; vL1 = V[si+1][p_top][1]
        nR0 = N[si  ][p_top][0]; nL0 = N[si  ][p_top][1]
        nR1 = N[si+1][p_top][0]; nL1 = N[si+1][p_top][1]
        # Two triangles making the roof strip
        mesh.face([vR0, vL0, vL1], [nR0, nL0, nL1])
        mesh.face([vR0, vL1, vR1], [nR0, nL1, nR1])

    # ---------- bottom floor cap ----------
    mesh.use("black_plastic")
    for si in range(NS - 1):
        p_bot = 0
        vR0 = V[si  ][p_bot][0]; vL0 = V[si  ][p_bot][1]
        vR1 = V[si+1][p_bot][0]; vL1 = V[si+1][p_bot][1]
        nu  = mesh.n(0, 0, -1)
        mesh.face([vR0, vR1, vL1], [nu, nu, nu])
        mesh.face([vR0, vL1, vL0], [nu, nu, nu])


def _build_windows(mesh: OBJMesh):
    """Add window glass panels."""
    mesh.use("glass")

    def glass_quad(pts4):
        """pts4: list of 4 (x,y,z), adds both-sided quad."""
        fn = face_normal(pts4[0], pts4[1], pts4[2])
        vs = [mesh.v(*p) for p in pts4]
        ns = [mesh.n(*fn) for _ in pts4]
        mesh.face([vs[0],vs[1],vs[2]], [ns[0],ns[1],ns[2]])
        mesh.face([vs[0],vs[2],vs[3]], [ns[0],ns[2],ns[3]])
        fn2 = (-fn[0],-fn[1],-fn[2])
        ns2 = [mesh.n(*fn2) for _ in pts4]
        mesh.face([vs[2],vs[1],vs[0]], ns2)
        mesh.face([vs[3],vs[2],vs[0]], ns2)

    # Windshield
    glass_quad([
        ( 0.72, 1.60, 0.08), (-0.72, 1.60, 0.08),
        (-0.60, 0.70, 0.58), ( 0.60, 0.70, 0.58),
    ])
    # Rear window
    glass_quad([
        ( 0.60,-1.06, 0.56), (-0.60,-1.06, 0.56),
        (-0.72,-1.55, 0.08), ( 0.72,-1.55, 0.08),
    ])
    # Left front side window
    glass_quad([
        (-0.91, 1.55, 0.10), (-0.91, 0.60, 0.10),
        (-0.76, 0.55, 0.58), (-0.76, 1.50, 0.55),
    ])
    # Right front side window
    glass_quad([
        ( 0.91, 0.60, 0.10), ( 0.91, 1.55, 0.10),
        ( 0.76, 1.50, 0.55), ( 0.76, 0.55, 0.58),
    ])
    # Left rear side window
    glass_quad([
        (-0.91,-0.10, 0.10), (-0.91,-1.00, 0.10),
        (-0.76,-0.95, 0.58), (-0.76,-0.05, 0.56),
    ])
    # Right rear side window
    glass_quad([
        ( 0.91,-1.00, 0.10), ( 0.91,-0.10, 0.10),
        ( 0.76,-0.05, 0.56), ( 0.76,-0.95, 0.58),
    ])


def _build_headlights(mesh: OBJMesh):
    """Headlights and taillights as glowing panels."""
    def light_box(cx, y, z, hw, hh, wd, mat):
        mesh.use(mat)
        fn = (0.0, 1.0 if y > 0 else -1.0, 0.0)
        pts = [
            ( cx+hw, y, z-hh), (cx-hw, y, z-hh),
            (cx-hw, y, z+hh), (cx+hw, y, z+hh),
        ]
        vs = [mesh.v(*p) for p in pts]
        ns = [mesh.n(*fn)] * 4
        mesh.face([vs[0],vs[1],vs[2]], ns)
        mesh.face([vs[0],vs[2],vs[3]], ns)

    # Front headlights
    light_box( 0.62, 2.05,  0.08, 0.22, 0.10, 0.05, "headlight")
    light_box(-0.62, 2.05,  0.08, 0.22, 0.10, 0.05, "headlight")
    # Front DRL strip
    light_box( 0.0,  2.06,  0.22, 0.55, 0.03, 0.02, "headlight")
    # Rear taillights
    light_box( 0.68,-2.05,  0.08, 0.20, 0.12, 0.05, "taillight")
    light_box(-0.68,-2.05,  0.08, 0.20, 0.12, 0.05, "taillight")
    # Rear light strip
    light_box( 0.0, -2.06,  0.18, 0.55, 0.03, 0.02, "taillight")


def _build_grille(mesh: OBJMesh):
    """Front grille slats."""
    mesh.use("black_plastic")
    for row in range(4):
        z = -0.02 + row * 0.07
        fn = (0.0, 1.0, 0.0)
        pts = [
            ( 0.38, 2.065, z), (-0.38, 2.065, z),
            (-0.38, 2.065, z+0.03), (0.38, 2.065, z+0.03),
        ]
        vs = [mesh.v(*p) for p in pts]
        ns = [mesh.n(*fn)] * 4
        mesh.face([vs[0],vs[1],vs[2]], ns)
        mesh.face([vs[0],vs[2],vs[3]], ns)


def _build_spoiler(mesh: OBJMesh):
    """Rear spoiler."""
    mesh.use("body_paint")
    W = 0.82; wd = 0.07; ht = 0.10
    y = -2.05; z = 0.50
    pts_top = [
        ( W, y,  z+ht), (-W, y,  z+ht),
        (-W, y+wd, z+ht), ( W, y+wd, z+ht),
    ]
    vs = [mesh.v(*p) for p in pts_top]
    nu = mesh.n(0,0,1)
    ns = [nu]*4
    mesh.face([vs[0],vs[1],vs[2]], ns)
    mesh.face([vs[0],vs[2],vs[3]], ns)


def generate_car():
    mesh = OBJMesh()
    _build_car_body(mesh)
    _build_windows(mesh)
    _build_headlights(mesh)
    _build_grille(mesh)
    _build_spoiler(mesh)

    mtl = """
newmtl body_paint
Ka 0.04 0.07 0.25
Kd 0.10 0.18 0.62
Ks 0.85 0.85 0.90
Ns 150
illum 2

newmtl body_front
Ka 0.04 0.07 0.25
Kd 0.12 0.20 0.65
Ks 0.85 0.85 0.90
Ns 150
illum 2

newmtl body_rear
Ka 0.04 0.07 0.25
Kd 0.10 0.18 0.60
Ks 0.85 0.85 0.90
Ns 150
illum 2

newmtl glass
Ka 0.02 0.05 0.08
Kd 0.12 0.22 0.28
Ks 0.95 0.95 0.95
Ns 250
d 0.35
illum 4

newmtl headlight
Ka 0.95 0.95 0.85
Kd 1.00 1.00 0.92
Ks 1.00 1.00 1.00
Ns 250
Ke 0.70 0.70 0.60
illum 2

newmtl taillight
Ka 0.70 0.04 0.04
Kd 0.90 0.08 0.08
Ks 1.00 0.50 0.50
Ns 200
Ke 0.50 0.00 0.00
illum 2

newmtl black_plastic
Ka 0.03 0.03 0.03
Kd 0.07 0.07 0.07
Ks 0.25 0.25 0.25
Ns 40
illum 2
"""
    mesh.save(
        os.path.join(ASSETS_DIR, "car.obj"),
        os.path.join(ASSETS_DIR, "car.mtl"),
        mtl,
    )
    print("[Assets] car.obj generated")


# ---------------------------------------------------------------------------
# Wheel generator
# ---------------------------------------------------------------------------

def generate_wheel():
    mesh  = OBJMesh()
    SEGS  = 24   # circumference segments
    R     = 0.33  # tyre outer radius
    RI    = 0.23  # rim outer radius
    RIB   = 0.19  # rim inner (hub) radius
    HW    = 0.12  # half-width

    mtl = """
newmtl rubber
Ka 0.04 0.04 0.04
Kd 0.07 0.07 0.07
Ks 0.10 0.10 0.10
Ns 15
illum 1

newmtl rim
Ka 0.45 0.46 0.50
Kd 0.62 0.64 0.68
Ks 0.95 0.96 1.00
Ns 200
illum 2

newmtl hub
Ka 0.35 0.35 0.38
Kd 0.50 0.52 0.55
Ks 0.90 0.90 0.95
Ns 180
illum 2
"""

    # ---- Tyre barrel ----
    mesh.use("rubber")
    for i in range(SEGS):
        a0 = 2*math.pi * i / SEGS
        a1 = 2*math.pi * (i+1) / SEGS
        # outer tyre face
        for (z0, z1) in [(-HW*1.0, -HW*0.82), (-HW*0.82, HW*0.82), (HW*0.82, HW*1.0)]:
            p = [
                (R*math.cos(a0), R*math.sin(a0), z0),
                (R*math.cos(a1), R*math.sin(a1), z0),
                (R*math.cos(a1), R*math.sin(a1), z1),
                (R*math.cos(a0), R*math.sin(a0), z1),
            ]
            vs = [mesh.v(*q) for q in p]
            ns = [mesh.n(math.cos(a0), math.sin(a0), 0),
                  mesh.n(math.cos(a1), math.sin(a1), 0),
                  mesh.n(math.cos(a1), math.sin(a1), 0),
                  mesh.n(math.cos(a0), math.sin(a0), 0)]
            mesh.face([vs[0],vs[1],vs[2]], [ns[0],ns[1],ns[2]])
            mesh.face([vs[0],vs[2],vs[3]], [ns[0],ns[2],ns[3]])

        # Tyre sidewall (inner taper)
        for z_sgn, z_outer, z_inner in [(-1, -HW, -HW*0.75), (1, HW, HW*0.75)]:
            for r0, r1 in [(R, RI+0.02)]:
                p = [
                    (r0*math.cos(a0), r0*math.sin(a0), z_outer),
                    (r0*math.cos(a1), r0*math.sin(a1), z_outer),
                    (r1*math.cos(a1), r1*math.sin(a1), z_inner),
                    (r1*math.cos(a0), r1*math.sin(a0), z_inner),
                ]
                vs = [mesh.v(*q) for q in p]
                nz = -1.0 if z_sgn < 0 else 1.0
                ns = [mesh.n(0,0,nz)]*4
                if z_sgn < 0:
                    mesh.face([vs[2],vs[1],vs[0]], [ns[2],ns[1],ns[0]])
                    mesh.face([vs[3],vs[2],vs[0]], [ns[3],ns[2],ns[0]])
                else:
                    mesh.face([vs[0],vs[1],vs[2]], ns)
                    mesh.face([vs[0],vs[2],vs[3]], ns)

    # ---- Rim outer ring ----
    mesh.use("rim")
    for i in range(SEGS):
        a0 = 2*math.pi * i / SEGS
        a1 = 2*math.pi * (i+1) / SEGS
        # rim barrel
        for z0, z1 in [(-HW*0.82, HW*0.82)]:
            p = [
                (RI*math.cos(a0), RI*math.sin(a0), z0),
                (RI*math.cos(a1), RI*math.sin(a1), z0),
                (RI*math.cos(a1), RI*math.sin(a1), z1),
                (RI*math.cos(a0), RI*math.sin(a0), z1),
            ]
            vs = [mesh.v(*q) for q in p]
            ns = [mesh.n(math.cos(a0), math.sin(a0), 0),
                  mesh.n(math.cos(a1), math.sin(a1), 0),
                  mesh.n(math.cos(a1), math.sin(a1), 0),
                  mesh.n(math.cos(a0), math.sin(a0), 0)]
            mesh.face([vs[2],vs[1],vs[0]], [ns[2],ns[1],ns[0]])
            mesh.face([vs[3],vs[2],vs[0]], [ns[3],ns[2],ns[0]])

    # ---- 5 spokes ----
    mesh.use("rim")
    SPOKE_W = 0.055
    for sp in range(5):
        base_a = 2*math.pi * sp / 5
        for side in (-1, 1):
            edge_a = base_a + side * math.atan2(SPOKE_W, (RI+RIB)*0.5)
            for z_sgn in (-1, 1):
                z = z_sgn * HW * 0.76
                nz = float(z_sgn)
                pts = [
                    (RI  *math.cos(base_a-side*0.04), RI  *math.sin(base_a-side*0.04), z),
                    (RI  *math.cos(base_a+side*0.04), RI  *math.sin(base_a+side*0.04), z),
                    (RIB *math.cos(base_a+side*0.12), RIB *math.sin(base_a+side*0.12), z),
                    (RIB *math.cos(base_a-side*0.12), RIB *math.sin(base_a-side*0.12), z),
                ]
                vs = [mesh.v(*p) for p in pts]
                ns = [mesh.n(0, 0, nz)] * 4
                if z_sgn > 0:
                    mesh.face([vs[0],vs[1],vs[2]], ns)
                    mesh.face([vs[0],vs[2],vs[3]], ns)
                else:
                    mesh.face([vs[2],vs[1],vs[0]], ns)
                    mesh.face([vs[3],vs[2],vs[0]], ns)

    # ---- Hub cap ----
    mesh.use("hub")
    for i in range(SEGS):
        a0 = 2*math.pi * i / SEGS
        a1 = 2*math.pi * (i+1) / SEGS
        for z_sgn in (-1, 1):
            z  = z_sgn * HW * 0.78
            nz = float(z_sgn)
            vc = mesh.v(0, 0, z)
            nc = mesh.n(0, 0, nz)
            v0 = mesh.v(RIB*math.cos(a0), RIB*math.sin(a0), z)
            v1 = mesh.v(RIB*math.cos(a1), RIB*math.sin(a1), z)
            n0 = mesh.n(0, 0, nz)
            if z_sgn > 0:
                mesh.face([vc,v0,v1], [nc,n0,n0])
            else:
                mesh.face([vc,v1,v0], [nc,n0,n0])

    mesh.save(
        os.path.join(ASSETS_DIR, "wheel.obj"),
        os.path.join(ASSETS_DIR, "wheel.mtl"),
        mtl,
    )
    print("[Assets] wheel.obj generated")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_all():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    generate_car()
    generate_wheel()
    print("[Assets] Alle Assets erzeugt.")


def assets_exist() -> bool:
    return (os.path.exists(os.path.join(ASSETS_DIR, "car.obj")) and
            os.path.exists(os.path.join(ASSETS_DIR, "wheel.obj")))


if __name__ == "__main__":
    generate_all()
