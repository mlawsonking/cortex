#!/usr/bin/env python3
# anomaly_feed.py - I8 Anomaly Feed: the cross-system correlation the daily audit structurally cannot see.
#
# The audit asks "is each system healthy?" - Radarr up, qBit bound, disks fine. It never asks "are these
# INDEPENDENT events all pointing at the same culprit?" This producer does exactly that and nothing else:
#   1. GRAB/IMPORT FAILURES BY INDEXER (48h, Radarr + Sonarr history POOLED - indexers are shared through
#      Prowlarr, so one failing indexer shows up in both apps and neither app alone can see the pattern).
#      Anomaly = >= 4 failures AND a share of all failures >= 3x that indexer's share of all attributed events.
#      Attribution: history data.indexer when present; otherwise joined via downloadId to the grab that carries
#      it (Radarr's downloadFailed carries indexer directly, Sonarr's mostly does not - the join is what makes
#      Sonarr countable at all). Failures we still cannot attribute are REPORTED, never silently dropped.
#   2. STALL CLUSTERING BY TRACKER: incomplete downloads sitting in stalledDL / error / missingFiles, grouped by
#      tracker host. One dead grab is noise; five on one tracker is a tracker problem.
#   3. ERROR-STATE TORRENTS: anything in error / missingFiles at all, grouped by tracker (data-integrity class).
#
# ACTIONLESS BY DESIGN (v1): this contract reports, it does not fix. No verb hangs off it and no card may add
# one without its own review. READ-ONLY against every API - the only non-GET is the qBit auth login, exactly as
# hnr_horizon.py does it.
#
# HONEST FAILURE: a source that will not answer is recorded as checked_sources[].ok = false and the rest is
# still computed from what DID answer. If EVERY source fails there is nothing honest to say - exit 1, write
# nothing, leave the previous contract in place to go stale on its own SLO.
#
# Runs every 6h as user-session task "Anomaly Feed". Pure stdlib, pure ASCII source.
import json, os, sys, collections, datetime, urllib.request, urllib.parse, http.cookiejar

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
QBIT = "http://127.0.0.1:8080"                 # NEVER "localhost" - VPN DNS sends it to ::1 and qBit 403s it
ARRS = (("radarr", "http://127.0.0.1:7878", "radarr.key"),
        ("sonarr", "http://127.0.0.1:8989", "sonarr.key"))
WINDOW_H = 48
FAIL_EVENTS = ("grabFailed", "downloadFailed", "importFailed")
BAD_STATES = ("stalledDL", "error", "missingFiles")
ERROR_STATES = ("error", "missingFiles")
MIN_FAILS = 4            # class 1: fewer than this is not a cluster, it is luck
SHARE_MULT = 3.0         # class 1: failure share must be >= 3x the indexer's share of all attributed events
MIN_STALLS = 5           # class 2
MIN_ALL_ERRORED = 3      # class 2: a smaller group counts if EVERY member is errored/missingFiles
MAX_ANOMALIES = 20
MAX_ERROR_ROWS = 10


def parse_utc(s):
    """*arr history dates are UTC with a trailing Z, which 3.10's fromisoformat will not take."""
    if not s:
        return None
    t = str(s).strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        d = datetime.datetime.fromisoformat(t)
    except Exception:
        try:
            d = datetime.datetime.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d


def ascii_only(s):
    return str(s).encode("ascii", "replace").decode("ascii")


def short(name, n=48):
    name = ascii_only(name).strip()
    return name if len(name) <= n else name[:n - 1] + "~"


def fetch_history(base, keyfile):
    key = open(os.path.join(WG, keyfile)).read().strip()
    url = base + "/api/v3/history?pageSize=500&sortKey=date&sortDirection=descending"
    req = urllib.request.Request(url, headers={"X-Api-Key": key})
    body = json.load(urllib.request.urlopen(req, timeout=60))
    recs = body.get("records")
    if not isinstance(recs, list):
        raise ValueError("history response had no records array")
    return recs


