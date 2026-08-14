#!/usr/bin/env python3
# taste_velocity.py - I7 Taste Velocity: what is HEATING UP and what is COOLING OFF in this household's taste.
# Per-genre share of plays in the rolling last 90 days vs the same share over the whole play history.
# delta = recent_share - lifetime_share. Positive = heating, negative = cooling.
#
# WHY WATCH HISTORY AND NOT RATINGS (the honest signal):
#   The gameplan wording is "rolling-90d vs lifetime deltas per genre/lane". The obvious input would be the Trakt
#   ratings in wg\audit\trakt-ratings.json - but that file is a FROZEN SNAPSHOT (the Trakt API is dead and is never
#   called from this box). A frozen file cannot produce a moving delta: every week it would report the exact same
#   "velocity", which is a plausible-looking lie. The one input that genuinely moves is WATCH BEHAVIOUR, so that is
#   what this measures.
#
# WHY PLEX HISTORY AND NOT TAUTULLI (deviation from the rhythm_map.py template, on purpose):
#   rhythm_map.py reads Tautulli (127.0.0.1:8181, key wg\tautulli.key) because it only ever looks at a 90-day
#   window. This producer needs a LIFETIME baseline, and Tautulli's database on this box only reaches back to
#   2026-06-18 - its entire history sits INSIDE the 90-day window, so "lifetime share" would equal "recent share"
#   and every delta would be a hard zero. Plex's own history endpoint holds ~5.3k plays back to 2024-01, so the
#   baseline is real. Same data-access shape as wg\audit\taste-graph.ps1: /status/sessions/history/all paged, with
#   the PlexOnlineToken read out of HKCU (winreg, stdlib).
#
# GENRES: a play names a title, not genres. taste-graph.ps1 solved this with a title -> genres map built from the
#   live Radarr movie list + Sonarr series list; episode plays map through their series (grandparentTitle). Reused
#   here, plus a small improvement: Plex sometimes disambiguates with a trailing "(2021)", so an exact miss retries
#   against a year-stripped key. Titles that still do not map (home videos, deleted-from-*arr kid shows) are
#   COUNTED and REPORTED in the note, never silently dropped.
#
# ONE HOUSEHOLD, ONE ACCOUNT: the kids' viewing blends into the same Plex account, so there is no per-user split to
#   strip it out with (see note emitted with the data). taste-graph.ps1 guesses a persona from genre + hour, but
#   that logic is circular HERE - classifying a play as "kids" because it is Animation and then measuring the
#   Animation share would manufacture the answer. So this counts every household play and says so, loudly.
#
# HONEST EXIT (guardrail 5 - never a plausible-looking lie):
#   * history unreachable / unparseable, or no genre map at all -> print CANNOT TELL, exit 2, write NOTHING.
#   * fewer than MIN_RECENT genre-mapped plays in the window -> CANNOT TELL, exit 2, write NOTHING (a "velocity"
#     over 4 plays is noise wearing a percentage sign). The previous contract then ages into a STALE badge, true.
#   * between MIN_RECENT and THIN_RECENT plays -> still emitted, but the note says the sample is thin.
#   * any other failure -> exit 1, write nothing.
#
# Standalone producer, weekly task "Taste Velocity" Sunday 07:05 (pythonw.exe - no console flash, exit code still
# reaches the task-health watchdog).
import json, os, re, sys, time, urllib.request, collections, xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
WINDOW_DAYS = 90
TOP_N = 14
MIN_GENRE_LIFETIME = 5      # a genre seen fewer times than this over ALL history is noise, not a lane
MIN_RECENT = 5              # below this: refuse to report
THIN_RECENT = 20            # below this: report, but say the sample is thin
PAGE = 1000
HARD_CAP = 40000            # paging guard - never loop forever against a misbehaving endpoint

PLEX = "http://127.0.0.1:32400"
RADARR = "http://127.0.0.1:7878/api/v3/movie"
SONARR = "http://127.0.0.1:8989/api/v3/series"

