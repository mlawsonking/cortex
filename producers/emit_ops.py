# emit_ops.py - turn gen-dashboard.py's already-gathered dict into versioned ops contracts.
# P0 of the Cortex brain app. Pure stdlib, pure ASCII source (unicode glyphs are written as escapes).
#
# WHY THIS SHAPE: most ops data (services, disks, qBit, Plex, calendar, activity) is gathered INLINE by
# gen-dashboard.py, not by standalone producers. Reusing the dict it already built means zero duplicated
# gathering logic, zero extra API load on the *arr stack, no new scheduled task and no new listener.
#
# CONTRACT WITH THE CALLER: emit(d) must never raise into the render path. gen-dashboard calls it inside a
# try/except AFTER the atomic page writes, and every contract here is written in its own try/except so one bad
# contract cannot take the other nineteen (or the page) down with it. Failures are recorded honestly in
# data\_emit-status.json instead of being swallowed silently.
import os, sys, time, json, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc
import wrap_files

WG = r"C:\Users\bobdo\wg"
# Backdrop cache INSIDE the served dashboard dir, so the app loads art same-origin. .jpg is already on
# dashboard-server.py's serve allow-list, so this needs no new route. Bounded by the recs pool size (~30 files).
ART_DIR = os.path.join(WG, "dashboard", "art")

# gen-dashboard writes these glyphs into its tuples; map them back to semantic kinds so the UI owns its own icons.
CAL_KIND = {"\U0001F4FA": "episode", "\U0001F3AC": "movie"}
EV_KIND = {"\u2b07": "grabbed", "\U0001F4E5": "imported", "\u2717": "failed", "\u25b6": "watched"}


def _s(v):
    return "" if v is None else str(v)


def _clamp(v, lo, hi):
    try:
        return max(lo, min(hi, v))
    except Exception:
        return lo


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _emit_services(d):
    svcs = [{"name": _s(n), "up": bool(u)} for n, u in (d.get("services") or [])]
    vpn = d.get("vpn")
    bc.write_contract("services", {
        "up_count": sum(1 for s in svcs if s["up"]),
        "total": len(svcs),
        "vpn_bound": None if vpn is None else bool(vpn),
        "services": svcs,
    })


def _emit_storage(d):
    disks = []
    for k in (d.get("disks") or []):
        disks.append({
            "letter": _s(k.get("letter"))[:1] or "?",
            "label": _s(k.get("label")),
            "total": _num(k.get("total")) or 0,
            "used": _num(k.get("used")) or 0,
            "free": _num(k.get("free")) or 0,
            "removable": bool(k.get("removable")),
        })
    pa = d.get("parity")
    parity = None
    if pa:
        st = pa.get("state")
        parity = {
            "state": st if st in ("synced", "syncing", "stale") else "stale",
            "pct": pa.get("pct") if isinstance(pa.get("pct"), int) else None,
            "pfree": _num(pa.get("pfree")),
        }
    bc.write_contract("storage", {"disks": disks, "forecast": _s(d.get("forecast")), "parity": parity})


def _emit_pipeline(d):
    q = d.get("qbit") or {}
    active = []
    for row in (q.get("active") or []):
        try:
            nm, pc, sp = row
        except Exception:
            continue
        active.append({"name": _s(nm), "pct": _clamp(float(pc or 0), 0.0, 100.0), "mbps": max(0.0, float(sp or 0))})
    bc.write_contract("pipeline", {
        "dl_bps": _num(q.get("dl")),
        "ul_bps": _num(q.get("ul")),
        "ratio": _num(q.get("ratio")),
        "downloading": q.get("downloading") if isinstance(q.get("downloading"), int) else None,
        "seeding": q.get("seeding") if isinstance(q.get("seeding"), int) else None,
        "torrents": q.get("total") if isinstance(q.get("total"), int) else None,
        "active": active,
        "queue": {
            "radarr": d.get("rq") if isinstance(d.get("rq"), int) else None,
            "sonarr": d.get("sq") if isinstance(d.get("sq"), int) else None,
            "sonarr_missing": d.get("smiss") if isinstance(d.get("smiss"), int) else None,
        },
    })


def _emit_hnr(d):
    rows = []
    for row in ((d.get("qbit") or {}).get("hnr") or []):
        try:
            nm, rt = row
        except Exception:
            continue
        rows.append({"name": _s(nm), "ratio": max(0.0, float(rt or 0))})
    bc.write_contract("hnr", {"count": len(rows), "torrents": rows})


def _emit_library_stats(d):
    p = d.get("plex") or {}
    r = d.get("radarr") or {}
    s = d.get("sonarr") or {}

    def i(v):
        return v if isinstance(v, int) and not isinstance(v, bool) else None

    bc.write_contract("library-stats", {
        "plex": {"movies": i(p.get("movies")), "tv": i(p.get("tv"))},
        "radarr": {"total": i(r.get("total")), "have": i(r.get("have")),
                   "monitored_missing": i(r.get("mon_missing")), "size_bytes": _num(r.get("size"))},
        "sonarr": {"series": i(s.get("series")), "monitored": i(s.get("mon")),
                   "missing_episodes": i(d.get("smiss"))},
        "rated": i(d.get("rated")),
    })