def fetch_torrents():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    pw = open(os.path.join(WG, "qbit-webui.pass")).read().strip()
    op.open(urllib.request.Request(QBIT + "/api/v2/auth/login",
            data=urllib.parse.urlencode({"username": "admin", "password": pw}).encode(),
            headers={"Referer": QBIT}), timeout=20)
    tor = json.load(op.open(QBIT + "/api/v2/torrents/info", timeout=120))
    if not isinstance(tor, list) or len(tor) < 2:
        raise ValueError("torrent list parsed to %s items - not credible" % (len(tor) if isinstance(tor, list) else "?"))
    return tor


def host_of(tracker):
    try:
        h = urllib.parse.urlparse(tracker or "").hostname
    except Exception:
        h = None
    return h or "(no tracker)"


def indexer_failures(sources, cutoff):
    """Class 1. Returns (anomalies, per-app detail strings)."""
    fails = collections.Counter()          # indexer -> failures in window
    events = collections.Counter()         # indexer -> attributed events in window
    by_app = collections.defaultdict(collections.Counter)   # indexer -> {app: failures}
    details = {}

    for app, recs in sources.items():
        # downloadId -> indexer, learned from every record in the feed that names one (grabs do).
        dmap = {}
        for r in recs:
            ind = (r.get("data") or {}).get("indexer")
            did = r.get("downloadId")
            if ind and did:
                dmap.setdefault(did, ind)

        win = [r for r in recs if (parse_utc(r.get("date")) or datetime.datetime.min.replace(
            tzinfo=datetime.timezone.utc)) >= cutoff]
        n_fail = n_unattr = 0
        seen_types = collections.Counter()
        for r in win:
            et = r.get("eventType")
            seen_types[et] += 1
            ind = (r.get("data") or {}).get("indexer") or dmap.get(r.get("downloadId"))
            is_fail = et in FAIL_EVENTS
            if is_fail:
                n_fail += 1
            if ind:
                events[ind] += 1
                if is_fail:
                    fails[ind] += 1
                    by_app[ind][app] += 1
            elif is_fail:
                n_unattr += 1
        oldest = parse_utc(recs[-1].get("date")) if recs else None
        details[app] = ("%d history records back to %s; %d in the %dh window (%s); %d failure event(s), "
                        "%d not attributable to an indexer"
                        % (len(recs), oldest.strftime("%Y-%m-%d") if oldest else "?", len(win), WINDOW_H,
                           ", ".join("%s %d" % (k, v) for k, v in seen_types.most_common()) or "no events",
                           n_fail, n_unattr))

    total_f = sum(fails.values())
    total_e = sum(events.values())
    out = []
    if total_f and total_e:
        for ind, f in fails.most_common():
            if f < MIN_FAILS:
                continue
            share_f = f / float(total_f)
            share_e = events[ind] / float(total_e)
            if share_e <= 0 or share_f < SHARE_MULT * share_e:
                continue
            mix = ", ".join("%s %d" % (a, c) for a, c in sorted(by_app[ind].items()))
            out.append({
                "type": "indexer-failures",
                "subject": ascii_only(ind),
                "severity": "warn" if f >= 2 * MIN_FAILS else "info",
                "count": f,
                "evidence": ("%d of %d failures in %dh (%.0f%%) but only %.0f%% of the %d attributed events "
                             "- %.1fx over-represented; %s"
                             % (f, total_f, WINDOW_H, share_f * 100, share_e * 100, total_e,
                                share_f / share_e, mix)),
            })
    return out, details


