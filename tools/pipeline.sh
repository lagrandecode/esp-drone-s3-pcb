#!/bin/sh
# Full board generation: place -> route (two Freerouting passes) -> stitch/fill -> finish leftovers -> DRC
set -e
cd "$(dirname "$0")/.."
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
export PYTHONPATH=tools/pylib
quiet() { grep -v "wxApp\|traits" || true; }

$PY tools/build.py place 2>&1 | quiet
$PY tools/build.py dsn out/pass1.dsn 2>&1 | quiet
python3 tools/route.py out/pass1.dsn out/pass1.ses "${PASSES:-60}" 2>&1 | grep -E "Auto-routing stage completed" || true
$PY tools/build.py import out/pass1.ses --raw 2>&1 | quiet
$PY tools/build.py dsn out/pass2.dsn 2>&1 | quiet
python3 tools/route.py out/pass2.dsn out/pass2.ses "${PASSES:-60}" 2>&1 | grep -E "Auto-routing stage completed|optimization stage completed" || true
$PY tools/build.py import out/pass2.ses 2>&1 | quiet
for i in 1 2 3; do
    python3 tools/drc.py > out/drc_summary.txt
    grep -q "^unconnected: 0" out/drc_summary.txt && break
    $PY tools/fixroute.py 2>&1 | quiet
done
python3 tools/drc.py > out/drc_summary.txt
$PY tools/fixroute.py --cleanup 2>&1 | quiet
python3 tools/drc.py
