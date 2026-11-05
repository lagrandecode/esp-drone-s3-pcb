"""Run KiCad DRC and summarise the report."""
import collections
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KC = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PCB = os.path.join(ROOT, "kicad", "esp_drone_s3.kicad_pcb")
OUT = os.path.join(ROOT, "out", "drc.json")

subprocess.run([KC, "pcb", "drc", "--format", "json", "--severity-error", "--severity-warning",
                "--schematic-parity" if "--parity" in sys.argv else "--refill-zones", "-o", OUT, PCB],
               check=True, capture_output=True)
d = json.load(open(OUT))
viol = d["violations"]
print("violations:", dict(collections.Counter(f'{v["severity"]}:{v["type"]}' for v in viol)))
print("unconnected:", len(d["unconnected_items"]))
limit = int(os.environ.get("N", "40"))
for v in viol[:limit]:
    pos = v["items"][0].get("pos", {})
    print(f'  {v["severity"]} {v["type"]}: {v["description"]} @({pos.get("x", 0) - 100:.2f},{pos.get("y", 0) - 100:.2f})',
          "|", " / ".join(i["description"][:60] for i in v["items"]))
for v in d["unconnected_items"][:limit]:
    pos = v["items"][0].get("pos", {})
    print(f'  UNCONNECTED @({pos.get("x", 0) - 100:.2f},{pos.get("y", 0) - 100:.2f})', " / ".join(i["description"][:60] for i in v["items"]))
