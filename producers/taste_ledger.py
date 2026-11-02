# taste_ledger.py - the taste loop's memory (wg\GAMEPLAN-TASTE-LOOP-2026-11.md s1-s2). Three jobs:
#   * append()  - the ONLY writer of wg\audit\taste-ledger.jsonl: one JSON event per line, append-only, fsync'd,
#                 under a lock file. Nothing is ever rewritten or deleted; an undo is a new event.
#   * ingest    - Plex userRating (sections 1 + 2) newer than the watermark become events (ratings made with the TV
#                 remote). The first run reconciles against the frozen Trakt base and STOPS on > 20 conflicts.
#   * compile   - base (wg\audit\trakt-ratings.json, NEVER modified) + ledger -> ratings-effective.json (exactly the
#                 trakt list shape, so every reader switches by path alone) + taste-signals.json (thumbs, bailed,
#                 household, hidden) + the taste-ledger contract.
# Latest explicit rating wins per (type, tmdb). Thumbs / notme / skip / bailed are never ratings.
# Kill switch wg\brain\TASTE-LEDGER-OFF: compile emits base-only (degraded) and the taste verbs refuse.
# Paths honour env overrides (TASTE_LEDGER_PATH, TASTE_STATE_PATH, TASTE_OUT_DIR, TASTE_BASE_PATH, TASTE_OFF_PATH,
# TASTE_NO_CONTRACT) so the unit tests never touch real data.
# Exit codes: 0 ok (degraded included - it says so), 1 hard failure, 2 stopped on conflicts (nothing written).
import argparse, collections, datetime, json, os, sys, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
AUDIT = os.path.join(WG, "audit")
PLEX = "http://127.0.0.1:32400"
CONFLICT_STOP = 20
BURST_STOP = 25             # more new Plex ratings than this in one non-first ingest = a bulk tool, not michael
KINDS = {"rating", "thumb", "notme", "skip", "bailed", "undo"}
SRCS = {"dash", "plex", "tv-remote", "derived"}
SURFACES = {"rate", "streaming", "missed", "tonight", "search", "ingest", None}


def P(name):
    """Resolved paths (re-read each call so tests can repoint the env between cases)."""
    out = os.environ.get("TASTE_OUT_DIR") or AUDIT
    return {
        "ledger": os.environ.get("TASTE_LEDGER_PATH") or os.path.join(AUDIT, "taste-ledger.jsonl"),
        "state": os.environ.get("TASTE_STATE_PATH") or os.path.join(AUDIT, "taste-ledger.state.json"),
        "base": os.environ.get("TASTE_BASE_PATH") or os.path.join(AUDIT, "trakt-ratings.json"),
        "off": os.environ.get("TASTE_OFF_PATH") or os.path.join(WG, "brain", "TASTE-LEDGER-OFF"),
        "effective": os.path.join(out, "ratings-effective.json"),
        "signals": os.path.join(out, "taste-signals.json"),
        "eval": os.path.join(out, "taste-eval.json"),
    }[name]


def is_off():
    return os.path.exists(P("off"))


def now_iso():
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def epoch(ts):
    """ISO string (with Z / offset / millis) -> unix seconds; unparseable -> 0."""
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        s = str(ts).replace("Z", "+00:00")
        if "." in s[19:]:
            head, rest = s[:19], s[19:]
            frac_end = 1
            while frac_end < len(rest) and rest[frac_end].isdigit():
                frac_end += 1
            s = head + rest[frac_end:]
        d = datetime.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.astimezone()
        return d.timestamp()
    except Exception:
        return 0.0


def key_of(typ, tmdb):
    return "%s:%d" % ("tv" if typ in ("tv", "show") else "movie", int(tmdb))


# ------------------------------------------------------------------------------------------------------- append
_THREAD_LOCK = threading.Lock()   # dashboard-server is threaded: serialize in-process before the cross-process lock


class _Lock(object):
    def __init__(self, path, wait=8.0, stale=30.0):
        self.path, self.wait, self.stale, self.fd = path, wait, stale, None

    def __enter__(self):
        t0 = time.time()
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("ascii"))
                return self
            except (FileExistsError, PermissionError):
                # PermissionError = Windows "delete pending": the previous holder just removed it (found by test V1.1)
                try:
                    if time.time() - os.path.getmtime(self.path) > self.stale:
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
                if time.time() - t0 > self.wait:
                    raise RuntimeError("taste ledger lock busy (%s)" % self.path)
                time.sleep(0.01)

    def __exit__(self, *a):
        try:
            os.close(self.fd)
        finally:
            try:
                os.remove(self.path)
            except OSError:
                pass


