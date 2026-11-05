#!/bin/sh
# Render selected layers to a cropped PNG: render.sh <name> <layers> [dpi] [cx cy size]
# cx, cy are frame coordinates in mm (board centre = 0,0); default view is the whole board.
set -e
cd "$(dirname "$0")/.."
KC=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
DPI=${3:-250}
CX=${4:-0}
CY=${5:-0}
SIZE_MM=${6:-92}
mkdir -p out
"$KC" pcb export pdf --layers "$2" --mode-single -o "out/$1.pdf" kicad/esp_drone_s3.kicad_pcb >/dev/null
pdftoppm -r "$DPI" -png -singlefile "out/$1.pdf" "out/$1" 2>/dev/null
rm "out/$1.pdf"
read OX OY SIZE <<EOF
$(python3 -c "d=$DPI/25.4; print(int((100+$CX-$SIZE_MM/2)*d), int((100+$CY-$SIZE_MM/2)*d), int($SIZE_MM*d))")
EOF
sips -c "$SIZE" "$SIZE" --cropOffset "$OY" "$OX" "out/$1.png" >/dev/null
echo "out/$1.png"
