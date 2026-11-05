r"""kids_shelf.py - Cortex producer for the `kids-shelf` contract (Spin to Watch).

Reads every movie section of the LAN Plex Media Server, keeps the kid-safe
titles, and writes wg\brain\data\kids-shelf.json through
brain_contracts.write_contract (the house {_meta, data} envelope; served to
clients at /v2/data/kids-shelf.json because the registry marks it client:true).
Install next to brain_contracts.py in wg\brain\producers\.

Kid-safe rules (FILTER_VERSION 2, 2026-11-04):
  --rule cartoons (DEFAULT since 2026-11-04; the Round 3 "Cartoons" wheel):
            genres include Animation
            AND ( rating in {G, PG, TV-Y, TV-Y7, TV-Y7-FV, TV-G}
                  OR unrated AND genres include Family or Children )
            AND NOT ( genres include Anime AND the rating is not a kid rating )
  --rule broad (the Round 1 rule; what "Everything" means):
            rating in {G, PG, TV-Y, TV-Y7, TV-Y7-FV, TV-G, TV-PG}        (rule "rating")
            or genres include Animation or Family AND not an adult rating (rule "genre")
  adult  =  PG-13, R, NC-17, X, TV-14, TV-MA, NR-adult variants, or any
            numeric age rating >= 12 (e.g. "gb/15", "de/16", "18").
  A country prefix ("us/PG", "gb/PG") is stripped before matching.

GENRE COMPLETENESS (the 2026-11-04 field finding): a Plex section listing
(/library/sections/<k>/all) returns only the FIRST TWO Genre tags per item -
Frozen lists as "Family, Fantasy" although its full record carries seven genres
including Animation. Any genre rule evaluated on the listing alone silently
drops Frozen, Moana, Encanto, Tangled, Inside Out, Minions, Toy Story 4 and
Zootopia (39 Disney/Pixar/DreamWorks/Illumination films on 2026-11-04). So
load_candidates_from_plex() completes every item's genres from the section's
genre index (/library/sections/<k>/genre, then /all?genre=<id> per genre),
which is exhaustive. Shelf items therefore carry COMPLETE genre lists.

CURATION ALLOW-LIST: spin-curation.json next to the --config file (or
--curation PATH) lists ratingKeys admitted whatever the rule says (mainstream
live-action family films: Sonic, Paddington, Minecraft...). Rule name "allow".
Exclusions are NOT here: they are spin-rules.json "bans" (parent page).

Deterministic: items sorted by numeric ratingKey, fixed field set; the only
run-to-run variance is _meta.generated_at/emitted_at. data.content_hash is the
sha256 of the items array, so consumers can tell "same shelf" cheaply.

Exit codes (honest, house style):
  0  wrote the contract
  1  FAILED: Plex unreachable, config/registry problem, or zero kid-safe
     titles - NOTHING written
  2  CANNOT TELL: the shelf would shrink below --max-shrink of the current
     contract (a half-scanned library looks exactly like this) - NOTHING
     written; re-run with --allow-shrink after checking

Stdlib only, Python 3.10.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

CONTRACT = "kids-shelf"
FILTER_VERSION = 2
DEFAULT_RULE = "cartoons"

KID_RATINGS = frozenset({"G", "PG", "TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G", "TV-PG"})
CARTOON_RATINGS = frozenset({"G", "PG", "TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G"})   # no TV-PG on the kid wheel
KID_GENRES = frozenset({"animation", "family"})
UNRATED_OK_GENRES = frozenset({"family", "children"})
UNRATED = frozenset({"", "NR", "NOT RATED", "UNRATED", "NONE"})
ADULT_RATINGS = frozenset({
    "PG-13", "R", "NC-17", "NC17", "X", "XXX", "TV-14", "TV-MA", "M", "MA", "MA15+",
    "R18+", "AO", "18+", "NR-17", "UNRATED-ADULT",
})
_AGE_RE = re.compile(r"^(?:FSK|PEGI|KIJ|ICAA|USK)?\s*-?\s*(\d{1,2})\+?$")

OUTPUT_FIELDS = (
    "ratingKey", "guid", "title", "year", "contentRating", "genres", "durationMin",
    "thumb", "art", "studio", "summary", "addedAt", "viewCount", "lastViewedAt",
    "videoResolution", "videoCodec", "audioCodec",
)


# --------------------------------------------------------------------------
# Filter (pure, unit-tested)
# --------------------------------------------------------------------------
def normalize_rating(raw) -> str:
    if raw is None:
        return ""
    r = str(raw).strip()
    if "/" in r:                       # "us/PG", "gb/15"
        r = r.split("/", 1)[1]
    return r.strip().upper()


def is_adult_rating(raw) -> bool:
    r = normalize_rating(raw)
    if not r:
        return False
    if r in ADULT_RATINGS:
        return True
    m = _AGE_RE.match(r)
    if m and int(m.group(1)) >= 12:
        return True
    return False


def kid_safe_reason_broad(item: dict) -> str | None:
    """Round 1 rule ("Everything"): the rule name that admits the item, or None."""
    rating = normalize_rating(item.get("contentRating"))
    if rating in KID_RATINGS:
        return "rating"
    genres = {str(g).strip().lower() for g in (item.get("genres") or [])}
    if genres & KID_GENRES and not is_adult_rating(item.get("contentRating")):
        return "genre"
    return None


def kid_safe_reason_cartoons(item: dict) -> str | None:
    """The Cartoons rule (default): animated, kid-rated (or unrated family/children), not unrated anime."""
    genres = {str(g).strip().lower() for g in (item.get("genres") or [])}
    if "animation" not in genres:
        return None
    rating = normalize_rating(item.get("contentRating"))
    kid_rated = rating in CARTOON_RATINGS
    unrated = rating in UNRATED
    if not kid_rated and not (unrated and genres & UNRATED_OK_GENRES):
        return None
    if "anime" in genres and not kid_rated:
        return None
    return "cartoon"


RULES = {"cartoons": kid_safe_reason_cartoons, "broad": kid_safe_reason_broad}


def kid_safe_reason(item: dict, rule: str = DEFAULT_RULE) -> str | None:
    """Return the rule name that admits the item under `rule`, or None if it is excluded."""
    return RULES[rule](item)


# --------------------------------------------------------------------------
# Plex -> shelf item
# --------------------------------------------------------------------------
def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def from_plex_metadata(m: dict) -> dict:
    media = (m.get("Media") or [{}])[0] or {}
    duration_ms = _int_or_none(m.get("duration")) or _int_or_none(media.get("duration"))
    return {
        "ratingKey": str(m.get("ratingKey", "")),
        "guid": m.get("guid") or "",
        "title": m.get("title") or "",
        "year": _int_or_none(m.get("year")),
        "contentRating": m.get("contentRating") or "",
        "genres": [g.get("tag") for g in (m.get("Genre") or []) if g.get("tag")],
        "durationMin": round(duration_ms / 60000) if duration_ms else None,
        "thumb": m.get("thumb") or "",
        "art": m.get("art") or "",
        "studio": m.get("studio") or "",
        "summary": m.get("summary") or "",
        "addedAt": _int_or_none(m.get("addedAt")),
        "viewCount": _int_or_none(m.get("viewCount")) or 0,
        "lastViewedAt": _int_or_none(m.get("lastViewedAt")),
        "videoResolution": media.get("videoResolution") or "",
        "videoCodec": media.get("videoCodec") or "",
        "audioCodec": media.get("audioCodec") or "",
    }


def normalize_item(item: dict) -> dict:
    """Coerce an already-shelf-shaped item (e.g. the sample export) to the fixed field set."""
    out = {}
    for f in OUTPUT_FIELDS:
        v = item.get(f)
        if f == "ratingKey":
            v = str(v if v is not None else "")
        elif f == "genres":
            v = [str(g) for g in (v or [])]
        elif f in ("year", "durationMin", "addedAt", "lastViewedAt"):
            v = _int_or_none(v)
        elif f == "viewCount":
            v = _int_or_none(v) or 0
        else:
            v = "" if v is None else str(v)
        out[f] = v
    return out


def _rk_sort_key(item):
    rk = item["ratingKey"]
    return (0, int(rk), "") if rk.isdigit() else (1, 0, rk)


def build_items(candidates, rule: str = DEFAULT_RULE, allow=()) -> tuple[list, dict]:
    """Filter + dedupe + sort. Returns (items, stats). `allow` = ratingKeys admitted regardless of the rule."""
    seen = {}
    allow = {str(k) for k in allow}
    stats = {"scanned": 0, "rating": 0, "genre": 0, "cartoon": 0, "allow": 0, "excluded": 0, "duplicates": 0}
    for raw in candidates:
        stats["scanned"] += 1
        item = normalize_item(raw)
        if not item["ratingKey"] or not item["title"]:
            stats["excluded"] += 1
            continue
        reason = "allow" if item["ratingKey"] in allow else kid_safe_reason(item, rule)
        if reason is None:
            stats["excluded"] += 1
            continue
        if item["ratingKey"] in seen:
            stats["duplicates"] += 1
            continue
        stats[reason] += 1
        seen[item["ratingKey"]] = item
    items = sorted(seen.values(), key=_rk_sort_key)
    return items, stats


def content_hash(items: list) -> str:
    blob = json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("ascii")).hexdigest()


def build_data(candidates, source: str, rule: str = DEFAULT_RULE, allow=()) -> dict:
    """The contract payload (validated by contracts/kids-shelf.schema.json)."""
    items, stats = build_items(candidates, rule, allow)
    if rule == "cartoons":
        filt = {"version": FILTER_VERSION, "rule": "cartoons", "ratings": sorted(CARTOON_RATINGS),
                "genres": ["Animation"], "unrated_ok_genres": ["Family", "Children"],
                "adult": "Animation AND (kid rating OR unrated Family/Children) AND NOT unrated Anime; "
                         "genres completed from the Plex genre index (listings truncate to 2)"}
    else:
        filt = {"version": FILTER_VERSION, "rule": "broad", "ratings": sorted(KID_RATINGS),
                "genres": ["Animation", "Family"],
                "adult": "PG-13, R, NC-17, TV-14, TV-MA and any age rating >= 12 never pass the genre rule"}
    return {
        "source": source,
        "filter": filt,
        "counts": {"kids_shelf": len(items), "scanned": stats["scanned"], "by_rule_rating": stats["rating"],
                   "by_rule_genre": stats["genre"], "by_rule_cartoon": stats["cartoon"],
                   "by_rule_allow": stats["allow"],
                   "excluded": stats["excluded"], "duplicates": stats["duplicates"]},
        "content_hash": content_hash(items),
        "items": items,
    }


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------
def load_candidates_from_file(path: str) -> list:
    with open(path, "r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    if isinstance(data.get("data"), dict):  # a {_meta, data} contract envelope
        data = data["data"]
    for key in ("items", "titles", "movies", "Metadata"):
        if isinstance(data.get(key), list):
            return data[key]
    if isinstance(data.get("MediaContainer"), dict):
        return [from_plex_metadata(m) for m in data["MediaContainer"].get("Metadata", [])]
    raise ValueError("no item list found in %s" % path)


SKIP_SECTIONS = frozenset({"home movies"})     # never scanned (Round 3 brief)


def section_genre_index(plex, section_key) -> dict:
    """ratingKey -> [genre, ...] for EVERY item of the section, from the genre index.
    Exhaustive where the listing is not: /all?genre=<id> returns every item carrying that tag."""
    key = str(section_key)
    idx = {}
    mc = plex.get_json("/library/sections/%s/genre" % key, {"type": "1"})
    for d in mc.get("Directory", []) or []:
        gid, tag = d.get("key"), d.get("title")
        if not gid or not tag:
            continue
        hits = plex.get_json("/library/sections/%s/all" % key, {"type": "1", "genre": str(gid)})
        for m in hits.get("Metadata", []) or []:
            rk = str(m.get("ratingKey", ""))
            if rk:
                idx.setdefault(rk, []).append(str(tag))
    return idx


def complete_genres(items: list, idx: dict) -> int:
    """Union each item's listing genres with the index; returns how many items gained a genre."""
    gained = 0
    for it in items:
        full = idx.get(it["ratingKey"])
        if not full:
            continue
        have = list(it.get("genres") or [])
        extra = [g for g in full if g not in have]
        if extra:
            it["genres"] = have + extra
            gained += 1
    return gained