def validate(ev):
    k = ev.get("kind")
    if k not in KINDS:
        raise ValueError("kind must be one of %s" % sorted(KINDS))
    if ev.get("src") not in SRCS:
        raise ValueError("bad src")
    if ev.get("surface") not in SURFACES:
        raise ValueError("bad surface")
    if k == "undo":
        if not isinstance(ev.get("undoes"), str) or not ev["undoes"]:
            raise ValueError("undo needs undoes=<event id>")
        return
    if ev.get("type") not in ("movie", "tv"):
        raise ValueError("type must be movie or tv")
    t = ev.get("tmdb")
    if not (isinstance(t, int) and not isinstance(t, bool) and t > 0):
        raise ValueError("tmdb must be a positive int")
    rk = ev.get("rating_key")
    if rk is not None and not (isinstance(rk, str) and rk.isdigit()):
        raise ValueError("rating_key must be digits")
    v = ev.get("value")
    if k == "rating" and not (isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 10):
        raise ValueError("rating value must be an integer 1-10")
    if k == "thumb" and v not in ("up", "down", "clear"):
        raise ValueError("thumb value must be up/down/clear")


def append(ev):
    """Validate, stamp (id, ts) and durably append one event. Returns the stored event."""
    ev = dict(ev)
    ev.setdefault("src", "dash")
    ev.setdefault("surface", None)
    ev.setdefault("prev", None)
    ev.setdefault("undoes", None)
    ev.setdefault("value", None)
    ev.setdefault("rating_key", None)
    ev.setdefault("title", "")
    ev.setdefault("year", None)
    if ev.get("kind") == "undo":
        ev.setdefault("type", None)
        ev.setdefault("tmdb", None)
    validate(ev)
    ev["id"] = "%d-%s" % (time.time_ns(), os.urandom(3).hex())
    ev["ts"] = ev.get("ts") or now_iso()
    path = P("ledger")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(ev, ensure_ascii=True, separators=(",", ":")) + "\n"
    with _THREAD_LOCK, _Lock(path + ".lock"):
        with open(path, "a", encoding="ascii", newline="\n") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
    return ev


def read_events():
    """(events in file order, bad_line_count). A truncated / corrupt line is skipped and counted, never fatal."""
    path = P("ledger")
    out, bad = [], 0
    if not os.path.exists(path):
        return out, 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                if not isinstance(ev, dict) or "id" not in ev or ev.get("kind") not in KINDS:
                    raise ValueError
                out.append(ev)
            except Exception:
                bad += 1
    return out, bad


def voided_ids(events):
    """Ids cancelled by a (non-cancelled) undo. undo-of-undo reinstates the original."""
    undo_of = {}
    for e in events:
        if e.get("kind") == "undo" and e.get("undoes"):
            undo_of.setdefault(e["undoes"], []).append(e["id"])
    memo = {}

    def voided(eid, depth=0):
        if eid in memo:
            return memo[eid]
        if depth > 50:
            return False
        memo[eid] = any(not voided(u, depth + 1) for u in undo_of.get(eid, []))
        return memo[eid]

    return {e["id"] for e in events if voided(e["id"])}


# -------------------------------------------------------------------------------------------------------- fold
def load_base():
    rows = bc.read_json(P("base"))
    if not isinstance(rows, list):
        raise RuntimeError("ratings base %s missing or not a list" % P("base"))
    return rows


