# taste_core.py - the ONE "is this michael?" scoring module shared by streaming_best.py (page 1, outward) and
# missed_gems.py (page 2, inward). Import-only: importing it does nothing; every network call happens inside an
# explicit method call. Pure stdlib, pure ASCII source. Spec: wg\GAMEPLAN-STREAMING-PAGES-2026-10.md.
#
# WHAT "ME" MEANS HERE (assembled only from assets that already exist on this box - nothing new is collected):
#   * RATINGS   wg\audit\trakt-ratings.json - 488 banked film ratings (a frozen Trakt snapshot; Trakt itself is dead
#               and NEVER called). love >= 8, meh 6-7, dislike <= 5.
#   * GENRES    two signals blended: (a) the ratings themselves - per-genre mean deviation from his own average,
#               shrunk toward zero for thin genres; (b) the taste-graph contract's 'michael' persona genre counts
#               (what he actually plays). Page 1 may add the taste-velocity heat as a mild multiplier.
#   * PEOPLE    directors / creators + top-billed cast harvested from the TMDB credits of the films he rated.
#               Loved films push a person up, disliked films push them down. The 16 auteur loyalties curated in
#               wg\audit\passport.ps1 (read READ-ONLY via gap_radar's parser) are a strong prior on top.
#   * SEEDS     the loved films (and, for TV, the series the taste-graph says he binges) are the comparison set.
#               Similarity = TMDB keyword overlap + genre overlap + shared people. The seeds a candidate is most
#               similar to become its `because` list - the UI explains itself from these, never from prose.
#
# HARD RULES (code, not UI - guardrail 8):
#   * 1987 year floor for films (memory cinematic-taste-profile). Page 1's 18-month window makes it moot there.
#   * NO kids / household lanes: Family, Kids and Children are always excluded. Animation is excluded UNLESS his
#     own ratings show he loves animation (the shared Plex account pollutes Animation - Taste Velocity proved it -
#     so only his RATINGS may open that lane, never household plays).
#   * Documentary / talk / reality / news are excluded unless his ratings give the genre a positive weight.
#
# TMDB is the only external service (key wg\tmdb.key). Every lookup is cached under wg\brain\data\cache\tmdb\ and
# throttled (TMDB_SLEEP between live calls) - gentle by construction. NEVER api.trakt.tv.
import json, math, os, re, sys, time, urllib.parse, urllib.request, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
RATINGS = os.path.join(WG, "audit", "trakt-ratings.json")
# Taste loop (wg\GAMEPLAN-TASTE-LOOP-2026-11.md): taste_ledger.py compiles the frozen base + the append-only ledger
# into ratings-effective.json (same list shape) + taste-signals.json. Read those when sane, else fall back to the
# base - a broken loop can never take the pages down. TASTE_OUT_DIR / TASTE_OFF_PATH are the tests' overrides.
EFFECTIVE_MIN_ROWS = 400
THUMB_UP_W = 0.35           # a thumbs-up is a seed at about the weight of an 8 (8 -> .33)
SOFT_DISLIKE_W = 0.5        # thumbs-down and "bailed" count as half a dislike


def taste_paths():
    out = os.environ.get("TASTE_OUT_DIR") or os.path.join(WG, "audit")
    off = os.environ.get("TASTE_OFF_PATH") or os.path.join(WG, "brain", "TASTE-LEDGER-OFF")
    return os.path.join(out, "ratings-effective.json"), os.path.join(out, "taste-signals.json"), off


def ratings_source():
    """(rows, source_name, signals_dict). ratings-effective when present, parseable and >= EFFECTIVE_MIN_ROWS rows
    and the loop is not switched off; otherwise the frozen Trakt base with empty signals."""
    eff_p, sig_p, off = taste_paths()
    if not os.path.exists(off):
        rows = bc.read_json(eff_p)
        if isinstance(rows, list) and len(rows) >= EFFECTIVE_MIN_ROWS:
            sig = bc.read_json(sig_p)
            return rows, "ratings-effective", sig if isinstance(sig, dict) else {}
    return bc.read_json(RATINGS), "trakt-ratings", {}