def load_candidates_from_plex(plex) -> tuple[list, str]:
    sections = [s for s in plex.movie_sections() if str(s.get("title", "")).strip().lower() not in SKIP_SECTIONS]
    if not sections:
        raise RuntimeError("Plex reports no movie sections")
    out, gained = [], 0
    for sec in sections:
        items = [from_plex_metadata(m) for m in plex.section_movies(sec.get("key"))]
        try:
            gained += complete_genres(items, section_genre_index(plex, sec.get("key")))
        except Exception as exc:   # the index is a completeness aid; a failure must be loud, not silent
            raise RuntimeError("genre index for section %s failed: %s: %s" % (sec.get("key"), type(exc).__name__, exc))
        out.extend(items)
    names = ", ".join(sorted(str(x.get("title", x.get("key"))) for x in sections))
    return out, "Plex movie sections: %s (%d titles scanned, %d genre lists completed from the index)" % (
        names, len(out), gained)


def current_count(bc) -> int | None:
    env = bc.read_json(os.path.join(bc.DATA, CONTRACT + ".json"))
    try:
        return int(env["data"]["counts"]["kids_shelf"])
    except (TypeError, KeyError, ValueError):
        return None


def load_allow(path: str | None) -> list:
    """ratingKeys from a spin-curation.json ({"allow": [{"ratingKey": ..}, ..]} or a plain list). Missing file = []."""
    if not path or not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    rows = data.get("allow", []) if isinstance(data, dict) else data
    out = []
    for r in rows or []:
        k = r.get("ratingKey") if isinstance(r, dict) else r
        if k not in (None, ""):
            out.append(str(k))
    return out


