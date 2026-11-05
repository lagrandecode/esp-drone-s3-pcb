"""Generate the drone PCB with KiCad's pcbnew API.

Run with KiCad's bundled Python:
    PYTHONPATH=tools/pylib <kicad python> tools/build.py place   # placement, outline, planes, fanout
    PYTHONPATH=tools/pylib <kicad python> tools/build.py import  # import Freerouting result, stitch, fill
"""
import json
import math
import os
import sys

import pcbnew
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB_DIR = os.path.join(ROOT, "kicad")
PCB = os.path.join(PCB_DIR, "esp_drone_s3.kicad_pcb")
PRO = os.path.join(PCB_DIR, "esp_drone_s3.kicad_pro")

OX, OY = D.BOARD_ORIGIN
VIA_D, VIA_DRILL = 0.6, 0.3
CLEARANCE = 0.2
EDGE_CLEARANCE = 0.3


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(x + OX), mm(y + OY))


def to_local(v):
    return pcbnew.ToMM(v.x) - OX, pcbnew.ToMM(v.y) - OY


# ---------------------------------------------------------------- outline
def frame_polygon():
    x0, y0, x1, y1 = D.BODY
    r = D.BODY_CORNER_R
    body = box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, resolution=16)
    shapes = [body]
    cut = []
    for n, (mx, my) in D.MOTORS.items():
        rx, ry = D.ARM_ROOTS[n]
        shapes.append(LineString([(rx, ry), (mx, my)]).buffer(D.ARM_WIDTH / 2, cap_style=2))
        shapes.append(Point(mx, my).buffer(D.RING_OUTER_D / 2, resolution=32))
        cut.append(Point(mx, my).buffer(D.MOTOR_HOLE_D / 2, resolution=32))
        ux, uy = mx / math.hypot(mx, my), my / math.hypot(mx, my)
        far = (mx + ux * D.RING_OUTER_D, my + uy * D.RING_OUTER_D)
        cut.append(LineString([(mx, my), far]).buffer(D.SLOT_WIDTH / 2, cap_style=2))
    solid = unary_union(shapes)
    f = D.FILLET_R
    solid = solid.buffer(f, resolution=16).buffer(-f, resolution=16)
    frame = solid.difference(unary_union(cut))
    frame = frame.buffer(-0.4, resolution=16).buffer(0.4, resolution=16)  # round slot corners
    assert frame.geom_type == "Polygon" and not frame.interiors, frame.geom_type
    return frame.simplify(0.005)


def add_outline(board, poly):
    coords = list(poly.exterior.coords)
    for (xa, ya), (xb, yb) in zip(coords[:-1], coords[1:]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pt(xa, ya))
        s.SetEnd(pt(xb, yb))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)


def poly_to_chain(poly, chain):
    chain.NewOutline()
    for x, y in list(poly.exterior.coords)[:-1]:
        chain.Append(mm(x + OX), mm(y + OY))


def add_zone(board, layer, net, poly, priority, thermal=True, name=""):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net)
    z.SetZoneName(name)
    poly_to_chain(poly, z.Outline())
    z.SetAssignedPriority(priority)
    z.SetMinThickness(mm(0.2))
    z.SetLocalClearance(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if thermal else pcbnew.ZONE_CONNECTION_FULL)
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


# ---------------------------------------------------------------- parts
_nets = {}


def net(board, name):
    if name not in _nets:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        _nets[name] = n
    return _nets[name]


def text(board, s, x, y, layer=pcbnew.F_SilkS, size=1.0, rot=0, thick=0.15, mirror=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(thick))
    t.SetTextAngleDegrees(rot)
    if mirror:
        t.SetMirrored(True)
    board.Add(t)
    return t