PASSPORT_PS1 = os.path.join(WG, "audit", "passport.ps1")
CACHE = os.path.join(bc.DATA, "cache", "tmdb")
RADARR = "http://127.0.0.1:7878/api/v3"
SONARR = "http://127.0.0.1:8989/api/v3"
PLEX = "http://127.0.0.1:32400"

YEAR_FLOOR = 1987
LOVE, DISLIKE = 8, 5
TMDB_SLEEP = 0.25
STATIC_TTL_D = 180          # rated / owned titles: credits + keywords barely change
LIVE_TTL_D = 20             # page-1 candidates: vote counts move, refresh roughly monthly
TV_SEED_MIN_PLAYS = 6       # taste-graph michael topTitles with at least this many plays become TV seeds
TV_SEED_MAX = 8
TV_SEED_RATING = 8          # implied rating for a binged series (it is a "love" by behaviour, not by a score)
SIM_SCALE = 0.12            # raw top-3 similarity that counts as a full-strength match (calibrated on the 2026-10 pool)
QUALITY_M, QUALITY_C = 1500.0, 6.6   # Bayesian prior: votes of weight, prior mean

KIDS = {"Family", "Kids", "Children"}
NONFICTION = {"Documentary", "Talk", "Reality", "News"}
# TMDB's TV genres are compound; fold them into the film genre names his ratings are expressed in.
TV_GENRE_MAP = {
    "Action & Adventure": ["Action", "Adventure"],
    "Sci-Fi & Fantasy": ["Science Fiction", "Fantasy"],
    "War & Politics": ["War"],
}

YEAR_SUFFIX = re.compile(r"\s*\((?:19|20)\d\d\)$")


def norm_title(t):
    """Match key for a title (same rule as taste_velocity.py): lowercased, trimmed, trailing '(1999)' removed."""
    return YEAR_SUFFIX.sub("", (t or "").strip().lower())


def norm_genres(names):
    out = []
    for g in names or []:
        for x in TV_GENRE_MAP.get(g, [g]):
            if x and x not in out:
                out.append(x)
    return out


def api_key(name):
    p = os.path.join(WG, name + ".key")
    return open(p, encoding="utf-8-sig").read().strip() if os.path.isfile(p) else ""


def arr_get(base, keyname, path, timeout=180):
    req = urllib.request.Request(base + path, headers={"X-Api-Key": api_key(keyname)})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def plex_token():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Plex, Inc.\Plex Media Server") as k:
        return winreg.QueryValueEx(k, "PlexOnlineToken")[0]


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / float(len(a | b)) if inter else 0.0


class TMDB:
    """Cached, throttled TMDB v3 client. live_calls / cache_hits / failures are reported by the producers."""

    def __init__(self, key):
        self.key = key
        self.live_calls = 0
        self.cache_hits = 0
        self.failures = 0
        os.makedirs(CACHE, exist_ok=True)

    def get(self, path, params=None):
        q = {"api_key": self.key}
        if params:
            q.update(params)
        url = "https://api.themoviedb.org/3/%s?%s" % (path, urllib.parse.urlencode(q))
        req = urllib.request.Request(url, headers={"User-Agent": "cortex-taste-core/1.0", "Accept": "application/json"})
        for attempt in (1, 2):
            try:
                self.live_calls += 1
                with urllib.request.urlopen(req, timeout=25) as r:
                    out = json.loads(r.read().decode("utf-8"))
                time.sleep(TMDB_SLEEP)
                return out
            except Exception:
                if attempt == 2:
                    self.failures += 1
                    raise
                time.sleep(2.0)

    def details(self, kind, tid, ttl_days):
        """kind 'movie' or 'tv'. Details + credits + keywords (+ release_dates / external_ids), cached."""
        tid = int(tid)
        path = os.path.join(CACHE, "%s-%d.json" % (kind, tid))
        cur = bc.read_json(path)
        if isinstance(cur, dict) and (time.time() - float(cur.get("_fetched", 0))) < ttl_days * 86400:
            self.cache_hits += 1
            return cur
        if kind == "movie":
            d = self.get("movie/%d" % tid, {"append_to_response": "credits,keywords,release_dates"})
        else:
            d = self.get("tv/%d" % tid, {"append_to_response": "aggregate_credits,keywords,external_ids"})
        d = slim(kind, d)
        d["_fetched"] = time.time()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
        return d


