#!/usr/bin/env python3
# hnr_horizon.py - I4 H&R Horizon: for every private torrent still below its 1.0 ratio goal, project WHEN it
# gets there from its actual upload velocity - per tracker and as a ranked risk feed. After the 2026-08 notices
# this is the difference between "seeding" as a hope and as a measured trajectory.
#
# READ-ONLY BY CONSTRUCTION (the H&R sentinel ethos): no verb, no force-start, no removal. The audit's
# check-hnr-exposure self-heal already handles silent torrents; this contract makes the RATIO trajectory
# visible. Runs every 6h as user-session task "HnR Horizon". HONEST EXIT: failure -> exit 1, write nothing.
import json, os, sys, time, urllib.request, urllib.parse, http.cookiejar, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
BASE = "http://127.0.0.1:8080"
PRIVATE = ("torrentleech", "tleechreload", "iptorrents", "torrentday", "td.jumbohostpro", "sync.td-peers",
           "async.empirehost", "ssl.empirehost", "cow.milkie", "immortalseed", "datascene", "stackoverflow.tech")
NEVER_BPS = 128.0            # below ~128 B/s average upload, "never at the current rate" is the honest label


def main():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    pw = open(os.path.join(WG, "qbit-webui.pass")).read().strip()
    op.open(urllib.request.Request(BASE + "/api/v2/auth/login",
            data=urllib.parse.urlencode({"username": "admin", "password": pw}).encode(),
            headers={"Referer": BASE}), timeout=20)
    tor = json.load(op.open(BASE + "/api/v2/torrents/info", timeout=120))
    if len(tor) < 2:
        print("FAILED: torrent list parsed to %d items - not credible" % len(tor))
        return 1

    rows = []
    for t in tor:
        tr = (t.get("tracker") or "").lower()
        if not any(p in tr for p in PRIVATE):
            continue
        dl = t.get("downloaded") or 0
        if dl <= 0:                      # nothing downloaded = no ratio obligation
            continue
        ratio = t.get("ratio") or 0
        if ratio >= 1.0:
            continue
        st = t.get("seeding_time") or 0
        up = t.get("uploaded") or 0
        remaining = dl * 1.0 - up
        vel = (up / st) if st > 600 else 0.0        # need >10min of seed history to call it a velocity
        days = (remaining / vel / 86400.0) if vel > NEVER_BPS else None
        host = urllib.parse.urlparse(t.get("tracker") or "").hostname or "?"
        rows.append({"name": (t.get("name") or "?")[:70], "tracker": host, "ratio": round(ratio, 3),
                     "remaining_gb": round(remaining / 1e9, 2),
                     "up_kbps": round(vel / 1024.0, 2),
                     "projected_days": (round(days, 1) if days is not None and days < 3650 else None),
                     "state": t.get("state", "?")})

    trackers = []
    grouped = collections.defaultdict(list)
    for r in rows:
        grouped[r["tracker"]].append(r)
    for host in sorted(grouped, key=lambda h: -len(grouped[h])):
        items = grouped[host]
        proj = [r["projected_days"] for r in items if r["projected_days"] is not None]
        proj.sort()
        trackers.append({
            "tracker": host,
            "below_goal": len(items),
            "remaining_gb": round(sum(r["remaining_gb"] for r in items), 1),
            "on_track_week": sum(1 for d in proj if d <= 7),
            "on_track_month": sum(1 for d in proj if 7 < d <= 30),
            "beyond_month": sum(1 for d in proj if d > 30),
            "never_at_current_rate": sum(1 for r in items if r["projected_days"] is None),
            "median_days": (proj[len(proj) // 2] if proj else None),
        })

    # ranked risk feed: 'never' first (worst), then longest projections
    rows.sort(key=lambda r: (r["projected_days"] is not None, -(r["projected_days"] or 0), -r["remaining_gb"]))

    # v1.1.0 (M3 feedback 2026-08-14): Michael only wants to KNOW about a below-goal torrent when it is not
    # seeding properly. "Not seeding properly" is judged from qBit state alone (honest - announce silence is
    # invisible here; check-hnr-exposure --fix owns that and the audit alerts on it):
    #   actively seeding = uploading / stalledUP (no peers right now is normal) / forcedUP
    #   still in flight  = any downloading/checking/queuedDL state (not a seeding failure yet)
    #   PROBLEM          = pausedUP / stoppedUP / queuedUP (not announcing) / error / missingFiles / unknown
    SEEDING_OK = {"uploading", "stalledUP", "forcedUP"}
    IN_FLIGHT = {"downloading", "stalledDL", "forcedDL", "metaDL", "queuedDL", "allocating",
                 "checkingDL", "checkingUP", "checkingResumeData", "moving"}
    problems = [r for r in rows if r["state"] not in SEEDING_OK and r["state"] not in IN_FLIGHT]

    data = {
        "totals": {"below_goal": len(rows), "remaining_gb": round(sum(r["remaining_gb"] for r in rows), 1),
                   "never_at_current_rate": sum(1 for r in rows if r["projected_days"] is None),
                   "problems": len(problems)},
        "trackers": trackers,
        "risk_feed": rows[:25],
        "problems": problems[:25],
    }
    path = bc.write_contract("hnr-horizon", data)
    print("hnr-horizon written: %s (%d below goal, %.0f GB remaining, %d never-at-current-rate, %d PROBLEMS)"
          % (path, len(rows), data["totals"]["remaining_gb"], data["totals"]["never_at_current_rate"],
             len(problems)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
