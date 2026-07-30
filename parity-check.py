#!/usr/bin/env python3
# parity-check.py - prove the v2 contracts say the SAME THING as the legacy dashboard.
#
# Both are produced by a single gen-dashboard run from one gathered dict, so any disagreement here is a mapping
# bug in emit_ops - which is exactly what this is for. Run it after any producer or emitter change; it is also a
# candidate regression line for verify-brain.ps1 in P6.
#
# Exit 0 = every checked value matches. Exit 1 = at least one disagreement (printed).
import json, os, re, sys, urllib.request

BRAIN = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BRAIN, "data")
LEGACY_URL = "http://127.0.0.1:8500/"


def contract(name):
    with open(os.path.join(DATA, name + ".json"), encoding="utf-8-sig") as fh:
        return json.load(fh)["data"]


def fmt_bytes(b):
    """Byte-for-byte the legacy page's fmt() so the comparison is exact, not approximate."""
    g = b / 1073741824
    return ("%.1f TB" % (g / 1024)) if g >= 1024 else ("%.0f GB" % g)


def grab(pattern, html, label, flags=0):
    m = re.search(pattern, html, flags)
    return m.groups() if m else None


def main():
    html = urllib.request.urlopen(LEGACY_URL, timeout=30).read().decode("utf-8", errors="replace")
    rows, bad = [], 0

    def cmp(label, legacy, v2):
        nonlocal bad
        ok = str(legacy) == str(v2)
        if not ok:
            bad += 1
        rows.append((label, legacy, v2, "MATCH" if ok else "DIFFER"))

    svc = contract("services")
    g = grab(r"<h2>Services &middot; (\d+)/(\d+)</h2>|<h2>Services · (\d+)/(\d+)</h2>", html, "services")
    if g:
        vals = [x for x in g if x is not None]
        cmp("services up", vals[0], svc["up_count"])
        cmp("services total", vals[1], svc["total"])

    lib = contract("library-stats")
    for label, key, path in (("Movies (Plex)", "movies", ("plex", "movies")),
                             ("TV Shows", "tv", ("plex", "tv")),
                             ("Rated", "rated", ("rated",))):
        g = grab(r'<div class="n">([^<]+)</div><div class="l">%s</div>' % re.escape(label), html, label)
        if g:
            v = lib
            for p in path:
                v = v[p]
            cmp("library: " + label, g[0], v)

    g = grab(r"Radarr tracks (\d+) movies \((\d+) downloaded · (\d+) wanted\) · Sonarr (\d+) series", html, "radarr")
    if g:
        cmp("radarr total", g[0], lib["radarr"]["total"])
        cmp("radarr have", g[1], lib["radarr"]["have"])
        cmp("radarr wanted", g[2], lib["radarr"]["monitored_missing"])
        cmp("sonarr series", g[3], lib["sonarr"]["series"])

    pipe = contract("pipeline")
    for label, key in (("Downloading", "downloading"), ("Seeding", "seeding"), ("Ratio", "ratio")):
        g = grab(r'<div class="n">([^<]+)</div><div class="l">%s</div>' % label, html, label)
        if g:
            want = pipe[key]
            # the legacy page prints the ratio with whatever precision python gave it; compare as floats
            if key == "ratio" and want is not None:
                cmp("pipeline ratio", float(g[0]), float(want))
            else:
                cmp("pipeline " + key, g[0], want)
    g = grab(r"queue: Radarr (\d+) / Sonarr (\d+)", html, "queues")
    if g:
        cmp("queue radarr", g[0], pipe["queue"]["radarr"])
        cmp("queue sonarr", g[1], pipe["queue"]["sonarr"])

    st = contract("storage")
    for dk in st["disks"]:
        g = grab(r'<div class="barlabel">%s: <span class="muted">(.*?) free</span>' % dk["letter"], html, dk["letter"])
        if g:
            cmp("disk %s: free" % dk["letter"], g[0].endswith(fmt_bytes(dk["free"])) and fmt_bytes(dk["free"]) or g[0],
                fmt_bytes(dk["free"]))

    sm = contract("smart")
    legacy_smart = len(re.findall(r"&mdash; \d+°C · <b>|— \d+°C · <b>", html))
    if legacy_smart:
        cmp("smart drive rows", legacy_smart, len(sm["drives"]))

    hnr = contract("hnr")
    cmp("H&R rows (<1.0 ratio)", len(re.findall(r'<div class="barpct">\d\.\d\d</div>', html)), hnr["count"])

    print("%-26s %-22s %-22s %s" % ("VALUE", "LEGACY PAGE", "V2 CONTRACT", ""))
    print("-" * 82)
    for label, a, b, verdict in rows:
        print("%-26s %-22s %-22s %s" % (label, str(a)[:22], str(b)[:22], verdict))
    print("\n%d compared | %d differ | exit %d" % (len(rows), bad, 1 if bad else 0))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