def slim(kind, d):
    """Keep only what scoring and the page need (a full TMDB payload with every credit is ~100 KB)."""
    if kind == "movie":
        crew = (d.get("credits") or {}).get("crew") or []
        cast = (d.get("credits") or {}).get("cast") or []
        kw = [k.get("name") for k in ((d.get("keywords") or {}).get("keywords") or []) if k.get("name")]
        digital = False
        today = time.strftime("%Y-%m-%d")
        for c in ((d.get("release_dates") or {}).get("results") or []):
            for rd in c.get("release_dates") or []:
                if rd.get("type") in (4, 5) and (rd.get("release_date") or "9999")[:10] <= today:
                    digital = True
        rel = d.get("release_date") or ""
        return {
            "kind": "movie", "id": d.get("id"), "title": d.get("title") or d.get("original_title") or "",
            "year": int(rel[:4]) if rel[:4].isdigit() else None, "release_date": rel,
            "genres": [g.get("name") for g in d.get("genres") or [] if g.get("name")],
            "keywords": kw[:40],
            "directors": [c.get("name") for c in crew if c.get("job") == "Director" and c.get("name")][:3],
            "cast": [c.get("name") for c in sorted(cast, key=lambda x: x.get("order", 99))[:6] if c.get("name")],
            "vote_average": d.get("vote_average") or 0.0, "vote_count": d.get("vote_count") or 0,
            "popularity": d.get("popularity") or 0.0, "overview": d.get("overview") or "",
            "poster_path": d.get("poster_path"), "original_language": d.get("original_language"),
            "runtime": d.get("runtime"), "digital": digital, "imdb_id": d.get("imdb_id"),
        }
    cast = (d.get("aggregate_credits") or {}).get("cast") or []
    kw = [k.get("name") for k in ((d.get("keywords") or {}).get("results") or []) if k.get("name")]
    fa = d.get("first_air_date") or ""
    return {
        "kind": "tv", "id": d.get("id"), "title": d.get("name") or d.get("original_name") or "",
        "year": int(fa[:4]) if fa[:4].isdigit() else None, "first_air_date": fa,
        "last_air_date": d.get("last_air_date") or "", "status": d.get("status") or "",
        "in_production": bool(d.get("in_production")),
        "next_episode_to_air": (d.get("next_episode_to_air") or {}).get("air_date"),
        "seasons": d.get("number_of_seasons"),
        "genres": [g.get("name") for g in d.get("genres") or [] if g.get("name")],
        "keywords": kw[:40],
        "directors": [c.get("name") for c in d.get("created_by") or [] if c.get("name")][:3],
        "cast": [c.get("name") for c in sorted(cast, key=lambda x: x.get("order", 99))[:6] if c.get("name")],
        "vote_average": d.get("vote_average") or 0.0, "vote_count": d.get("vote_count") or 0,
        "popularity": d.get("popularity") or 0.0, "overview": d.get("overview") or "",
        "poster_path": d.get("poster_path"), "original_language": d.get("original_language"),
        "tvdb_id": (d.get("external_ids") or {}).get("tvdb_id"),
        "imdb_id": (d.get("external_ids") or {}).get("imdb_id"),
    }


def feature_sets(f):
    return {
        "genres": set(norm_genres(f.get("genres"))),
        "keywords": set(k.lower() for k in f.get("keywords") or []),
        "directors": set(f.get("directors") or []),
        "cast": set(f.get("cast") or []),
    }


