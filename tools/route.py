"""Autoroute signal nets with Freerouting.

GND and VBAT (net class PLANE) are skipped: they are carried by the inner
planes and the fanout vias placed by build.py. Outer-layer GND pours are
removed from the DSN because KiCad refills them after the routes come back.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JAR = os.path.join(ROOT, "tools", "freerouting-2.5.0.jar")
JAVA = "/opt/homebrew/opt/openjdk@25/bin/java"


def strip_outer_planes(text):
    out, i = [], 0
    pat = re.compile(r"\(plane \S+ \(polygon (F\.Cu|B\.Cu) ")
    while True:
        m = pat.search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i:m.start()])
        depth, j = 0, m.start()
        while True:
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1
    return "".join(out)


def ensure_jar():
    if not os.path.exists(JAR):
        url = "https://github.com/freerouting/freerouting/releases/download/v2.5.0/freerouting-2.5.0.jar"
        print("downloading", url)
        subprocess.run(["curl", "-sL", "-o", JAR, url], check=True)


def main(dsn, ses, passes="40"):
    ensure_jar()
    text = open(dsn).read()
    routed_dsn = dsn.replace(".dsn", "_route.dsn")
    open(routed_dsn, "w").write(strip_outer_planes(text))
    cmd = [JAVA, "-Djava.awt.headless=true", "-jar", JAR, "-de", routed_dsn, "-do", ses,
           "-mp", passes, "-mt", "8", "-inc", "PLANE", "--gui.enabled=false",
           "--usage_and_diagnostic_data.disable_analytics=true"]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