YEAR_SUFFIX = re.compile(r"\s*\((?:19|20)\d\d\)$")


def norm(title):
    """Match key for a title. Lowercased, trimmed, trailing '(1999)' disambiguator removed."""
    t = (title or "").strip().lower()
    return YEAR_SUFFIX.sub("", t)


def plex_token():
    """The server's own token, same source taste-graph.ps1 uses. winreg is stdlib; HKCU needs the user session."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Plex, Inc.\Plex Media Server") as k:
        return winreg.QueryValueEx(k, "PlexOnlineToken")[0]


def api_key(name):
    with open(os.path.join(WG, name + ".key"), encoding="utf-8-sig") as fh:
        return fh.read().strip()


def arr_genres(url, keyname, genre_of):
    """Fold one *arr library into the title -> genres map. Returns how many rows it contributed (0 = it failed)."""
    try:
        req = urllib.request.Request(url, headers={"X-Api-Key": api_key(keyname)})
        rows = json.load(urllib.request.urlopen(req, timeout=180))
    except Exception as ex:
        print("WARN: %s genre source unavailable (%s: %s) - titles from it will not map"
              % (keyname, type(ex).__name__, ex))
        return 0
    n = 0
    for r in rows:
        t = r.get("title")
        g = [x for x in (r.get("genres") or []) if isinstance(x, str) and x.strip()]
        if t and g:
            genre_of.setdefault(norm(t), g)
            n += 1
    return n


def plex_history(token):
    """Every play Plex still remembers, newest first. Returns [(title, viewedAt, accountID), ...]."""
    out, start = [], 0
    while start < HARD_CAP:
        url = ("%s/status/sessions/history/all?X-Plex-Token=%s&sort=viewedAt:desc"
               "&X-Plex-Container-Start=%d&X-Plex-Container-Size=%d" % (PLEX, token, start, PAGE))
        root = ET.fromstring(urllib.request.urlopen(url, timeout=120).read())
        vids = [v for v in root if v.tag in ("Video", "Track")]
        if not vids:
            break
        for v in vids:
            title = v.get("grandparentTitle") if v.get("type") == "episode" else v.get("title")
            try:
                seen = int(v.get("viewedAt"))
            except (TypeError, ValueError):
                continue                                   # undateable play - cannot bucket it, so drop it
            if title:
                out.append((title, seen, v.get("accountID") or "?"))
        start += len(vids)
        if len(vids) < PAGE:
            break
    return out


def main():
    try:
        token = plex_token()
    except Exception as ex:
        print("CANNOT TELL: no Plex token in HKCU (%s: %s) - is this running in bobdo's session?"
              " Writing nothing." % (type(ex).__name__, ex))
        return 2

    genre_of = {}
    n_movies = arr_genres(RADARR, "radarr", genre_of)
    n_series = arr_genres(SONARR, "sonarr", genre_of)
    if not genre_of:
        print("CANNOT TELL: neither Radarr nor Sonarr answered, so no play can be mapped to a genre."
              " Writing nothing.")
        return 2

    try:
        plays = plex_history(token)
    except Exception as ex:
        print("CANNOT TELL: Plex history unreadable (%s: %s). Writing nothing." % (type(ex).__name__, ex))
        return 2
    if not plays:
        print("CANNOT TELL: Plex returned no play history at all. Writing nothing.")
        return 2

    cutoff = time.time() - WINDOW_DAYS * 86400
    life_g, rec_g = collections.Counter(), collections.Counter()
    life_n = rec_n = life_unmapped = rec_unmapped = 0
    accounts = collections.Counter()
    oldest = min(p[1] for p in plays)

    for title, seen, acct in plays:
        recent = seen >= cutoff
        accounts[acct] += 1
        genres = genre_of.get(norm(title))
        if not genres:
            life_unmapped += 1
            rec_unmapped += 1 if recent else 0
            continue
        life_n += 1
        for g in set(genres):
            life_g[g] += 1
        if recent:
            rec_n += 1
            for g in set(genres):
                rec_g[g] += 1

    if rec_n < MIN_RECENT:
        print("CANNOT TELL: only %d genre-mapped plays in the last %d days (need %d) - there is no velocity to"
              " measure, just noise. Writing nothing." % (rec_n, WINDOW_DAYS, MIN_RECENT))
        return 2
    if life_n == 0:
        print("CANNOT TELL: no play in the whole history mapped to a genre. Writing nothing.")
        return 2

    rows = []
    for g, n in life_g.items():
        if n < MIN_GENRE_LIFETIME:
            continue                                       # too rare to have a trend
        rs = round(rec_g[g] / float(rec_n), 3)
        ls = round(n / float(life_n), 3)
        rows.append({"genre": g, "recent_share": rs, "lifetime_share": ls, "delta": round(rs - ls, 3)})
    rows.sort(key=lambda r: (-abs(r["delta"]), -r["recent_share"], r["genre"]))
    rows = rows[:TOP_N]

    # --- the note carries every caveat a reader needs to not over-trust these numbers ---
    top_acct, top_n = accounts.most_common(1)[0]
    shared = top_n >= 0.95 * len(plays)
    bits = []
    if rec_n < THIN_RECENT:
        bits.append("THIN SAMPLE: only %d genre-mapped plays in the last %d days, so these deltas are a hint,"
                    " not a trend - one long weekend of one genre would move them." % (rec_n, WINDOW_DAYS))
    if shared:
        bits.append("ALL household plays are counted, kids included: %d of %d plays sit on the single shared Plex"
                    " account, so no per-user split exists to strip the kids' viewing out with. Animation, Family"
                    " and Children movement here is the household's, not michael's alone." % (top_n, len(plays)))
    else:
        bits.append("Plays span %d Plex accounts but are pooled here - no account is labelled as a kid account,"
                    " so a per-user split would be a guess. Kids' viewing is included." % len(accounts))
    bits.append("Lifetime baseline = %d genre-mapped plays back to %s; episodes count individually, so a"
                " binged series moves a genre far more than a single film does."
                % (life_n, time.strftime("%Y-%m-%d", time.localtime(oldest))))
    bits.append("Shares are the fraction of plays carrying that genre (a title has several, so shares do not sum"
                " to 1). Genres with fewer than %d lifetime plays are dropped as noise." % MIN_GENRE_LIFETIME)
    if life_unmapped:
        bits.append("%d lifetime / %d recent plays had no title match in Radarr (%d) or Sonarr (%d) and are"
                    " excluded - home videos and shows since removed from the *arrs."
                    % (life_unmapped, rec_unmapped, n_movies, n_series))
    note = " ".join(bits)

    data = {
        "window_days": WINDOW_DAYS,
        "plays_recent": rec_n,
        "plays_lifetime": life_n,
        "genres": rows,
        "note": note,
    }
    path = bc.write_contract("taste-velocity", data)

    up = [r for r in rows if r["delta"] > 0]
    down = [r for r in rows if r["delta"] < 0]
    print("taste-velocity written: %s (%d recent / %d lifetime genre-mapped plays over %dd; %d genres, %d heating,"
          " %d cooling)" % (path, rec_n, life_n, WINDOW_DAYS, len(rows), len(up), len(down)))
    print("%-18s %8s %8s %8s" % ("GENRE", "90D", "LIFE", "DELTA"))
    for r in rows[:8]:
        print("%-18s %7.1f%% %7.1f%% %+8.1f%%  %s"
              % (r["genre"][:18], 100 * r["recent_share"], 100 * r["lifetime_share"], 100 * r["delta"],
                 "HEATING" if r["delta"] > 0 else ("cooling" if r["delta"] < 0 else "flat")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