class Taste:
    """michael's taste profile. Build with Taste(log).build(); then score(features) per candidate."""

    def __init__(self, log=print):
        self.log = log
        self.tmdb = None
        self.ratings = []           # [(tmdb_id, rating, title, year)]
        self.rated_ids = set()
        self.seeds = []             # [{title, rating, weight, sets}] loved films + binged series
        self.dislikes = []          # [{title, rating, sets}]
        self.genre_w = {}           # genre -> weight in [-1, 1]
        self.person_w = collections.defaultdict(float)
        self.person_src = collections.defaultdict(list)   # person -> loved titles they directed/starred in
        self.seed_rating = {}                              # loved title -> rating (prompt grounding)
        self.auteurs = set()
        self.mean = 7.0
        self.animation_ok = False
        self.nonfiction_ok = set()
        self.lang_share = {}
        self.notes = []
        self.source = "trakt-ratings"
        self.signals = {}
        self.rated_tv_ids = set()
        self.blocked = {}           # "movie:<tmdb>" / "tv:<tmdb>" -> reason (thumbs-down, household)

    # ---------------------------------------------------------------------------------------------------- build
    def build(self, tmdb_key, rows=None):
        self.tmdb = TMDB(tmdb_key)
        if rows is None:
            rated, self.source, self.signals = ratings_source()
        else:
            rated, self.source = rows, "injected"       # taste_eval builds on a training split
        self.log("taste source: %s" % self.source)
        if not isinstance(rated, list) or len(rated) < 50:
            raise RuntimeError("ratings seed (%s) missing or implausibly small" % self.source)
        for k in self.signals.get("hidden") or []:
            self.blocked[k] = "hidden by your thumbs-down"
        for d in self.signals.get("household") or []:
            self.blocked.setdefault(d.get("key"), "marked not-me (household)")
        tv_rows = [r for r in rated if r.get("type") == "show" and (r.get("show") or {}).get("ids", {}).get("tmdb")]
        for r in rated:
            m = r.get("movie") or {}
            tid = (m.get("ids") or {}).get("tmdb")
            if tid and isinstance(r.get("rating"), (int, float)):
                self.ratings.append((int(tid), float(r["rating"]), m.get("title") or "", m.get("year")))
                self.rated_ids.add(int(tid))
        self.mean = sum(x[1] for x in self.ratings) / float(len(self.ratings))

        feats, failed = {}, 0
        for tid, rating, title, year in self.ratings:
            try:
                feats[tid] = self.tmdb.details("movie", tid, STATIC_TTL_D)
            except Exception:
                failed += 1
        if failed > len(self.ratings) * 0.2:
            raise RuntimeError("TMDB failed for %d of %d rated films - the profile would be a guess" % (failed, len(self.ratings)))
        if failed:
            self.notes.append("%d rated films could not be looked up on TMDB and were left out of the profile" % failed)

        # --- genre affinity from ratings: shrunk mean deviation from his own average ---
        dev = collections.defaultdict(float)
        cnt = collections.Counter()
        for tid, rating, title, year in self.ratings:
            f = feats.get(tid)
            if not f:
                continue
            for g in set(norm_genres(f.get("genres"))):
                dev[g] += rating - self.mean
                cnt[g] += 1
        rate_aff = {g: dev[g] / (cnt[g] + 4.0) for g in cnt}          # +4 = shrink thin genres toward 0
        # --- taste-graph 'michael' persona: what he actually plays ---
        tg_share = {}
        tg = bc.read_json(os.path.join(bc.DATA, "taste-graph.json"))
        try:
            pm = tg["data"]["personas"]["michael"]
            top = max(1, max(int(x["count"]) for x in pm["topGenres"]))
            tg_share = {x["genre"]: int(x["count"]) / float(top) for x in pm["topGenres"]}
        except Exception:
            self.notes.append("taste-graph michael persona unreadable - genre weights from ratings alone")
        for g in set(rate_aff) | set(tg_share):
            ra = max(-1.0, min(1.0, rate_aff.get(g, 0.0) / 1.2))
            tw = tg_share.get(g, 0.0) - 0.25 if tg_share else 0.0
            self.genre_w[g] = round(max(-1.0, min(1.0, 0.65 * ra + 0.35 * tw)), 3)
        langs = collections.Counter(feats[t].get("original_language") for t, *_ in self.ratings if feats.get(t))
        tot = float(sum(langs.values())) or 1.0
        self.lang_share = {k: n / tot for k, n in langs.items() if k}
        anim = [r for t, r, *_ in self.ratings if feats.get(t) and "Animation" in feats[t].get("genres", [])]
        self.animation_ok = len(anim) >= 3 and (sum(anim) / len(anim)) >= 7.5
        self.nonfiction_ok = {g for g in NONFICTION if self.genre_w.get(g, 0.0) > 0.1 and cnt.get(g, 0) >= 3}

        # --- people affinity + seed sets ---
        for tid, rating, title, year in self.ratings:
            f = feats.get(tid)
            if not f:
                continue
            sets = feature_sets(f)
            if rating >= LOVE:
                w = (rating - 7.0) / 3.0                                    # 8 -> .33, 10 -> 1.0
                self.seeds.append({"title": title or f.get("title"), "rating": rating, "weight": w, "sets": sets, "kind": "movie"})
                self.seed_rating[title or f.get("title")] = rating
                for p in sets["directors"]:
                    self.person_w[p] += 1.0 * w
                    self.person_src[p].append("directed " + (title or f.get("title")))
                for p in sets["cast"]:
                    self.person_w[p] += 0.4 * w
                    self.person_src[p].append(title or f.get("title"))
            elif rating <= DISLIKE:
                self.dislikes.append({"title": title or f.get("title"), "rating": rating, "sets": sets})
                for p in sets["directors"]:
                    self.person_w[p] -= 0.6
                for p in sets["cast"]:
                    self.person_w[p] -= 0.2

        # --- auteur prior (passport.ps1 curated list, read-only via gap_radar's parser) ---
        try:
            import gap_radar
            alias = {"Coen Brothers": ["Joel Coen", "Ethan Coen"]}
            for name, _films in gap_radar.parse_filmography(PASSPORT_PS1):
                for n in alias.get(name, [name]):
                    self.auteurs.add(n)
                    self.person_w[n] += 2.0
        except Exception as ex:
            self.notes.append("auteur list unreadable from passport.ps1 (%s) - no auteur prior" % type(ex).__name__)

        self._tv_seeds()
        self._ledger_tv(tv_rows)
        self._soft_signals()
        self.log("taste profile: %d ratings (mean %.2f), %d loved seeds (%d TV), %d dislikes, %d genres weighted, "
                 "%d people, %d auteurs; animation lane %s; TMDB %d live / %d cached"
                 % (len(self.ratings), self.mean, len(self.seeds), sum(1 for s in self.seeds if s["kind"] == "tv"),
                    len(self.dislikes), len(self.genre_w), len(self.person_w), len(self.auteurs),
                    "OPEN (his ratings)" if self.animation_ok else "closed", self.tmdb.live_calls, self.tmdb.cache_hits))
        return self

    def _tv_seeds(self):
        """Binged series from the taste-graph michael persona become TV seeds (his TV taste has no ratings)."""
        tg = bc.read_json(os.path.join(bc.DATA, "taste-graph.json"))
        try:
            titles = [(x["title"], int(x["plays"])) for x in tg["data"]["personas"]["michael"]["topTitles"]]
        except Exception:
            return
        try:
            series = arr_get(SONARR, "sonarr", "/series")
        except Exception:
            self.notes.append("Sonarr unreachable - no TV seeds")
            return
        by = {}
        for s in series:
            if s.get("tmdbId"):
                by.setdefault(norm_title(s.get("title")), int(s["tmdbId"]))
        n = 0
        for title, plays in titles:
            if plays < TV_SEED_MIN_PLAYS or n >= TV_SEED_MAX:
                continue
            tid = by.get(norm_title(title))
            if not tid:
                continue
            try:
                f = self.tmdb.details("tv", tid, STATIC_TTL_D)
            except Exception:
                continue
            sets = feature_sets(f)
            if sets["genres"] & KIDS or ("Animation" in sets["genres"] and not self.animation_ok):
                continue
            w = (TV_SEED_RATING - 7.0) / 3.0
            self.seeds.append({"title": f.get("title") or title, "rating": TV_SEED_RATING, "weight": w,
                               "sets": sets, "kind": "tv"})
            self.seed_rating[f.get("title") or title] = "binged"
            for p in sets["directors"]:
                self.person_w[p] += 0.6 * w
                self.person_src[p].append("created " + (f.get("title") or title))
            n += 1

    def _ledger_tv(self, tv_rows):
        """Series he RATED (taste loop): >= LOVE join the TV seeds at their real rating, <= DISLIKE become dislikes."""
        for r in tv_rows:
            s = r["show"]
            tid = int(s["ids"]["tmdb"])
            self.rated_tv_ids.add(tid)
            rating = float(r.get("rating") or 0)
            if DISLIKE < rating < LOVE:
                continue
            try:
                f = self.tmdb.details("tv", tid, STATIC_TTL_D)
            except Exception:
                continue
            sets = feature_sets(f)
            title = f.get("title") or s.get("title") or ""
            # The household rates too (2026-11-02: the one show rating in Plex was Gabby's Dollhouse 10/10). A
            # kids-lane title never becomes a seed or a dislike, whoever pressed the stars.
            if sets["genres"] & KIDS or ("Animation" in sets["genres"] and not self.animation_ok):
                self.log("ignored a kids-lane TV rating: %s" % title)
                continue
            if rating >= LOVE:
                w = (rating - 7.0) / 3.0
                self.seeds = [x for x in self.seeds if not (x["kind"] == "tv" and x["title"] == title)]
                self.seeds.append({"title": title, "rating": rating, "weight": w, "sets": sets, "kind": "tv"})
                self.seed_rating[title] = rating
                for p in sets["directors"]:
                    self.person_w[p] += 0.8 * w
                    self.person_src[p].append("created " + title)
            else:
                self.dislikes.append({"title": title, "rating": rating, "sets": sets, "w": 1.0})
                for p in sets["directors"]:
                    self.person_w[p] -= 0.4

    def _soft_signals(self):
        """Thumbs-up = a light seed; thumbs-down / bailed = half a dislike. Never ratings (the ledger keeps them apart)."""
        def feats(d):
            try:
                return self.tmdb.details(d["type"] if d.get("type") in ("movie", "tv") else "movie", int(d["tmdb"]), STATIC_TTL_D)
            except Exception:
                return None
        n_up = n_soft = 0
        for d in self.signals.get("thumbs_up") or []:
            f = feats(d)
            if not f:
                continue
            sets = feature_sets(f)
            title = f.get("title") or d.get("title") or ""
            self.seeds.append({"title": title, "rating": "thumb", "weight": THUMB_UP_W, "sets": sets,
                               "kind": f.get("kind") or "movie"})
            self.seed_rating.setdefault(title, "thumbs-up")
            for p in sets["directors"]:
                self.person_w[p] += 1.0 * THUMB_UP_W
                self.person_src[p].append("directed " + title)
            for p in sets["cast"]:
                self.person_w[p] += 0.4 * THUMB_UP_W
            n_up += 1
        for d in (self.signals.get("thumbs_down") or []) + (self.signals.get("bailed") or []):
            f = feats(d)
            if not f:
                continue
            sets = feature_sets(f)
            self.dislikes.append({"title": f.get("title") or d.get("title") or "", "rating": "soft", "sets": sets,
                                  "w": SOFT_DISLIKE_W})
            for p in sets["directors"]:
                self.person_w[p] -= 0.6 * SOFT_DISLIKE_W
            for p in sets["cast"]:
                self.person_w[p] -= 0.2 * SOFT_DISLIKE_W
            n_soft += 1
        if n_up or n_soft:
            self.log("taste loop signals: %d thumbs-up seeds, %d soft dislikes, %d blocked titles"
                     % (n_up, n_soft, len(self.blocked)))

    # ---------------------------------------------------------------------------------------------- hard rules
    def excluded(self, f, enforce_floor=True):
        """Reason string if a candidate breaks a hard taste rule, else None."""
        if f.get("id") is not None and self.blocked:
            why = self.blocked.get("%s:%s" % ("tv" if f.get("kind") == "tv" else "movie", f.get("id")))
            if why:
                return why
        g = set(norm_genres(f.get("genres")))
        if g & KIDS:
            return "kids/family lane"
        if "Animation" in g and not self.animation_ok:
            return "animation lane closed"
        bad = (g & NONFICTION) - self.nonfiction_ok
        if bad:
            return "non-fiction (%s)" % ",".join(sorted(bad))
        if enforce_floor and f.get("kind") == "movie" and (f.get("year") or 0) < YEAR_FLOOR:
            return "pre-1987"
        return None

    # --------------------------------------------------------------------------------------------------- score
    def score(self, f, heat=None):
        """(match 0-1, because[list of seed titles], people[list], parts{}) for one candidate's TMDB features."""
        cs = feature_sets(f)
        # Similarity is driven by WHAT the film is about (TMDB keywords) and WHO made it; genre overlap only scales
        # it. Measured 2026-10-26: with genre overlap as an additive term, 403 loved seeds meant every pure Drama
        # "matched" some pure-Drama favourite at 1.0 and the list filled with generic dramas because of The Help.
        sims = []
        for s in self.seeds:
            ss = s["sets"]
            ppl = 1.0 if (cs["directors"] & ss["directors"]) else (0.6 if len(cs["cast"] & ss["cast"]) else 0.0)
            sim = (0.70 * jaccard(cs["keywords"], ss["keywords"]) + 0.30 * ppl) * \
                  (0.4 + 0.6 * jaccard(cs["genres"], ss["genres"]))
            if s["kind"] != f.get("kind"):
                sim *= 0.85                                          # cross-medium similarity counts a bit less
            sims.append((sim * (0.5 + 0.5 * s["weight"]), sim, s["title"], ppl))
        sims.sort(key=lambda x: -x[0])
        top = sims[:3]
        sim_raw = sum(x[0] for x in top) / max(1, len(top))
        dis = 0.0
        for d in self.dislikes:
            ds = d["sets"]
            dis = max(dis, d.get("w", 1.0) * 0.70 * jaccard(cs["keywords"], ds["keywords"]) *
                      (0.4 + 0.6 * jaccard(cs["genres"], ds["genres"])))
        sim_n = max(0.0, min(1.0, (sim_raw - 0.5 * dis) / SIM_SCALE))

        gws = sorted((self.genre_w.get(g, 0.0) for g in cs["genres"]), reverse=True)[:3]
        genre_n = (sum(gws) / len(gws) + 1.0) / 2.0 if gws else 0.4

        pw = 0.0
        hit = []
        for p in cs["directors"]:
            v = self.person_w.get(p, 0.0)
            pw += v
            if v >= 0.5:
                hit.append(p)
        for p in cs["cast"]:
            v = 0.5 * self.person_w.get(p, 0.0)
            pw += v
            if v >= 0.4:
                hit.append(p)
        people_n = 1.0 - math.exp(-max(0.0, pw) / 1.5)

        # Bayesian-weighted quality: 8.9 over 900 fan votes is not better than 8.1 over 9,000 (IMDb's top-list method).
        v, r = float(f.get("vote_count") or 0), float(f.get("vote_average") or 0.0)
        bayes = (v * r + QUALITY_M * QUALITY_C) / (v + QUALITY_M) if v + QUALITY_M > 0 else QUALITY_C
        quality_n = max(0.0, min(1.0, (bayes - 6.3) / 1.7))
        match = 0.42 * sim_n + 0.23 * genre_n + 0.20 * people_n + 0.15 * quality_n
        match *= self.lang_factor(f.get("original_language"))
        boost = 0.0
        if heat:
            boost = max([heat.get(g, 0.0) for g in cs["genres"]] + [0.0])
            match *= 1.0 + 0.15 * max(0.0, min(1.0, boost / 0.3))
        match = round(max(0.0, min(1.0, match)), 3)

        because = []
        for w, sim, title, ppl in sorted(sims, key=lambda x: (-(x[3] > 0), -x[0]))[:6]:
            if sim >= 0.025 and title not in because:
                because.append(title)
            if len(because) == 3:
                break
        if not because:
            because = [t for _, sim, t, _ in top if sim > 0.012][:2]
        hit = list(dict.fromkeys(hit))
        return match, because, hit[:3], {"sim": round(sim_n, 3), "genre": round(genre_n, 3),
                                         "people": round(people_n, 3), "quality": round(quality_n, 3),
                                         "heat": round(boost, 3)}

    def lang_factor(self, lang):
        """His ratings are his language habit too: a language he has rated many films in costs nothing, a language
        he has (almost) never rated costs up to 25%. Derived from the ratings, never a hard filter."""
        if not lang or not self.lang_share:
            return 1.0
        return 0.75 + 0.25 * min(1.0, self.lang_share.get(lang, 0.0) / 0.10)

    def heat_map(self):
        """taste-velocity rising genres (positive deltas only, kids lanes ignored) for page 1's mild multiplier."""
        tv = bc.read_json(os.path.join(bc.DATA, "taste-velocity.json"))
        out = {}
        try:
            for r in tv["data"]["genres"]:
                if r["delta"] > 0 and r["genre"] not in KIDS and r["genre"] != "Animation":
                    out[r["genre"]] = float(r["delta"])
        except Exception:
            self.notes.append("taste-velocity unreadable - no heat multiplier")
        return out


