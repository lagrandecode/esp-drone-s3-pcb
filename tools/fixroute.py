"""Finish connections Freerouting left open with a small two-layer A* maze router.

Reads the unconnected pairs from out/drc.json (written by drc.py), routes each on
a 0.05 mm grid around the pair with the net class track width and clearance,
and adds the tracks/vias to the board.
"""
import heapq
import json
import math
import os
import sys

import numpy as np
import pcbnew
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D  # noqa: E402
from build import PCB, VIA_D, VIA_DRILL, frame_polygon, mm, to_local  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRID = 0.05
MARGIN = 6.0
CLEARANCE = 0.2
VIA_COST = 40.0
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]


def net_width(name):
    for w, _c, nets in D.NETCLASSES.values():
        if name in nets:
            return w
    return 0.2


def pad_poly(p, layer):
    poly = p.GetEffectivePolygon(layer)
    o = poly.Outline(0)
    return Polygon([to_local(o.CPoint(i)) for i in range(o.PointCount())]).buffer(0)


def item_geoms(item):
    """{layer: geometry} for a pad, track or via."""
    out = {}
    if item.Type() == pcbnew.PCB_PAD_T:
        for layer in LAYERS:
            if item.IsOnLayer(layer):
                out[layer] = pad_poly(item, layer)
    elif item.Type() == pcbnew.PCB_VIA_T:
        x, y = to_local(item.GetPosition())
        g = Point(x, y).buffer(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)) / 2)
        out = {layer: g for layer in LAYERS}
    elif item.Type() == pcbnew.PCB_TRACE_T:
        if item.GetLayer() in LAYERS:
            g = LineString([to_local(item.GetStart()), to_local(item.GetEnd())]).buffer(pcbnew.ToMM(item.GetWidth()) / 2)
            out[item.GetLayer()] = g
    return out


def collect(board):
    """All copper on the outer layers: list of (netname, {layer: geom}), plus drill holes."""
    items, holes = [], []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            items.append((p.GetNetname(), item_geoms(p)))
            if p.GetDrillSize().x > 0:
                holes.append(Point(*to_local(p.GetPosition())).buffer(pcbnew.ToMM(p.GetDrillSize().x) / 2))
    for t in board.GetTracks():
        items.append((t.GetNetname(), item_geoms(t)))
        if t.Type() == pcbnew.PCB_VIA_T:
            holes.append(Point(*to_local(t.GetPosition())).buffer(VIA_DRILL / 2))
    keepouts = []
    for fp in board.GetFootprints():
        for z in fp.Zones():
            if z.GetIsRuleArea():
                o = z.Outline().Outline(0)
                keepouts.append(Polygon([to_local(o.CPoint(i)) for i in range(o.PointCount())]))
    return items, holes, keepouts