def _emit_plex_now(d):
    p = d.get("plex") or {}
    sessions = []
    for row in (p.get("now") or []):
        try:
            title, user, thumb, off, dur = row
        except Exception:
            continue
        off = float(off or 0)
        dur = float(dur or 1)
        sessions.append({"title": _s(title), "user": _s(user), "thumb": _s(thumb),
                         "offset_ms": max(0.0, off), "duration_ms": max(0.0, dur),
                         "pct": int(_clamp(100.0 * off / max(dur, 1.0), 0.0, 100.0))})
    recent = []
    for row in (p.get("recent") or []):
        try:
            title, year, thumb = row
        except Exception:
            continue
        recent.append({"title": _s(title), "year": year if isinstance(year, int) else _s(year), "thumb": _s(thumb)})
    bc.write_contract("plex-now", {"ok": bool(d.get("plex_ok")), "sessions": sessions, "recent": recent})


def _emit_calendar(d):
    items = []
    for row in (d.get("calendar") or []):
        try:
            dt, glyph, title, sub = row
        except Exception:
            continue
        kind = CAL_KIND.get(glyph)
        if kind is None:
            kind = "movie" if _s(sub) == "release" else "other"
        dt = _s(dt)[:10]
        if len(dt) != 10:
            continue                                  # a row we cannot date honestly is dropped, not faked
        items.append({"date": dt, "kind": kind, "title": _s(title), "detail": _s(sub)})
    bc.write_contract("calendar", {"days": 14, "items": items})


def _emit_activity(d):
    items = []
    for row in (d.get("events") or []):
        try:
            ts, glyph, title, verb = row
        except Exception:
            continue
        items.append({"ts": max(0.0, float(ts or 0)), "kind": EV_KIND.get(glyph, "other"),
                      "title": _s(title), "detail": _s(verb)})
    bc.write_contract("activity", {"items": items})


def _emit_health(d):
    probes = [{"name": _s(p.get("name")), "ok": bool(p.get("ok")), "detail": _s(p.get("detail"))}
              for p in (d.get("deephealth") or []) if isinstance(p, dict)]
    inc = []
    for row in (d.get("incidents7d") or []):
        try:
            svc, n = row
        except Exception:
            continue
        inc.append({"service": _s(svc), "downs": int(n or 0)})
    bc.write_contract("health", {"probes": probes, "incidents_7d": inc})


def _emit_security(d):
    probes = [{"name": _s(p.get("name")), "ok": bool(p.get("ok")), "detail": _s(p.get("detail"))}
              for p in (d.get("security") or []) if isinstance(p, dict)]
    # generated_at = the 15-minute cache file's mtime: copying a cached probe does not re-run it.
    bc.write_contract("security", {"probes": probes},
                      generated_at_ts=bc.mtime(os.path.join(WG, "dashboard", "security.json")))


def _emit_smart(d):
    drives = []
    for s in (d.get("smart") or []):
        if not isinstance(s, dict):
            continue
        v = _s(s.get("verdict")).upper() or "PASS"
        drives.append({"dev": _s(s.get("dev")), "model": _s(s.get("model")), "serial": _s(s.get("serial")),
                       "temp": s.get("temp") if isinstance(s.get("temp"), (int, float)) else None,
                       "verdict": v if v in ("PASS", "WARN", "RMA", "FAIL") else "WARN",
                       "realloc": s.get("realloc") if isinstance(s.get("realloc"), (int, float)) else 0,
                       "pending": s.get("pending") if isinstance(s.get("pending"), (int, float)) else 0})
    bc.write_contract("smart", {"drives": drives},
                      generated_at_ts=bc.mtime(os.path.join(WG, "dashboard", "smart.json")))


def _cache_art(tmdb, url):
    """Fetch the TMDB backdrop ONCE into the served dashboard dir and return its same-origin path (or None).

    The legacy page embeds the TMDB URL directly, which is an external request. The v2 bundle runs under a strict
    CSP (default-src 'self') and must make none, so the producer - which is server-side and already talks to TMDB
    for this exact URL - does the fetching instead. Verified to be a real JPEG before it is published.
    """
    if not tmdb or not url.startswith("https://image.tmdb.org/"):
        return None
    try:
        fn = "%d.jpg" % int(tmdb)
    except Exception:
        return None
    path = os.path.join(ART_DIR, fn)
    rel = "/art/" + fn
    try:
        if os.path.isfile(path) and os.path.getsize(path) > 1024:
            return rel
    except Exception:
        pass
    try:
        os.makedirs(ART_DIR, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "cortex-art-cache"})
        with urllib.request.urlopen(req, timeout=10) as r:
            blob = r.read(4 * 1024 * 1024)
        if len(blob) < 1024 or blob[:2] != b"\xff\xd8":       # JPEG magic - never publish a 404 page as art
            return None
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, path)
        return rel
    except Exception:
        return None


