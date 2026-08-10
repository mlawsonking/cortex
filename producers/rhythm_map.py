#!/usr/bin/env python3
# rhythm_map.py - I1 Rhythm Map: WHEN does this household actually watch? (weekday x hour heat, per user)
# Reads Tautulli's play history (the record of what was really watched, not what was downloaded) and emits the
# 'rhythm' contract. Consumed by the I1 card now and the schedule-aware Tonight's Pick later (auto Date-Night
# pick in the Friday-evening slot once the pick scheduler is wired in a later engine pass).
#
# Standalone producer, scheduled daily via the user-session task "Rhythm Map" (pythonw.exe so no console flash,
# exit code still propagates to the task-health watchdog). HONEST EXIT: any fetch/parse failure exits 1 and
# writes NOTHING - the previous contract ages into a STALE badge, which is true. An empty history is a real
# state and IS written (with its sample size, so the card can say how thin the evidence is).
import json, os, sys, time, urllib.request, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
WINDOW_DAYS = 90
TOP_USERS = 4


def main():
    key = open(os.path.join(WG, "tautulli.key")).read().strip()
    url = "http://127.0.0.1:8181/api/v2?apikey=%s&cmd=get_history&length=5000" % key
    rows = json.load(urllib.request.urlopen(url, timeout=60))["response"]["data"]["data"]

    cutoff = time.time() - WINDOW_DAYS * 86400
    plays = []
    for r in rows:
        st = r.get("started")
        if not st or st < cutoff:
            continue
        if r.get("media_type") not in ("movie", "episode"):
            continue
        lt = time.localtime(st)
        plays.append({"user": r.get("user") or "?", "weekday": lt.tm_wday, "hour": lt.tm_hour,
                      "media": r.get("media_type")})

    def matrix(items):
        m = [[0] * 24 for _ in range(7)]
        for p in items:
            m[p["weekday"]][p["hour"]] += 1
        return m

    by_user = collections.Counter(p["user"] for p in plays)
    users = []
    for u, n in by_user.most_common(TOP_USERS):
        users.append({"user": u, "plays": n, "matrix": matrix([p for p in plays if p["user"] == u])})

    allm = matrix(plays)
    slots = [{"weekday": d, "hour": h, "plays": allm[d][h]}
             for d in range(7) for h in range(24) if allm[d][h] > 0]
    slots.sort(key=lambda s: -s["plays"])

    data = {
        "window_days": WINDOW_DAYS,
        "total_plays": len(plays),
        "movies": sum(1 for p in plays if p["media"] == "movie"),
        "episodes": sum(1 for p in plays if p["media"] == "episode"),
        "all": allm,
        "users": users,
        "top_slots": slots[:5],
    }
    path = bc.write_contract("rhythm", data)
    print("rhythm contract written: %s (%d plays / %dd, %d users)"
          % (path, len(plays), WINDOW_DAYS, len(users)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
