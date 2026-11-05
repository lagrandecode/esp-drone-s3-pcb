"""Fetch JLCPCB/EasyEDA footprint pads for LCSC parts (mm, relative to footprint origin, y down).

Results are merged into easyeda_pads.json so repeated runs only fetch missing parts.
"""
import json
import os
import sys
import time
import urllib.request

URL = "https://easyeda.com/api/products/{}/components?version=6.4.19.5"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "easyeda_pads.json")


def pads(lcsc):
    req = urllib.request.Request(URL.format(lcsc), headers={"User-Agent": "curl/8.7.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)["result"]
    pkg = res["packageDetail"]["dataStr"]
    ox, oy = float(pkg["head"]["x"]), float(pkg["head"]["y"])
    out = []
    for s in pkg["shape"]:
        f = s.split("~")
        if f[0] != "PAD":
            continue
        x = (float(f[2]) - ox) * 0.254
        y = (float(f[3]) - oy) * 0.254
        out.append((f[8], round(x, 3), round(y, 3), round(float(f[4]) * 0.254, 2), round(float(f[5]) * 0.254, 2)))
    return res["packageDetail"]["title"], out


if __name__ == "__main__":
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    for part in sys.argv[1:]:
        if part in cache:
            continue
        for attempt in range(6):
            try:
                title, p = pads(part)
                break
            except Exception as e:  # rate limiting shows up as HTTP 403
                print(f"{part}: {e}, retrying")
                time.sleep(20 * (attempt + 1))
        else:
            sys.exit(f"failed to fetch {part}")
        cache[part] = {"package": title, "pads": p}
        json.dump(cache, open(CACHE, "w"), indent=1)
        print(f"fetched {part} {title}")
        time.sleep(3)