# ------------------------------------------------------------------------------------------------ exclusions
def owned_sets():
    """({radarr tmdb ids}, {sonarr tvdb ids}, {sonarr tmdb ids}, {radarr tmdb -> movie}, {sonarr tvdb -> series}).
    Raises if either *arr is unreachable: without the owned set a page would propose the library back to him."""
    movies = arr_get(RADARR, "radarr", "/movie")
    series = arr_get(SONARR, "sonarr", "/series")
    if not movies or not series:
        raise RuntimeError("Radarr or Sonarr returned an empty library")
    m_tmdb = {int(m["tmdbId"]) for m in movies if m.get("tmdbId")}
    s_tvdb = {int(s["tvdbId"]) for s in series if s.get("tvdbId")}
    s_tmdb = {int(s["tmdbId"]) for s in series if s.get("tmdbId")}
    return m_tmdb, s_tvdb, s_tmdb, {int(m["tmdbId"]): m for m in movies if m.get("tmdbId")}, \
        {int(s["tvdbId"]): s for s in series if s.get("tvdbId")}


def watched_titles(token=None):
    """Normalized titles of everything Plex remembers being played (the taste_velocity method, NOT Tautulli -
    Tautulli's history only reaches back to 2026-06). Episodes count as their series title."""
    import xml.etree.ElementTree as ET
    token = token or plex_token()
    out, start = set(), 0
    while start < 40000:
        url = ("%s/status/sessions/history/all?X-Plex-Token=%s&sort=viewedAt:desc"
               "&X-Plex-Container-Start=%d&X-Plex-Container-Size=1000" % (PLEX, token, start))
        root = ET.fromstring(urllib.request.urlopen(url, timeout=120).read())
        vids = [v for v in root if v.tag in ("Video", "Track")]
        if not vids:
            break
        for v in vids:
            t = v.get("grandparentTitle") if v.get("type") == "episode" else v.get("title")
            if t:
                out.add(norm_title(t))
        start += len(vids)
        if len(vids) < 1000:
            break
    return out


def current_ids(contract):
    """tmdb ids already listed in another page's CURRENT contract (cross-page dedupe)."""
    env = bc.read_json(os.path.join(bc.DATA, contract + ".json"))
    ids = set()
    try:
        d = env["data"]
        rows = d.get("items") or (d.get("landed") or []) + (d.get("gems") or [])
        for r in rows:
            if r.get("tmdb_id"):
                ids.add((r.get("type"), int(r["tmdb_id"])))
    except Exception:
        pass
    return ids


def to_ascii(s):
    fix = {u"\u2018": "'", u"\u2019": "'", u"\u201c": '"', u"\u201d": '"', u"\u2013": "-", u"\u2014": " - ",
           u"\u2026": "...", u"\u00a0": " "}
    for a, b in fix.items():
        s = s.replace(a, b)
    return s


def clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 3].rsplit(" ", 1)[0] + "..."
