"""Generate JLCPCB fabrication + assembly files.

Outputs in production/:
  esp_drone_s3_gerbers.zip   Gerber + Excellon drill files (upload as the PCB)
  esp_drone_s3_bom.csv       BOM with LCSC part numbers (JLCPCB format)
  esp_drone_s3_cpl.csv       pick-and-place file (JLCPCB format)

Placement rotations and centroids are corrected per part by comparing each
KiCad footprint's pads with the pads of JLCPCB's own (EasyEDA) footprint for
that LCSC number, cached in tools/easyeda_pads.json.
"""
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D  # noqa: E402
from build import PCB  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROD = os.path.join(ROOT, "production")
KC = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
EASY = json.load(open(os.path.join(ROOT, "tools", "easyeda_pads.json")))
NAME = "esp_drone_s3"


def rot(x, y, deg):
    """Rotate counter-clockwise as seen on screen (KiCad / JLCPCB convention, y axis down)."""
    a = math.radians(deg)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def kicad_pads(lib, name):
    fp = pcbnew.FootprintLoad(os.path.join(D.FP_LIB, lib + ".pretty"), name)
    out = {}
    for p in fp.Pads():
        if not p.GetNumber() or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            continue
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and pcbnew.ToMM(p.GetDrillSize().x) < 0.25:
            continue  # thermal vias inside exposed pads
        out.setdefault(p.GetNumber(), []).append((pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)))
    return out


def easyeda_pads(lcsc):
    out = {}
    remap = {v: k for k, v in D.EASYEDA_PAD_MAP.get(lcsc, {}).items()}
    for num, x, y, *_ in EASY[lcsc]["pads"]:
        names = re.findall(r"[AB]\d+", num) if re.fullmatch(r"([AB]\d+){2,}", num) else [num]
        for n in names:
            out.setdefault(remap.get(n, n), []).append((x, y))
    return out


def correction(lcsc, lib, name):
    """Return (rotation, (dx, dy), rms_error) mapping JLC footprint onto the KiCad one."""
    kp, ep = kicad_pads(lib, name), easyeda_pads(lcsc)
    pairs = [(kp[n][0], ep[n][0]) for n in kp if n in ep and len(kp[n]) == 1 and len(ep[n]) == 1]
    best = None
    for theta in (0, 90, 180, 270):
        if len(pairs) >= 2:
            er = [rot(*e, theta) for _, e in pairs]
            k = [kk for kk, _ in pairs]
            dx = sum(a[0] - b[0] for a, b in zip(k, er)) / len(k)
            dy = sum(a[1] - b[1] for a, b in zip(k, er)) / len(k)
            err = math.sqrt(sum((a[0] - b[0] - dx) ** 2 + (a[1] - b[1] - dy) ** 2 for a, b in zip(k, er)) / len(k))
        else:  # unnumbered match (symmetric parts such as 4-pad tact switches)
            kall = [q for v in kp.values() for q in v]
            eall = [rot(*q, theta) for v in ep.values() for q in v]
            kcx, kcy = sum(q[0] for q in kall) / len(kall), sum(q[1] for q in kall) / len(kall)
            ecx, ecy = sum(q[0] for q in eall) / len(eall), sum(q[1] for q in eall) / len(eall)
            dx, dy = kcx - ecx, kcy - ecy
            err = math.sqrt(sum(min((a[0] - b[0] - dx) ** 2 + (a[1] - b[1] - dy) ** 2 for b in eall) for a in kall) / len(kall))
        if best is None or err < best[2] - 1e-6:
            best = (theta, (dx, dy), err)
    return best


def write_bom_cpl(board):
    rows, groups, report = [], {}, []
    cache = {}
    for ref, spec in D.PARTS.items():
        (lib, name), value, lcsc, *_ = spec
        fp = board.FindFootprintByReference(ref)
        if (lcsc, name) not in cache:
            cache[(lcsc, name)] = correction(lcsc, lib, name)
            th, (dx, dy), err = cache[(lcsc, name)]
            report.append(f"{lcsc:9} {name:45} rot {th:3d}  offset ({dx:+.3f},{dy:+.3f}) mm  rms {err:.3f} mm")
            if err > 0.5:  # pad-length conventions differ by up to ~0.45 mm along the pad axis
                raise RuntimeError(f"footprint mismatch for {ref} {lcsc}: rms {err:.3f} mm")
        th, (dx, dy), _ = cache[(lcsc, name)]
        r = fp.GetOrientationDegrees()
        px, py = pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y)
        ox, oy = rot(dx, dy, r)
        rows.append([ref, f"{px + ox:.4f}mm", f"{-(py + oy):.4f}mm", "Top", f"{(r + th) % 360:.1f}"])
        groups.setdefault((value, name, lcsc), []).append(ref)

    def natural(s):
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]

    with open(os.path.join(PROD, f"{NAME}_cpl.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(sorted(rows, key=lambda r: natural(r[0])))
    with open(os.path.join(PROD, f"{NAME}_bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Quantity"])
        for (value, name, lcsc), refs in sorted(groups.items(), key=lambda g: natural(sorted(g[1], key=natural)[0])):
            w.writerow([value, ",".join(sorted(refs, key=natural)), name, lcsc, len(refs)])
    open(os.path.join(PROD, "jlc_corrections.txt"), "w").write("\n".join(report) + "\n")
    print("\n".join(report))


def gerbers():
    gdir = os.path.join(PROD, "gerbers")
    shutil.rmtree(gdir, ignore_errors=True)
    os.makedirs(gdir)
    layers = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"
    subprocess.run([KC, "pcb", "export", "gerbers", "-o", gdir, "--layers", layers, "--subtract-soldermask",
                    "--check-zones", PCB], check=True, capture_output=True)
    subprocess.run([KC, "pcb", "export", "drill", "-o", gdir + "/", "--format", "excellon", "--excellon-units", "mm",
                    "--excellon-zeros-format", "decimal", "--drill-origin", "absolute", "--excellon-separate-th",
                    "--excellon-oval-format", "alternate", PCB], check=True, capture_output=True)
    zpath = os.path.join(PROD, f"{NAME}_gerbers.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(gdir)):
            if fn.endswith(".gbrjob"):
                continue
            z.write(os.path.join(gdir, fn), fn)
    print("gerbers:", ", ".join(sorted(os.listdir(gdir))))


def netlist(board):
    nets = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname():
                nets.setdefault(p.GetNetname(), set()).add(f"{fp.GetReference()}.{p.GetNumber()}")

    def natural(s):
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]

    with open(os.path.join(PROD, f"{NAME}_netlist.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Net", "Pins"])
        for n in sorted(nets, key=natural):
            w.writerow([n, " ".join(sorted(nets[n], key=natural))])


def renders():
    for side in ("top", "bottom"):
        subprocess.run([KC, "pcb", "render", "--side", side, "--quality", "high", "-w", "1600", "-h", "1600",
                        "--background", "opaque", "-o", os.path.join(PROD, f"render_{side}.png"), PCB],
                       check=True, capture_output=True)
    subprocess.run([KC, "pcb", "render", "--side", "top", "--quality", "high", "-w", "1800", "-h", "1200",
                    "--rotate", "-40,0,25", "--perspective", "--background", "opaque",
                    "-o", os.path.join(PROD, "render_iso.png"), PCB], check=True, capture_output=True)


if __name__ == "__main__":
    os.makedirs(PROD, exist_ok=True)
    board = pcbnew.LoadBoard(PCB)
    write_bom_cpl(board)
    netlist(board)
    gerbers()
    if "--no-render" not in sys.argv:
        renders()
