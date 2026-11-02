# plex_rows.py - put the taste pages on the TV (wg\GAMEPLAN-TASTE-LOOP-2026-11.md s8). Owns four Plex collections
# directly through the Plex API and promotes them to michael's HOME screen (not shared users' - decision D5):
#   Movies:   "Missed Gems"            (missed-gems films: gems then landed, contract order = taste order)
#             "Streaming Best: On Your Shelf"  (films added from the page - tag streaming-best - or on the current
#                                                list, once a file is on disk; newest first)
#   TV Shows: "Missed Gems: Shows"     (never-started series, taste order)
#             "Streaming Best: On Your Shelf"  (series added from the page with episodes on disk)
# DEVIATION from the gameplan (2026-11-02): it said Kometa; Kometa refuses collection_order: custom with an id list
# ("custom can only be used with a single builder"), and the taste ORDER is the point of the row - so the rows are
# managed here instead (Kometa's config was restored byte-exact). Collections only ever group existing library
# items: nothing is downloaded, moved or deleted; removing an item from a collection never touches the media.
# Idempotent: membership synced to the contract, custom sort order applied, hub promotion verified by re-read.
# An empty row keeps its collection but empties it and drops it from the home screen (honest, reversible).
import json, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brain_contracts as bc
import taste_core as tc

SUMMARY = {
    "Missed Gems": "Already on your shelf, never played, and very much your kind of thing - ranked by Cortex, refreshed weekly.",
    "Missed Gems: Shows": "Series on your shelf you have never started, ranked by Cortex, refreshed weekly.",
    "Streaming Best: On Your Shelf": "Picks you added from Cortex's Streaming Best page, ready to play.",
}


class Plex(object):
    def __init__(self):
        self.tok = tc.plex_token()

    def req(self, path, method="GET", timeout=60):
        sep = "&" if "?" in path else "?"
        r = urllib.request.Request(tc.PLEX + path + sep + "X-Plex-Token=" + self.tok, method=method,
                                   headers={"Accept": "application/json"})
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        try:
            return json.loads(raw).get("MediaContainer", {}) if raw.strip() else {}
        except ValueError:
            return {}


def tmdb_map(px, section, ptype):
    out = {}
    for m in px.req("/library/sections/%s/all?type=%s&includeGuids=1" % (section, ptype)).get("Metadata") or []:
        for g in m.get("Guid") or []:
            if g.get("id", "").startswith("tmdb://") and g["id"][7:].isdigit():
                out[int(g["id"][7:])] = str(m["ratingKey"])
    return out


def sync_collection(px, mid, section, ptype, title, rks, log):
    """Make collection `title` in `section` hold exactly `rks` in that order; promote/unpromote on home. Returns a
    verification dict."""
    uri = lambda keys: urllib.parse.quote("server://%s/com.plexapp.plugins.library/library/metadata/%s" % (mid, ",".join(keys)), safe="")
    cols = [c for c in px.req("/library/sections/%s/collections" % section).get("Metadata") or [] if c.get("title") == title]
    cid = str(cols[0]["ratingKey"]) if cols else None
    if cid is None:
        if not rks:
            return {"title": title, "items": 0, "home": False, "note": "empty - not created"}
        made = px.req("/library/collections?type=%s&title=%s&smart=0&sectionId=%s&uri=%s"
                      % (ptype, urllib.parse.quote(title), section, uri(rks)), method="POST")
        cid = str(((made.get("Metadata") or [{}])[0]).get("ratingKey") or "")
        if not cid:
            raise RuntimeError("Plex did not return a collection id for %s" % title)
        log("created collection %s (%s)" % (title, cid))
    cur = [str(c["ratingKey"]) for c in px.req("/library/collections/%s/children" % cid).get("Metadata") or []]
    add = [k for k in rks if k not in cur]
    drop = [k for k in cur if k not in rks]
    if add:
        px.req("/library/collections/%s/items?uri=%s" % (cid, uri(add)), method="PUT")
    for k in drop:
        px.req("/library/collections/%s/items/%s" % (cid, k), method="DELETE")
    px.req("/library/metadata/%s/prefs?collectionSort=2" % cid, method="PUT")          # 2 = custom order
    prev = None
    for k in rks:
        px.req("/library/collections/%s/items/%s/move%s" % (cid, k, ("?after=" + prev) if prev else ""), method="PUT")
        prev = k
    px.req("/library/sections/%s/all?type=18&id=%s&summary.value=%s&summary.locked=1"
           % (section, cid, urllib.parse.quote(SUMMARY.get(title, ""))), method="PUT")
    # home-screen promotion (own home only)
    want_home = bool(rks)
    hubs = px.req("/hubs/sections/%s/manage" % section).get("Hub") or []
    hub = next((h for h in hubs if str(h.get("identifier", "")).endswith("." + cid) or str(h.get("title")) == title), None)
    flags = "promotedToRecommended=%d&promotedToOwnHome=%d&promotedToSharedHome=0" % (int(want_home), int(want_home))
    if hub is None:
        if want_home:
            px.req("/hubs/sections/%s/manage?metadataItemId=%s&%s" % (section, cid, flags), method="POST")
    else:
        px.req("/hubs/sections/%s/manage/%s?%s" % (section, urllib.parse.quote(str(hub["identifier"])), flags), method="PUT")
    # verify by re-read
    got = [str(c["ratingKey"]) for c in px.req("/library/collections/%s/children" % cid).get("Metadata") or []]
    hubs = px.req("/hubs/sections/%s/manage" % section).get("Hub") or []
    hub = next((h for h in hubs if str(h.get("identifier", "")).endswith("." + cid) or str(h.get("title")) == title), None)
    return {"title": title, "id": cid, "items": len(got), "order_ok": got == rks, "members_ok": sorted(got) == sorted(rks),
            "home": bool(hub and hub.get("promotedToOwnHome")), "shared_home": bool(hub and hub.get("promotedToSharedHome")),
            "added": len(add), "removed": len(drop)}