def _load_config(path: str | None) -> dict:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        pass  # pythonw: no console


def main(argv=None, bc=None, plex=None) -> int:
    ap = argparse.ArgumentParser(description="Produce the kids-shelf Cortex contract.")
    ap.add_argument("--config", help="roku-play config JSON (optional; uses its 'plex' block)")
    ap.add_argument("--from-file", help="build from a JSON export instead of live Plex (dev/tests)")
    ap.add_argument("--max-shrink", type=float, default=0.5,
                    help="CANNOT TELL (exit 2) if the count drops below this fraction of the current contract")
    ap.add_argument("--allow-shrink", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the summary, write nothing")
    ap.add_argument("--curation", help="spin-curation.json allow-list (default: next to --config)")
    ap.add_argument("--rule", choices=sorted(RULES), default=DEFAULT_RULE,
                    help="cartoons (default: animated + kid-rated) or broad (Round 1: any G/PG/TV-G or Animation/Family)")
    args = ap.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        if bc is None:
            import brain_contracts as bc  # noqa: E402  (lives next to this file in wg\brain\producers)
        bc.entry(CONTRACT)  # registry must know the contract before anything is fetched
        cfg = _load_config(args.config)
        cur = args.curation or (os.path.join(os.path.dirname(os.path.abspath(args.config)), "spin-curation.json")
                                if args.config else None)
        allow = load_allow(cur)
    except Exception as exc:
        log("FAILED: %s: %s - nothing written" % (type(exc).__name__, exc))
        return 1

    try:
        if args.from_file:
            candidates = load_candidates_from_file(args.from_file)
            source = "file export %s (%d rows)" % (os.path.basename(args.from_file), len(candidates))
        else:
            if plex is None:
                for p in (os.path.join(here, "..", "..", "dashboard"), os.path.join(here, "..", "dashboard")):
                    if os.path.isdir(p) and p not in sys.path:
                        sys.path.insert(0, p)
                from plex_lan import PlexLan  # noqa: E402
                pcfg = cfg.get("plex") or {}
                plex = PlexLan(pcfg.get("base_url") or "http://127.0.0.1:32400", pcfg.get("credential_file") or None)
            candidates, source = load_candidates_from_plex(plex)
    except Exception as exc:  # Plex/network/file failure -> honest exit 1, no write
        log("FAILED reading source: %s: %s - nothing written" % (type(exc).__name__, exc))
        return 1

    data = build_data(candidates, source, args.rule, allow)
    c = data["counts"]
    if c["kids_shelf"] == 0:
        log("FAILED: zero kid-safe titles (scanned %d) - nothing written" % c["scanned"])
        return 1
    prev = current_count(bc)
    if prev and not args.allow_shrink and c["kids_shelf"] < prev * args.max_shrink:
        log("CANNOT TELL: shelf would shrink %d -> %d (below %.0f%%) - nothing written; "
            "re-run with --allow-shrink if intended" % (prev, c["kids_shelf"], args.max_shrink * 100))
        return 2
    summary = "kids-shelf: %d titles (rule=%s cartoon=%d allow=%d rating=%d genre=%d excluded=%d dup=%d) %s" % (
        c["kids_shelf"], args.rule, c["by_rule_cartoon"], c["by_rule_allow"], c["by_rule_rating"], c["by_rule_genre"],
        c["excluded"], c["duplicates"], data["content_hash"][:19])
    if args.dry_run:
        log(summary + " (dry run, nothing written)")
        return 0
    try:
        path = bc.write_contract(CONTRACT, data)
    except Exception as exc:
        log("FAILED writing contract: %s: %s" % (type(exc).__name__, exc))
        return 1
    log(summary + " -> " + path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # house rule: never a traceback-shaped success
        log("FAILED: %s: %s - nothing written" % (type(e).__name__, e))
        sys.exit(1)