def fold(base_rows, events):
    """Pure: base + events -> (effective rows list, signals dict, stats dict)."""
    void = voided_ids(events)
    live = [e for e in events if e["id"] not in void and e.get("kind") != "undo"]
    best = {}       # key -> (epoch, row)
    for r in base_rows:
        m = r.get("movie") or r.get("show") or {}
        tid = (m.get("ids") or {}).get("tmdb")
        if not tid or not isinstance(r.get("rating"), (int, float)):
            continue
        k = key_of(r.get("type") or "movie", tid)
        row = dict(r)
        row.setdefault("src", "trakt")
        best[k] = (epoch(r.get("rated_at")), row)
    base_keys = set(best)
    ledger_rated = 0
    thumbs, bailed, notme, skip = {}, {}, {}, {}
    for e in live:
        k = key_of(e["type"], e["tmdb"])
        t = epoch(e.get("ts"))
        kind = e["kind"]
        if kind == "rating":
            ent = {"title": e.get("title") or "", "year": e.get("year"), "ids": {"tmdb": int(e["tmdb"])}}
            if e.get("rating_key"):
                ent["ids"]["plex"] = e["rating_key"]
            if e["type"] == "tv":
                row = {"rated_at": e["ts"], "rating": int(e["value"]), "type": "show", "show": ent, "src": e["src"]}
            else:
                row = {"rated_at": e["ts"], "rating": int(e["value"]), "type": "movie", "movie": ent, "src": e["src"]}
            if k not in best or t >= best[k][0]:
                best[k] = (t, row)
                ledger_rated += 1
        elif kind == "thumb":
            if k not in thumbs or t >= thumbs[k][0]:
                thumbs[k] = (t, e["value"], e)
        elif kind == "bailed":
            bailed[k] = (t, e)
        elif kind == "notme":
            notme[k] = (t, e)
        elif kind == "skip":
            skip[k] = (t, e)
    eff = [row for _, row in sorted(best.values(), key=lambda x: -x[0])]

    def brief(e):
        return {"key": key_of(e["type"], e["tmdb"]), "type": e["type"], "tmdb": int(e["tmdb"]),
                "rating_key": e.get("rating_key"), "title": e.get("title") or "", "ts": e.get("ts")}

    ups = [brief(v[2]) for v in thumbs.values() if v[1] == "up"]
    downs = [brief(v[2]) for v in thumbs.values() if v[1] == "down"]
    signals = {
        "thumbs_up": ups,
        "thumbs_down": downs,
        "bailed": [brief(v[1]) for v in bailed.values() if key_of(v[1]["type"], v[1]["tmdb"]) not in best],
        "household": [brief(v[1]) for v in notme.values()],
        "skipped": [dict(brief(v[1]), until=v[0] + 30 * 86400) for v in skip.values()],
        "hidden": [d["key"] for d in downs],
    }
    by_src = collections.Counter(row.get("src", "trakt") for _, row in best.values())
    stats = {
        "base": len(base_keys), "effective": len(best),
        "effective_movie": sum(1 for k in best if k.startswith("movie:")),
        "effective_tv": sum(1 for k in best if k.startswith("tv:")),
        "by_src": dict(by_src), "events": len(events), "voided": len(void),
        "kinds": dict(collections.Counter(e["kind"] for e in events)),
        "thumbs_up": len(ups), "thumbs_down": len(downs), "bailed": len(signals["bailed"]),
        "notme": len(signals["household"]), "skip": len(signals["skipped"]),
        "ledger_rated": ledger_rated,
    }
    return eff, signals, stats


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------------------ ingest
def plex_token():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Plex, Inc.\Plex Media Server") as k:
        return winreg.QueryValueEx(k, "PlexOnlineToken")[0]


def plex_rated(token):
    """[(type, tmdb, rating_key, title, year, userRating, lastRatedAt)] for every rated movie/show."""
    out = []
    for sec, typ, ptype in (("1", "movie", "1"), ("2", "tv", "2")):
        url = "%s/library/sections/%s/all?type=%s&includeGuids=1&userRating%%3E%%3E=0&X-Plex-Token=%s" % (PLEX, sec, ptype, token)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        md = json.load(urllib.request.urlopen(req, timeout=180))["MediaContainer"].get("Metadata", [])
        for m in md:
            tid = None
            for g in m.get("Guid") or []:
                if g.get("id", "").startswith("tmdb://"):
                    try:
                        tid = int(g["id"][7:])
                    except ValueError:
                        pass
            if tid and m.get("userRating") is not None:
                out.append((typ, tid, str(m["ratingKey"]), m.get("title") or "", m.get("year"),
                            float(m["userRating"]), int(m.get("lastRatedAt") or 0)))
    return out


def ingest(rated=None, log=print, accept_burst=False):
    """Plex ratings newer than the watermark -> events. Returns (new_events, report). Raises SystemExit(2) on the
    first-run conflict stop. `rated` may be injected (tests)."""
    state = bc.read_json(P("state")) or {}
    first = "watermark" not in state
    if rated is None:
        rated = plex_rated(plex_token())
    events, _ = read_events()
    eff, _, _ = fold(load_base(), events)
    cur = {}
    for row in eff:
        m = row.get("movie") or row.get("show") or {}
        cur[key_of(row.get("type") or "movie", m["ids"]["tmdb"])] = row["rating"]
    wm = int(state.get("watermark", 0))
    conflicts, new, same = [], [], 0
    for typ, tid, rk, title, year, ur, lra in rated:
        if not first and lra <= wm:
            continue
        v = int(round(ur))
        if v < 1 or v > 10:
            continue
        k = key_of(typ, tid)
        if k in cur and cur[k] == v:
            same += 1
            continue
        if first and k in cur:
            conflicts.append({"title": title, "plex": v, "effective": cur[k]})
        new.append({"kind": "rating", "src": "plex" if first else "tv-remote", "surface": "ingest", "type": typ,
                    "tmdb": tid, "rating_key": rk, "title": title, "year": year, "value": v,
                    "ts": datetime.datetime.fromtimestamp(lra).astimezone().isoformat() if lra else None})
    report = {"first_run": first, "seen": len(rated), "same": same, "new": len(new), "conflicts": len(conflicts)}
    if not first and len(new) > BURST_STOP and not accept_burst:
        # No human rates 25+ titles with a remote between two 2-hour runs: this is a tool rewriting Plex ratings
        # (e.g. Kometa's mass_user_rating_update, which would overwrite his stars). Import nothing, say so loudly.
        log("STOP: %d new Plex ratings since the last ingest (> %d) - looks like a bulk rewrite, not michael. Nothing "
            "imported; watermark NOT advanced (if it really was you: taste_ledger.py --accept-burst). Sample: %s"
            % (len(new), BURST_STOP, [e["title"] for e in new[:5]]))
        raise SystemExit(2)
    if first and len(conflicts) > CONFLICT_STOP:
        log("STOP: %d Plex/base rating conflicts on the first ingest (> %d) - nothing written. Sample: %s"
            % (len(conflicts), CONFLICT_STOP, conflicts[:5]))
        raise SystemExit(2)
    for ev in new:
        append(ev)
    state["watermark"] = max([wm] + [x[6] for x in rated])
    state["last_ingest"] = now_iso()
    state["last_report"] = report
    write_json(P("state"), state)
    log("ingest: %s" % report)
    return new, report