def plan():
    mg = (bc.read_json(os.path.join(bc.DATA, "missed-gems.json")) or {}).get("data") or {}
    sb = (bc.read_json(os.path.join(bc.DATA, "streaming-best.json")) or {}).get("data") or {}
    if not mg or not sb:
        raise SystemExit("CANNOT TELL: missed-gems or streaming-best contract unreadable - collections left as they are")
    movies = {m["tmdbId"]: m for m in tc.arr_get(tc.RADARR, "radarr", "/movie") if m.get("tmdbId")}
    series = {s["tvdbId"]: s for s in tc.arr_get(tc.SONARR, "sonarr", "/series") if s.get("tvdbId")}
    rtag = next((t["id"] for t in tc.arr_get(tc.RADARR, "radarr", "/tag") if t.get("label") == "streaming-best"), None)
    stag = next((t["id"] for t in tc.arr_get(tc.SONARR, "sonarr", "/tag") if t.get("label") == "streaming-best"), None)
    has_eps = lambda s: ((s or {}).get("statistics") or {}).get("episodeFileCount", 0) > 0
    gem_films, gem_shows = [], []
    for r in (mg.get("gems") or []) + (mg.get("landed") or []):
        if r.get("type") == "movie" and r.get("rating_key") and r["rating_key"] not in gem_films:
            gem_films.append(r["rating_key"])
    for r in mg.get("shows") or []:
        if r.get("rating_key"):
            gem_shows.append(r["rating_key"])
    shelf_f = [m["tmdbId"] for m in sorted(movies.values(), key=lambda m: m.get("added") or "", reverse=True)
               if m.get("hasFile") and (rtag in (m.get("tags") or []))]
    shelf_f += [r["tmdb_id"] for r in sb.get("items") or [] if r.get("type") == "movie" and (movies.get(r.get("tmdb_id")) or {}).get("hasFile")
                and r["tmdb_id"] not in shelf_f]
    shelf_s = [s["tmdbId"] for s in sorted(series.values(), key=lambda s: s.get("added") or "", reverse=True)
               if has_eps(s) and stag in (s.get("tags") or []) and s.get("tmdbId")]
    shelf_s += [r["tmdb_id"] for r in sb.get("items") or [] if r.get("type") == "tv" and has_eps(series.get(r.get("tvdb_id")))
                and r.get("tmdb_id") and r["tmdb_id"] not in shelf_s]
    return gem_films, gem_shows, shelf_f, shelf_s


def main():
    log = lambda m: print(m, flush=True)
    try:
        gem_films, gem_shows, shelf_f, shelf_s = plan()
        px = Plex()
        mid = px.req("/").get("machineIdentifier")
        fmap, smap = tmdb_map(px, "1", "1"), tmdb_map(px, "2", "2")
        shelf_f_rk = [fmap[t] for t in shelf_f if t in fmap]
        shelf_s_rk = [smap[t] for t in shelf_s if t in smap]
        res = [sync_collection(px, mid, "1", "1", "Missed Gems", gem_films, log),
               sync_collection(px, mid, "1", "1", "Streaming Best: On Your Shelf", shelf_f_rk, log),
               sync_collection(px, mid, "2", "2", "Missed Gems: Shows", gem_shows, log),
               sync_collection(px, mid, "2", "2", "Streaming Best: On Your Shelf", shelf_s_rk, log)]
    except SystemExit as ex:
        print(ex)
        return 2
    except Exception as ex:
        print("FATAL: %s: %s" % (type(ex).__name__, ex))
        return 1
    bad = 0
    for r in res:
        ok = r.get("items", 0) == 0 or (r.get("members_ok") and r.get("order_ok") and r.get("home") and not r.get("shared_home"))
        bad += 0 if ok else 1
        log("%s %s" % ("OK  " if ok else "FAIL", json.dumps(r)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