def _emit_tonight(d):
    idx = 0
    pool = 0
    try:
        idx = int((bc.read_json(os.path.join(WG, "audit", "tonight-pick.json")) or {}).get("idx", 0))
    except Exception:
        idx = 0
    idx = max(0, idx)
    recs = bc.read_json(os.path.join(WG, "audit", "personal-recs.json"))
    rec = None
    if isinstance(recs, list) and recs:
        pool = len(recs)
        # Same resolution gen-dashboard.gather_tonight uses (idx % len), so we can recover the tmdb id it dropped
        # from its render tuple. Cross-checked on title below rather than assumed.
        cand = recs[idx % pool]
        if isinstance(cand, dict):
            rec = cand
    tn = d.get("tonight")
    pick = None
    if tn:
        art = _s(tn.get("art"))
        tmdb = None
        if rec is not None and _s(rec.get("title")) == _s(tn.get("title")):
            tmdb = rec.get("tmdb") if isinstance(rec.get("tmdb"), int) else None
        pick = {"title": _s(tn.get("title")),
                "year": tn.get("year") if isinstance(tn.get("year"), int) else _s(tn.get("year")),
                "why": _s(tn.get("why")), "genres": _s(tn.get("genres")),
                "tmdb": tmdb,
                "art_url": art,
                "art_external": art.startswith("http"),
                "art_local": _cache_art(tmdb, art)}
    bc.write_contract("tonight-pick", {"pick": pick, "idx": idx, "pool": pool})


def _emit_taste(d):
    t = d.get("taste")
    if not t:
        return                                        # no taste data: leave the previous contract alone rather
                                                      # than overwrite it with an empty-but-fresh-looking one
    hist = t.get("hist") or {}
    histogram = [{"rating": i, "count": int(hist.get(i, hist.get(str(i), 0)) or 0)} for i in range(1, 11)]
    dec = t.get("dec") or {}
    decades = []
    for k in sorted(dec.keys(), key=lambda x: int(x)):
        decades.append({"decade": int(k), "count": int(dec[k] or 0)})
    bc.write_contract("taste", {"total": int(t.get("total") or 0), "histogram": histogram,
                                "decades": decades, "cached": bool(t.get("cached"))},
                      generated_at_ts=bc.mtime(os.path.join(WG, "audit", "trakt-ratings.json")))


EMITTERS = [
    ("services", _emit_services), ("storage", _emit_storage), ("pipeline", _emit_pipeline),
    ("hnr", _emit_hnr), ("library-stats", _emit_library_stats), ("plex-now", _emit_plex_now),
    ("calendar", _emit_calendar), ("activity", _emit_activity), ("health", _emit_health),
    ("security", _emit_security), ("smart", _emit_smart), ("tonight-pick", _emit_tonight),
    ("taste", _emit_taste),
]


def emit(d):
    """Write every ops contract, then refresh the wrapped file contracts. Never raises."""
    ok, failed, skipped = [], [], []
    for name, fn in EMITTERS:
        try:
            fn(d)
            ok.append(name)
        except Exception as e:
            failed.append({"contract": name, "error": "%s: %s" % (type(e).__name__, e)})
    try:
        w_ok, w_failed, w_skipped = wrap_files.wrap_all()
        ok.extend(w_ok)
        failed.extend(w_failed)
        skipped.extend(w_skipped)
    except Exception as e:
        failed.append({"contract": "wrap_files", "error": "%s: %s" % (type(e).__name__, e)})
    try:
        os.makedirs(bc.DATA, exist_ok=True)
        p = os.path.join(bc.DATA, "_emit-status.json")
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"emitted_at": bc.iso(), "written": sorted(ok),
                       "unchanged_skipped": sorted(skipped), "failed": failed}, fh,
                      ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except Exception:
        pass
    return ok, failed


if __name__ == "__main__":
    # Standalone smoke test: re-gathers via gen-dashboard (a real API pass) and emits. Normal operation goes
    # through gen-dashboard's own tail hook, which passes the dict it already has.
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen_dashboard", os.path.join(WG, "dashboard", "gen-dashboard.py"))
    mod = importlib.util.module_from_spec(spec)
    os.chdir(os.path.join(WG, "dashboard"))
    sys.path.insert(0, os.path.join(WG, "dashboard"))
    spec.loader.exec_module(mod)
    t0 = time.time()
    o, f = emit(mod.gather())
    print("emitted %d ok, %d failed in %.1fs" % (len(o), len(f), time.time() - t0))
    for x in f:
        print("  FAIL", x)