# ----------------------------------------------------------------------------------------------------- compile
def compile_all(log=print, write_contract=True):
    """Fold and write ratings-effective + taste-signals (+ the contract). Returns the contract data dict."""
    base = load_base()
    degraded, reason = False, ""
    events, bad = [], 0
    if is_off():
        degraded, reason = True, "TASTE-LEDGER-OFF flag present - base ratings only"
    else:
        try:
            events, bad = read_events()
        except Exception as ex:
            degraded, reason = True, "ledger unreadable (%s) - base ratings only" % type(ex).__name__
    eff, signals, stats = fold(base, events)
    write_json(P("effective"), eff)
    write_json(P("signals"), signals)
    void = voided_ids(events)
    recent = []
    for e in reversed(events):
        if e.get("kind") == "undo" or e.get("surface") == "ingest":
            continue
        recent.append({"kind": e["kind"], "title": (e.get("title") or "")[:120], "type": e.get("type"),
                       "value": e.get("value") if e.get("value") is None or isinstance(e.get("value"), (int, str)) else None,
                       "ts": e.get("ts"), "undone": e["id"] in void})
        if len(recent) == 15:
            break
    base_loved = {key_of(r.get("type") or "movie", (r.get("movie") or {}).get("ids", {}).get("tmdb"))
                  for r in base if (r.get("movie") or {}).get("ids", {}).get("tmdb") and (r.get("rating") or 0) >= 8}
    eff_loved = {key_of(r.get("type") or "movie", (r.get("movie") or r.get("show"))["ids"]["tmdb"])
                 for r in eff if (r.get("rating") or 0) >= 8}
    ev = bc.read_json(P("eval")) or {}
    thumbs = {d["key"]: "up" for d in signals["thumbs_up"]}
    thumbs.update({d["key"]: "down" for d in signals["thumbs_down"]})
    data = {
        "degraded": degraded, "reason": reason, "bad_lines": bad,
        "counts": {
            "base": stats["base"], "effective": stats["effective"], "effective_movie": stats["effective_movie"],
            "effective_tv": stats["effective_tv"], "by_src": stats["by_src"], "events": stats["events"],
            "thumbs_up": stats["thumbs_up"], "thumbs_down": stats["thumbs_down"], "bailed": stats["bailed"],
            "notme": stats["notme"], "skip": stats["skip"],
        },
        "thumbs": thumbs,
        "recent": recent,
        "drift": {"loved_added": len(eff_loved - base_loved), "loved_removed": len(base_loved - eff_loved)},
        "eval": {"baseline": ev.get("baseline"), "latest": (ev.get("history") or [None])[-1],
                 "history": (ev.get("history") or [])[-26:], "live_mae": ev.get("live_mae")},
    }
    if write_contract and not os.environ.get("TASTE_NO_CONTRACT"):
        bc.write_contract("taste-ledger", data)
    log("compile: %d effective ratings (%d movie / %d tv; base %d), %d events, %d bad lines%s"
        % (stats["effective"], stats["effective_movie"], stats["effective_tv"], stats["base"], stats["events"], bad,
           (" - DEGRADED: " + reason) if degraded else ""))
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest-only", action="store_true")
    ap.add_argument("--compile-only", action="store_true")
    ap.add_argument("--accept-burst", action="store_true", help="import a > %d-rating Plex burst (it really was him)" % BURST_STOP)
    a = ap.parse_args()
    try:
        if not a.compile_only and not is_off():
            try:
                ingest(accept_burst=a.accept_burst)
            except SystemExit:
                raise
            except Exception as ex:
                print("ingest skipped: Plex unreachable or unreadable (%s: %s)" % (type(ex).__name__, ex))
        if not a.ingest_only:
            compile_all()
    except SystemExit as ex:
        return int(ex.code or 0)
    except Exception as ex:
        print("FATAL: %s: %s" % (type(ex).__name__, ex))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