def silk_line(board, a, b, layer=pcbnew.F_SilkS, w=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(pt(*a))
    s.SetEnd(pt(*b))
    s.SetLayer(layer)
    s.SetWidth(mm(w))
    board.Add(s)


def silk_arc(board, centre, start, angle_deg, layer=pcbnew.F_SilkS, w=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetCenter(pt(*centre))
    s.SetStart(pt(*start))
    s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(angle_deg, pcbnew.DEGREES_T), True)
    s.SetLayer(layer)
    s.SetWidth(mm(w))
    board.Add(s)


def load_fp(lib, name):
    fp = pcbnew.FootprintLoad(os.path.join(D.FP_LIB, lib + ".pretty"), name)
    if fp is None:
        raise RuntimeError(f"footprint {lib}:{name} not found")
    return fp


def place_part(board, ref, spec):
    (lib, name), value, lcsc, x, y, rot, pads = spec
    fp = load_fp(lib, name)
    if name.startswith("ESP32-S3-WROOM-1"):
        # The library keep-out assumes a bare board edge 15 mm around the antenna;
        # here the antenna overhangs the front edge, so a local keep-out is added instead.
        for z in list(fp.Zones()):
            fp.Remove(z)
        for p in list(fp.Pads()):
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and pcbnew.ToMM(p.GetDrillSize().x) < 0.25:
                fp.Remove(p)
        for g in list(fp.GraphicalItems()):
            if g.GetLayer() == pcbnew.F_CrtYd:
                fp.Remove(g)
        cy = pcbnew.PCB_SHAPE(fp)
        cy.SetShape(pcbnew.SHAPE_T_RECT)
        cy.SetStart(pcbnew.VECTOR2I(mm(-9.78), mm(-12.98)))
        cy.SetEnd(pcbnew.VECTOR2I(mm(9.78), mm(13.47)))
        cy.SetLayer(pcbnew.F_CrtYd)
        cy.SetWidth(mm(0.05))
        fp.Add(cy)
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetField("LCSC", lcsc)
    fp.GetField("LCSC").SetVisible(False)
    fp.Reference().SetLayer(pcbnew.F_Fab)
    fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.5), mm(0.5)))
    fp.Reference().SetTextThickness(mm(0.08))
    fp.Value().SetVisible(False)
    board.Add(fp)
    fp.SetPosition(pt(x, y))
    fp.SetOrientationDegrees(rot)
    for p in fp.Pads():
        n = pads.get(p.GetNumber())
        if n:
            p.SetNet(net(board, n))
    return fp