def torrent_anomalies(tor):
    """Classes 2 and 3. Returns (anomalies, detail string)."""
    bad = [t for t in tor if t.get("state") in BAD_STATES]
    # "download" = not yet complete. A stalled/errored SEED is an H&R matter (hnr-horizon owns it), not a
    # pipeline stall, so class 2 deliberately only looks at incomplete transfers.
    dl_bad = [t for t in bad if (t.get("progress") or 0) < 1.0]

    out = []
    grouped = collections.defaultdict(list)
    for t in dl_bad:
        grouped[host_of(t.get("tracker"))].append(t)
    for host in sorted(grouped, key=lambda h: -len(grouped[h])):
        items = grouped[host]
        n = len(items)
        errored = [t for t in items if t.get("state") in ERROR_STATES]
        all_errored = len(errored) == n and n >= MIN_ALL_ERRORED
        if not (n >= MIN_STALLS or all_errored):
            continue
        mix = collections.Counter(t.get("state") for t in items)
        names = "; ".join(short(t.get("name") or "?") for t in items[:3])
        out.append({
            "type": "stall-cluster",
            "subject": ascii_only(host),
            "severity": "warn" if (all_errored or n >= 8) else "info",
            "count": n,
            "evidence": ("%d incomplete download(s) stuck on this tracker (%s)%s; e.g. %s"
                         % (n, ", ".join("%s %d" % (k, v) for k, v in mix.most_common()),
                            " - ALL of them errored/missing files" if all_errored else "", names)),
        })

    err_groups = collections.defaultdict(list)
    for t in tor:
        if t.get("state") in ERROR_STATES:
            err_groups[host_of(t.get("tracker"))].append(t)
    rows = 0
    for host in sorted(err_groups, key=lambda h: -len(err_groups[h])):
        if rows >= MAX_ERROR_ROWS:
            break
        items = err_groups[host]
        mix = collections.Counter(t.get("state") for t in items)
        names = "; ".join(short(t.get("name") or "?") for t in items[:3])
        out.append({
            "type": "error-state",
            "subject": ascii_only(host),
            "severity": "warn",
            "count": len(items),
            "evidence": ("%d torrent(s) in an error state (%s) - qBit cannot read/write their files; %s"
                         % (len(items), ", ".join("%s %d" % (k, v) for k, v in mix.most_common()), names)),
        })
        rows += 1

    detail = ("%d torrents; %d in %s; %d of those are incomplete downloads"
              % (len(tor), len(bad), "/".join(BAD_STATES), len(dl_bad)))
    return out, detail


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=WINDOW_H)

    checked = []
    hist = {}
    for app, base, keyfile in ARRS:
        try:
            hist[app] = fetch_history(base, keyfile)
        except Exception as e:
            checked.append({"name": app + "-history", "ok": False,
                            "detail": "unreachable: %s: %s" % (type(e).__name__, ascii_only(e)[:160])})
    try:
        tor = fetch_torrents()
    except Exception as e:
        tor = None
        checked.append({"name": "qbittorrent", "ok": False,
                        "detail": "unreachable: %s: %s" % (type(e).__name__, ascii_only(e)[:160])})

    if not hist and tor is None:
        print("FAILED: every source unreachable (radarr, sonarr, qbittorrent) - writing nothing")
        for c in checked:
            print("  %s: %s" % (c["name"], c["detail"]))
        return 1

    anomalies = []
    if hist:
        rows, details = indexer_failures(hist, cutoff)
        anomalies += rows
        for app, _b, _k in ARRS:
            if app in details:
                checked.append({"name": app + "-history", "ok": True, "detail": details[app]})
    if tor is not None:
        rows, detail = torrent_anomalies(tor)
        anomalies += rows
        checked.append({"name": "qbittorrent", "ok": True, "detail": detail})

    checked.sort(key=lambda c: c["name"])
    order = {"warn": 0, "info": 1}
    anomalies.sort(key=lambda a: (order.get(a["severity"], 9), -a["count"], a["type"], a["subject"]))
    anomalies = anomalies[:MAX_ANOMALIES]

    all_ok = all(c["ok"] for c in checked)
    data = {
        "checked_sources": checked,
        "anomalies": anomalies,
        "all_clear": bool(all_ok and not anomalies),
    }
    path = bc.write_contract("anomaly-feed", data)

    print("anomaly-feed written: %s" % path)
    print("sources: %s" % ", ".join("%s=%s" % (c["name"], "ok" if c["ok"] else "FAIL") for c in checked))
    for c in checked:
        print("  [%s] %s: %s" % ("ok" if c["ok"] else "FAIL", c["name"], ascii_only(c["detail"])))
    if data["all_clear"]:
        print("ALL CLEAR: no cross-system clustering across %d source(s)" % len(checked))
    elif not anomalies:
        print("no anomalies found, but a source failed - all_clear is FALSE (cannot claim clear on partial data)")
    else:
        print("%d anomal%s:" % (len(anomalies), "y" if len(anomalies) == 1 else "ies"))
        for a in anomalies:
            print("  [%s] %s / %s (n=%d): %s" % (a["severity"], a["type"], a["subject"], a["count"],
                                                 ascii_only(a["evidence"])))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