def route(board, a, b, netname, items, holes, keepouts, frame):
    ga, gb = item_geoms(a), item_geoms(b)
    w = net_width(netname)
    allg = list(ga.values()) + list(gb.values())
    minx, miny, maxx, maxy = unary_union(allg).bounds
    minx, miny, maxx, maxy = minx - MARGIN, miny - MARGIN, maxx + MARGIN, maxy + MARGIN
    nx, ny = int((maxx - minx) / GRID) + 1, int((maxy - miny) / GRID) + 1
    xs = minx + np.arange(nx) * GRID
    ys = miny + np.arange(ny) * GRID
    X, Y = np.meshgrid(xs, ys, indexing="ij")

    inner = frame.buffer(-(0.3 + w / 2))
    via_inner = frame.buffer(-(0.3 + VIA_D / 2))
    free, goal, start = [], [], []
    for layer in LAYERS:
        foreign = [g[layer] for n, g in items if n != netname and layer in g]
        blocked = unary_union(foreign).buffer(CLEARANCE + w / 2 + 0.01)
        if layer == pcbnew.F_Cu and keepouts:
            blocked = blocked.union(unary_union(keepouts).buffer(w / 2))
        f = ~shapely.contains_xy(blocked, X, Y) & shapely.contains_xy(inner, X, Y)
        free.append(f)
        goal.append(shapely.contains_xy(gb[layer], X, Y) if layer in gb else np.zeros_like(f))
        start.append(shapely.contains_xy(ga[layer], X, Y) if layer in ga else np.zeros_like(f))
    foreign_all = unary_union([g for n, gs in items if n != netname for g in gs.values()])
    via_block = foreign_all.buffer(CLEARANCE + VIA_D / 2 + 0.01).union(unary_union(holes).buffer(0.25 + VIA_DRILL / 2 + 0.01))
    if keepouts:
        via_block = via_block.union(unary_union(keepouts).buffer(VIA_D / 2))
    via_ok = ~shapely.contains_xy(via_block, X, Y) & shapely.contains_xy(via_inner, X, Y)
    if netname in ("GND", "VBAT"):
        # a through via reaches the inner plane of this net, so any legal via site is a goal
        for li in range(2):
            goal[li] = goal[li] | (via_ok & ~start[li])
    for li in range(2):
        free[li] |= goal[li] | start[li]

    gpts = np.argwhere(goal[0] | goal[1])
    gx, gy = gpts[:, 0].mean(), gpts[:, 1].mean()

    def h(i, j):
        return math.hypot(i - gx, j - gy) * 0.5

    openq, came, cost = [], {}, {}
    for li in range(2):
        for i, j in np.argwhere(start[li]):
            s = (li, int(i), int(j))
            cost[s] = 0.0
            heapq.heappush(openq, (h(i, j), s))
    steps = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    end = None
    expansions = 0
    while openq and expansions < 600000:
        _, cur = heapq.heappop(openq)
        expansions += 1
        li, i, j = cur
        if goal[li][i, j]:
            end = cur
            break
        c0 = cost[cur]
        nbrs = [((li, i + di, j + dj), sc) for di, dj, sc in steps]
        if via_ok[i, j]:
            nbrs.append(((1 - li, i, j), VIA_COST))
        for nxt, sc in nbrs:
            l2, i2, j2 = nxt
            if not (0 <= i2 < nx and 0 <= j2 < ny) or not free[l2][i2, j2]:
                continue
            c = c0 + sc
            if c < cost.get(nxt, 1e18):
                cost[nxt] = c
                came[nxt] = cur
                heapq.heappush(openq, (c + h(i2, j2), nxt))
    if end is None:
        return False
    path = [end]
    while path[-1] in came:
        path.append(came[path[-1]])
    path.reverse()
    pts = [(li, float(xs[i]), float(ys[j])) for li, i, j in path]
    emit(board, pts, netname, w)
    if netname in ("GND", "VBAT") and not (gb.get(LAYERS[end[0]]) and gb[LAYERS[end[0]]].contains(Point(pts[-1][1], pts[-1][2]))):
        add_plane_via(board, pts[-1][1], pts[-1][2], netname)
    return True


def add_plane_via(board, x, y, netname):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(mm(x + 100), mm(y + 100)))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetWidth(mm(VIA_D))
    v.SetDrill(mm(VIA_DRILL))
    v.SetNet(board.FindNet(netname))
    board.Add(v)


def emit(board, pts, netname, w):
    net = board.FindNet(netname)

    def flush(run, layer):
        simp = LineString([(x, y) for x, y in run]).simplify(GRID * 0.6) if len(run) > 1 else None
        if simp is None:
            return
        c = list(simp.coords)
        for (xa, ya), (xb, yb) in zip(c[:-1], c[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(mm(xa + 100), mm(ya + 100)))
            t.SetEnd(pcbnew.VECTOR2I(mm(xb + 100), mm(yb + 100)))
            t.SetWidth(mm(w))
            t.SetLayer(layer)
            t.SetNet(net)
            board.Add(t)

    run, layer = [], pts[0][0]
    for li, x, y in pts:
        if li != layer:
            flush(run, LAYERS[layer])
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(mm(x + 100), mm(y + 100)))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetWidth(mm(VIA_D))
            v.SetDrill(mm(VIA_DRILL))
            v.SetNet(net)
            board.Add(v)
            run, layer = [run[-1]] if run else [], li
        run.append((x, y))
    flush(run, LAYERS[layer])


def cleanup(board, drc):
    """Delete vias/tracks DRC reports as dangling (autorouter leftovers)."""
    n = 0
    for v in drc["violations"]:
        if v["type"] in ("via_dangling", "track_dangling"):
            item = board.ResolveItem(pcbnew.KIID(v["items"][0]["uuid"]))
            if item is not None:
                board.Remove(item.Cast())
                n += 1
    return n


def main():
    board = pcbnew.LoadBoard(PCB)
    drc = json.load(open(os.path.join(ROOT, "out", "drc.json")))
    if "--cleanup" in sys.argv:
        print("removed", cleanup(board, drc), "dangling items")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(PCB, board)
        return
    frame = frame_polygon()
    ok = 0
    for u in drc["unconnected_items"]:
        a = board.ResolveItem(pcbnew.KIID(u["items"][0]["uuid"])).Cast()
        b = board.ResolveItem(pcbnew.KIID(u["items"][1]["uuid"])).Cast()
        netname = a.GetNetname()
        items, holes, keepouts = collect(board)
        done = route(board, a, b, netname, items, holes, keepouts, frame)
        print(("routed " if done else "FAILED ") + " / ".join(i["description"][:50] for i in u["items"]))
        ok += done
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)
    print(f"{ok}/{len(drc['unconnected_items'])} connections completed")


if __name__ == "__main__":
    main()