def tht_pad_fp(board, ref, pads, value, exclude=True):
    """Footprint of round plated through-hole pads: pads = [(number, x, y, dia, drill, extra_vias)]."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("esp_drone", f"{value}_PADS"))
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    attrs = pcbnew.FP_THROUGH_HOLE
    if exclude:
        attrs |= pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
    fp.SetAttributes(attrs)
    cx = sum(p[1] for p in pads) / len(pads)
    cy = sum(p[2] for p in pads) / len(pads)
    fp.SetPosition(pt(cx, cy))
    board.Add(fp)
    for number, x, y, dia, drill, nets, vias in pads:
        holes = [(x, y, dia, drill)]
        for i in range(vias):
            a = 2 * math.pi * i / vias
            holes.append((x + 1.45 * math.cos(a), y + 1.45 * math.sin(a), 0.7, 0.4))
        for hx, hy, hd, hdr in holes:
            p = pcbnew.PAD(fp)
            p.SetNumber(number)
            p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            p.SetLayerSet(pcbnew.PAD.PTHMask())
            p.SetSize(pcbnew.VECTOR2I(mm(hd), mm(hd)))
            p.SetDrillSize(pcbnew.VECTOR2I(mm(hdr), mm(hdr)))
            p.SetPosition(pt(hx, hy))
            p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
            p.SetNet(net(board, nets))
            fp.Add(p)
    return fp


def arm_point(n, dist):
    mx, my = D.MOTORS[n]
    rx, ry = D.ARM_ROOTS[n]
    L = math.hypot(rx - mx, ry - my)
    return mx + (rx - mx) * dist / L, my + (ry - my) * dist / L


def arm_normal(n):
    mx, my = D.MOTORS[n]
    rx, ry = D.ARM_ROOTS[n]
    L = math.hypot(rx - mx, ry - my)
    return -(ry - my) / L, (rx - mx) / L


# ---------------------------------------------------------------- silkscreen
def add_silk(board):
    F, B = pcbnew.F_SilkS, pcbnew.B_SilkS
    for n, (mx, my) in D.MOTORS.items():
        r = (D.RING_OUTER_D + D.MOTOR_HOLE_D) / 4  # middle of the clamp ring
        spin = D.MOTOR_SPIN[n]
        # arc drawn on the outside of the ring, arrow head shows the spin direction seen from above
        ux, uy = mx / math.hypot(mx, my), my / math.hypot(mx, my)
        a0 = math.atan2(uy, ux) + math.radians(35)
        sx, sy = mx + r * math.cos(a0), my + r * math.sin(a0)
        sweep = 110  # KiCad positive arc angle is clockwise on screen
        silk_arc(board, (mx, my), (sx, sy), sweep if spin == "CW" else -sweep)
        sweep_a = a0 + math.radians(sweep if spin == "CW" else -sweep)
        ex, ey = mx + r * math.cos(sweep_a), my + r * math.sin(sweep_a)
        tx, ty = (-math.sin(sweep_a), math.cos(sweep_a)) if spin == "CW" else (math.sin(sweep_a), -math.cos(sweep_a))
        nx, ny = math.cos(sweep_a), math.sin(sweep_a)
        silk_line(board, (ex, ey), (ex - 0.9 * tx + 0.5 * nx, ey - 0.9 * ty + 0.5 * ny))
        silk_line(board, (ex, ey), (ex - 0.9 * tx - 0.5 * nx, ey - 0.9 * ty - 0.5 * ny))
        # motor label on the arm
        lx, ly = arm_point(n, 17.6)
        angle = -math.degrees(math.atan2(D.ARM_ROOTS[n][1] - my, D.ARM_ROOTS[n][0] - mx))
        if angle > 90:
            angle -= 180
        if angle < -90:
            angle += 180
        text(board, f"M{n} {spin}", lx, ly, size=1.0, rot=angle)
        nx2, ny2 = arm_normal(n)
        for sign, dist in D.MOTOR_PAD_DIST.items():
            px, py = arm_point(n, dist)
            text(board, sign, px + 2.1 * nx2, py + 2.1 * ny2, size=1.0)
    bx, by = D.BAT_PADS["+"]
    text(board, "BAT+", bx + 2.9, by + 2.7, size=0.9)
    bx, by = D.BAT_PADS["-"]
    text(board, "BAT-", bx - 4.1, by + 1.6, size=0.9)
    text(board, "BOOT", 14.4, -8.2, size=0.8, thick=0.13)
    text(board, "RST", -14.4, -8.2, size=0.8, thick=0.13)
    text(board, "R G B", -8.0, -0.6, size=0.7, thick=0.12)
    text(board, "CHG", -13.6, 0.5, size=0.6, thick=0.12)
    text(board, "FULL", -13.6, 2.5, size=0.6, thick=0.12)
    text(board, "ON", 12.6, 0.6, size=0.7, thick=0.12)
    silk_line(board, (12.6, 1.4), (12.6, 4.4))
    silk_line(board, (12.6, 1.4), (12.25, 2.0))
    silk_line(board, (12.6, 1.4), (12.95, 2.0))
    text(board, "PWR", 12.3, 6.6, size=0.7, thick=0.12, rot=90)

    # bottom side information
    lines = [
        "ESP-DRONE S3  v1.0",
        "ESP32-S3-WROOM-1-N8 + MPU-6050",
        "1S LiPo 3.7V ONLY  |  USB-C charge 400mA",
        "firmware: github.com/espressif/esp-drone",
        "motors: 716/720 brushed, 7mm rubber ring",
    ]
    for i, s in enumerate(lines):
        text(board, s, 0, -6.0 + i * 1.6, layer=B, size=0.9, thick=0.14, mirror=True)
    text(board, "JLCJLCJLCJLC", 0, 4.5, layer=B, size=0.9, thick=0.14, mirror=True)
    bx, by = D.BAT_PADS["+"]
    text(board, "BAT+", bx, by - 2.9, layer=B, size=1.0, mirror=True)
    bx, by = D.BAT_PADS["-"]
    text(board, "BAT-", bx, by - 2.9, layer=B, size=1.0, mirror=True)
    text(board, "FRONT", 0, -17.0, layer=B, size=1.2, thick=0.18, mirror=True)


# ---------------------------------------------------------------- fanout
class Obstacles:
    """Copper keep-away geometry on the outer layers, per net."""

    def __init__(self, board, frame):
        self.items = []  # (geom, net, layers)
        self.inner = frame.buffer(-(EDGE_CLEARANCE + VIA_D / 2 + 0.05))
        for fp in board.GetFootprints():
            for p in fp.Pads():
                self.items.append((self.pad_geom(p), p.GetNetname(), self.pad_layers(p), p))
                if p.GetDrillSize().x > 0:
                    x, y = to_local(p.GetPosition())
                    self.items.append((Point(x, y).buffer(pcbnew.ToMM(p.GetDrillSize().x) / 2 + 0.25), "__hole__", {"F", "B"}, None))

    @staticmethod
    def pad_layers(p):
        if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            return {"F", "B"}
        return {"F"} if p.IsOnLayer(pcbnew.F_Cu) else {"B"}

    @staticmethod
    def pad_geom(p):
        poly = p.GetEffectivePolygon(pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
        outline = poly.Outline(0)
        coords = [to_local(outline.CPoint(i)) for i in range(outline.PointCount())]
        if len(coords) < 3:
            x, y = to_local(p.GetPosition())
            return Point(x, y).buffer(pcbnew.ToMM(p.GetSize().x) / 2)
        return Polygon(coords).buffer(0)

    def free(self, geom, netname, layers):
        if not self.inner.contains(geom.centroid if geom.geom_type != "Point" else geom):
            return False
        for g, n, ls, _ in self.items:
            if n == netname and n != "__hole__":
                continue
            if not (ls & layers):
                continue
            if g.distance(geom) < CLEARANCE:
                return False
        return True

    def add(self, geom, netname, layers):
        self.items.append((geom, netname, layers, None))


def add_track(board, a, b, width, netname, layer=pcbnew.F_Cu):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pt(*a))
    t.SetEnd(pt(*b))
    t.SetWidth(mm(width))
    t.SetLayer(layer)
    t.SetNet(net(board, netname))
    t.SetLocked(True)
    board.Add(t)
    return t


def add_via(board, x, y, netname, locked=True):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pt(x, y))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetWidth(mm(VIA_D))
    v.SetDrill(mm(VIA_DRILL))
    v.SetNet(net(board, netname))
    v.SetLocked(locked)
    board.Add(v)
    return v


def fanout(board, obs, pad, count=1, stub_w=0.4):
    """Drop `count` vias next to an SMD pad so it reaches its inner plane."""
    netname = pad.GetNetname()
    px, py = to_local(pad.GetPosition())
    fx, fy = to_local(pad.GetParentFootprint().GetPosition())
    pad_g = obs.pad_geom(pad)
    out = math.atan2(py - fy, px - fx) if (px, py) != (fx, fy) else 0.0
    sx, sy = pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)
    stub_w = min(stub_w, 0.8 * min(sx, sy))
    if max(sx, sy) > 1.4 * min(sx, sy):
        # elongated pad: leave along its long axis, on the side facing away from the part
        rot = math.radians(pad.GetOrientation().AsDegrees())
        ax = (math.cos(rot), -math.sin(rot)) if sx > sy else (math.sin(rot), math.cos(rot))
        if ax[0] * math.cos(out) + ax[1] * math.sin(out) < 0:
            ax = (-ax[0], -ax[1])
        out = math.atan2(ax[1], ax[0])
    placed = []
    for step in [0.0, 0.3, 0.6, 1.0, 1.5, 2.0, 2.5]:
        for k in range(16):
            a = out + (k // 2 + 1 if k % 2 else -(k // 2)) * math.pi / 8 if k else out
            # distance from pad centre to clear the pad edge
            for base in (0.0,):
                d0 = 0.0
                while Point(px + d0 * math.cos(a), py + d0 * math.sin(a)).within(pad_g) and d0 < 5:
                    d0 += 0.05
                d = d0 + VIA_D / 2 + 0.05 + step
                vx, vy = px + d * math.cos(a), py + d * math.sin(a)
                via_g = Point(vx, vy).buffer(VIA_D / 2)
                stub = LineString([(px, py), (vx, vy)]).buffer(stub_w / 2)
                if not obs.free(via_g, netname, {"F", "B"}):
                    continue
                if not obs.free(stub, netname, {"F"}):
                    continue
                if any(Point(vx, vy).distance(Point(q)) < VIA_D + CLEARANCE for q in placed):
                    continue
                add_track(board, (px, py), (vx, vy), stub_w, netname)
                add_via(board, vx, vy, netname)
                obs.add(via_g, netname, {"F", "B"})
                obs.add(stub, netname, {"F"})
                placed.append((vx, vy))
                if len(placed) >= count:
                    return placed
    if not placed:
        raise RuntimeError(f"no fanout spot for {pad.GetParentFootprint().GetReference()}.{pad.GetNumber()} ({netname})")
    return placed


def imu_escape(board):
    """Fixed escape routes for the MPU-6050 top pin row (8..12), which has GND pins
    on both sides of REGOUT and no room for the autorouter to place vias.
    Offsets are relative to the package centre with the part rotated 180 degrees."""
    u2 = board.FindFootprintByReference("U2")
    assert round(abs(u2.GetOrientationDegrees())) == 180
    cx, cy = to_local(u2.GetPosition())
    routes = [
        ("GND", 0.2, [(-0.75, -1.95), (-0.75, -2.8), (-1.0, -3.4)], True),          # pin 11 FSYNC
        ("GND", 0.2, [(0.25, -1.95), (0.25, -2.8), (0.5, -3.4)], True),             # pin 9 AD0
        ("MPU_REGOUT", 0.2, [(-0.25, -1.95), (-0.25, -4.0)], True),                 # pin 10
        ("IMU_INT", 0.2, [(-1.25, -1.95), (-1.25, -2.2), (-1.85, -2.8), (-1.85, -4.6)], False),
        ("3V3", 0.25, [(0.75, -1.95), (0.75, -2.7), (1.35, -3.3)], False),          # pin 8 VLOGIC
    ]
    for netname, w, path, via in routes:
        pts = [(cx + x, cy + y) for x, y in path]
        for a, b in zip(pts[:-1], pts[1:]):
            add_track(board, a, b, w, netname)
        if via:
            add_via(board, *pts[-1], netname)


def do_fanout(board, frame):
    imu_escape(board)
    done = set()
    seen_pos = set()
    obs = Obstacles(board, frame)
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            x, y = to_local(t.GetPosition())
            obs.add(Point(x, y).buffer(VIA_D / 2), t.GetNetname(), {"F", "B"})
        else:
            obs.add(LineString([to_local(t.GetStart()), to_local(t.GetEnd())]).buffer(0.1), t.GetNetname(), {"F"})
    heavy = {("Q1", "2"): 3, ("Q2", "2"): 3, ("Q3", "2"): 3, ("Q4", "2"): 3,
             ("D1", "1"): 2, ("D2", "1"): 2, ("D3", "1"): 2, ("D4", "1"): 2,
             ("C8", "1"): 2, ("C8", "2"): 2, ("C9", "1"): 2, ("C9", "2"): 2,
             ("U1", "41"): 4, ("U3", "9"): 2}
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        for p in fp.Pads():
            if p.GetNetname() not in ("GND", "VBAT"):
                continue
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            key = (fp.GetReference(), p.GetNumber())
            if key in {("U2", "9"), ("U2", "11")}:
                continue  # IMU top-row GND pins sit beside REGOUT/VLOGIC; fixroute.py finishes them
            pos = (p.GetPosition().x, p.GetPosition().y)
            if key in done or pos in seen_pos:
                continue
            done.add(key)
            seen_pos.add(pos)
            if fp.GetReference() == "U1" and p.GetNumber() == "41":
                if p.GetSize().x < mm(3):
                    continue  # paste-only sub-pads share the number
            fanout(board, obs, p, heavy.get(key, 1))
            if key in {("Q1", "2"), ("Q2", "2"), ("Q3", "2"), ("Q4", "2")}:
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    return obs


# ---------------------------------------------------------------- project / rules
def write_project():
    classes = [{
        "name": "Default", "clearance": CLEARANCE, "track_width": 0.2, "via_diameter": VIA_D,
        "via_drill": VIA_DRILL, "microvia_diameter": 0.3, "microvia_drill": 0.1,
        "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
        "wire_width": 6, "bus_width": 12, "line_style": 0, "schematic_color": "rgba(0, 0, 0, 0.000)",
        "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647,
    }]
    patterns = []
    for i, (name, (w, c, nets)) in enumerate(D.NETCLASSES.items()):
        cls = dict(classes[0])
        cls.update({"name": name, "clearance": c, "track_width": w, "priority": i})
        classes.append(cls)
        patterns += [{"netclass": name, "pattern": n} for n in nets]
    pro = {
        "board": {
            "design_settings": {
                "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2},
                "rules": {
                    "min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.5,
                    "min_through_hole_diameter": 0.3, "min_via_annular_width": 0.1,
                    "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25,
                    "min_copper_edge_clearance": EDGE_CLEARANCE, "min_silk_clearance": 0.0,
                    "min_text_height": 0.6, "min_text_thickness": 0.1,
                    "solder_mask_to_copper_clearance": 0.0, "min_microvia_diameter": 0.2,
                    "min_microvia_drill": 0.1, "min_resolved_spokes": 1,
                },
                "rule_severities": {
                    "silk_overlap": "ignore", "silk_over_copper": "ignore", "silk_edge_clearance": "ignore",
                    "lib_footprint_issues": "ignore", "lib_footprint_mismatch": "ignore",
                    "text_height": "warning", "text_thickness": "warning",
                    "footprint_type_mismatch": "ignore", "missing_courtyard": "ignore",
                    "courtyards_overlap": "error",
                },
                "track_widths": [0.0, 0.2, 0.3, 0.5, 0.8, 1.0],
                "via_dimensions": [{"diameter": 0.0, "drill": 0.0}, {"diameter": VIA_D, "drill": VIA_DRILL}],
            },
        },
        "meta": {"filename": "esp_drone_s3.kicad_pro", "version": 3},
        "net_settings": {"classes": classes, "meta": {"version": 4}, "netclass_patterns": patterns},
    }
    json.dump(pro, open(PRO, "w"), indent=2)


# ---------------------------------------------------------------- stages
def stage_place():
    os.makedirs(PCB_DIR, exist_ok=True)
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(4)
    board.SetLayerName(pcbnew.In1_Cu, "In1.GND")
    board.SetLayerName(pcbnew.In2_Cu, "In2.VBAT")
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(1.6))

    frame = frame_polygon()
    add_outline(board, frame)

    for ref, spec in D.PARTS.items():
        place_part(board, ref, spec)

    for n in D.MOTORS:
        pads = []
        for sign, dist in D.MOTOR_PAD_DIST.items():
            x, y = arm_point(n, dist)
            pads.append(("1" if sign == "+" else "2", x, y, 2.0, 1.0, "VBAT" if sign == "+" else f"MOT{n}_N", 0))
        tht_pad_fp(board, f"M{n}", pads, "MOTOR")
    tht_pad_fp(board, "BT1", [
        ("1", *D.BAT_PADS["+"], 4.0, 1.2, "VBAT", 6),
        ("2", *D.BAT_PADS["-"], 4.0, 1.2, "GND", 6),
    ], "BATTERY")

    add_silk(board)

    # planes: GND on In1, VBAT on In2, GND pours on both outer layers
    add_zone(board, pcbnew.In1_Cu, net(board, "GND"), frame, 0, name="GND_PLANE")
    add_zone(board, pcbnew.In2_Cu, net(board, "VBAT"), frame, 0, name="VBAT_PLANE")
    add_zone(board, pcbnew.F_Cu, net(board, "GND"), frame, 0, name="GND_TOP")
    add_zone(board, pcbnew.B_Cu, net(board, "GND"), frame, 0, name="GND_BOT")

    do_fanout(board, frame)

    pcbnew.SaveBoard(PCB, board)
    write_project()
    print("placed", len(list(board.GetFootprints())), "footprints")


def stage_import(ses, finish=True):
    board = pcbnew.LoadBoard(PCB)
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise RuntimeError("SES import failed")
    if finish:
        stitch(board, frame_polygon())
        fill(board)
    pcbnew.SaveBoard(PCB, board)
    print("imported", ses)


def stitch(board, frame, pitch=3.0):
    """GND stitching vias over free board area to tie the outer pours to the GND plane."""
    obs = Obstacles(board, frame)
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            x, y = to_local(t.GetPosition())
            obs.add(Point(x, y).buffer(VIA_D / 2 + 0.1), t.GetNetname(), {"F", "B"})
        else:
            a, b = to_local(t.GetStart()), to_local(t.GetEnd())
            layer = "F" if t.GetLayer() == pcbnew.F_Cu else "B" if t.GetLayer() == pcbnew.B_Cu else "I"
            obs.add(LineString([a, b]).buffer(pcbnew.ToMM(t.GetWidth()) / 2), t.GetNetname(), {layer})
    # keep stitching vias out from under the module and the IMU
    no_go = [box(-9.9, -28.0, 9.9, -1.4), box(-3.2, -0.2, 3.2, 6.2)]
    minx, miny, maxx, maxy = frame.bounds
    holes = [to_local(t.GetPosition()) for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    holes += [to_local(p.GetPosition()) for fp in board.GetFootprints() for p in fp.Pads() if p.GetDrillSize().x > 0]
    count = 0
    y = miny
    while y <= maxy:
        x = minx
        while x <= maxx:
            g = Point(x, y).buffer(VIA_D / 2 + 0.15)
            if (not any(n.intersects(g) for n in no_go) and obs.free(g, "GND", {"F", "B"})
                    and all(math.hypot(x - hx, y - hy) > 1.6 for hx, hy in holes)):
                add_via(board, x, y, "GND", locked=False)
                obs.add(Point(x, y).buffer(VIA_D / 2), "GND", {"F", "B"})
                holes.append((x, y))
                count += 1
            x += pitch
        y += pitch
    print("stitching vias:", count)


def fill(board):
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


if __name__ == "__main__":
    stage = sys.argv[1]
    if stage == "place":
        stage_place()
    elif stage == "dsn":
        b = pcbnew.LoadBoard(PCB)
        if not pcbnew.ExportSpecctraDSN(b, sys.argv[2]):
            raise RuntimeError("DSN export failed")
        print("exported", sys.argv[2])
    elif stage == "import":
        stage_import(sys.argv[2], finish="--raw" not in sys.argv)
    elif stage == "silk":
        b = pcbnew.LoadBoard(PCB)
        for d in list(b.GetDrawings()):
            if d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                b.Remove(d)
        add_silk(b)
        pcbnew.SaveBoard(PCB, b)
        print("silkscreen regenerated")
    elif stage == "fill":
        b = pcbnew.LoadBoard(PCB)
        fill(b)
        pcbnew.SaveBoard(PCB, b)
    else:
        sys.exit("unknown stage")
