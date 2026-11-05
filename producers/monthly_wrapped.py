#!/usr/bin/env python3
# monthly_wrapped.py - I9 Monthly Wrapped: a warm, plain-text monthly brief over what the OTHER insight engines
# already measured. It invents nothing: it compiles a compact ASCII facts digest from the existing contracts in
# wg\brain\data\ and asks claude -p to narrate THAT digest and only that digest.
#
# READ-ONLY CONTRACT, NO VERBS (per the gameplan: "None - reading pleasure"). Nothing here touches Radarr, qBit,
# Plex or the disks. It reads local JSON and writes one contract file.
#
# SUBSCRIPTION ONLY - HOUSE RULE. The narrative comes from `claude -p` (the Claude Code SUBSCRIPTION binary at
# C:\Users\bobdo\.local\bin\claude.exe, full path because a scheduled task does not share the shell PATH).
# There is NO ANTHROPIC_API_KEY here and there must never be one: this producer must never become metered.
# Exactly ONE claude call per run, and the run happens at most about once a month (see the self-gate).
#
# HONEST FAILURE (guardrail 5): if claude is missing / times out / errors / returns empty, this exits NONZERO and
# writes NOTHING. There is deliberately no deterministic fallback narrative - a Wrapped without the model is not
# a Wrapped, and a hand-rolled paragraph claiming to be one would be exactly the plausible-looking lie this repo
# exists to kill. The card's stale/missing badge is the honest signal.
#
# SELF-GATING MONTHLY SEMANTICS (why the scheduled task is DAILY):
#   Windows monthly triggers have no clean New-ScheduledTaskTrigger cmdlet form (they need a raw CIM
#   MSFT_TaskMonthlyTrigger or schtasks /SC MONTHLY), so task "Monthly Wrapped" fires DAILY at 07:15 and the
#   monthly cadence lives HERE. A run regenerates only if:
#       * data\wrapped.json is missing or unparseable                        (first run / recovery), OR
#       * its data.month != the current YYYY-MM                              (a new month began - i.e. the 1st), OR
#       * its _meta.generated_at is older than 27 days                       (aging toward the 35-day SLO).
#   Any other day it prints why it is skipping and exits 0 WITHOUT rewriting (no wasted claude call, and the
#   contract keeps its true generated_at). The month-changed test is the "today is the 1st" rule plus
#   idempotency: if the 1st's run already succeeded, a second fire that day is a no-op instead of a second call.
#
# MONTH LABEL HONESTY: the digest is made of CURRENT-STATE snapshots and rolling windows (e.g. rhythm is a
# 90-day heat map), not calendar-month aggregates. So `month` is the month the brief was PRODUCED in, and the
# prompt forbids the model from attributing a number to a specific calendar month.
#
# CONCURRENCY: a self-scoped lock file in %TEMP% keeps at most one of OUR claude calls in flight (same idea as
# wg\audit\nl-search.ps1, own lock name). A fresh lock means another wrapped run is working: exit NONZERO with
# an honest "busy" - never write a half-considered second narrative.
#
# Usage:  python monthly_wrapped.py [--force]      --force bypasses the self-gate (manual regeneration).
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

CLAUDE = r"C:\Users\bobdo\.local\bin\claude.exe"
# Phase 1a hook (2026-09-02): export the long-lived subscription token when wg\claude-oauth.token exists, so this
# scheduled run does not depend on the 8h session token (401 every morning otherwise). No-op until the file exists.
_TOKEN_FILE = r"C:\Users\bobdo\wg\claude-oauth.token"
try:
    if os.path.isfile(_TOKEN_FILE):
        _tok = open(_TOKEN_FILE, encoding="utf-8-sig").read().strip()
        if _tok:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = _tok
except Exception:
    pass
LOCK = os.path.join(tempfile.gettempdir(), "brain-wrapped-claude.lock")
LOCK_STALE_S = 420          # > the call timeout, so a crashed run's lock always clears itself
CALL_TIMEOUT_S = 180
REGEN_AFTER_DAYS = 27       # registry slo_seconds is 3024000 (35d); regenerate before that, not after
DIGEST_MAX = 3000
MIN_NARRATIVE = 200         # anything shorter than this is a degenerate answer, not a brief
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Non-ASCII the model tends to reach for -> the ASCII the console and the card actually want.
ASCII_FIX = {
    u"\u2018": "'", u"\u2019": "'", u"\u201c": '"', u"\u201d": '"',
    u"\u2013": "-", u"\u2014": " - ", u"\u2212": "-", u"\u2026": "...",
    u"\u00a0": " ", u"\u00b7": "-", u"\u2022": "-", u"\u00bd": "1/2",
}


def to_ascii(s):
    """Force plain ASCII. Formatting only - it never changes a number or a claim."""
    for bad, good in ASCII_FIX.items():
        s = s.replace(bad, good)
    return s.encode("ascii", "ignore").decode("ascii")


def load(name):
    """Return (data, age_hours) for a sibling contract, or (None, None) if absent/unreadable."""
    env = bc.read_json(os.path.join(bc.DATA, name + ".json"))
    if not isinstance(env, dict) or "data" not in env:
        return None, None
    age_h = None
    try:
        gen = env.get("_meta", {}).get("generated_at")
        age_h = (time.time() - datetime.datetime.fromisoformat(str(gen)).timestamp()) / 3600.0
    except Exception:
        age_h = None
    return env["data"], age_h


def hdr(name, age_h):
    return "[%s%s]" % (name, "" if age_h is None else " | %.0fh old" % age_h)


def titled(x):
    """'Title (Year)', or just 'Title' when the record has no year (TV season rows do not)."""
    y = x.get("year")
    return "%s (%s)" % (x.get("title", "?"), y) if y else str(x.get("title", "?"))


# --- section builders -------------------------------------------------------------------------------------
# Each returns a list of digest lines, or [] if the contract is absent. A shape surprise raises and is caught by
# the caller, which then records the contract as unavailable rather than guessing at its meaning.

def sec_rhythm():
    d, age = load("rhythm")
    if d is None:
        return []
    out = ["%s watching, last %d days: %d plays (%d movies, %d episodes)."
           % (hdr("rhythm", age), d.get("window_days", 0), d.get("total_plays", 0),
              d.get("movies", 0), d.get("episodes", 0))]
    slots = d.get("top_slots") or []
    if slots:
        out.append("  busiest slots: " + ", ".join(
            "%s %02d:00 (%d)" % (WEEKDAYS[s["weekday"] % 7], s["hour"], s["plays"]) for s in slots[:4]))
    users = d.get("users") or []
    if users:
        out.append("  by viewer: " + ", ".join("%s %d plays" % (u["user"], u["plays"]) for u in users[:3]))
    return out


def sec_ledger():
    d, age = load("ledger")
    if d is None:
        return []
    h, a, o = d.get("hevc") or {}, d.get("avc") or {}, d.get("other") or {}
    return [
        "%s compression ledger: HEVC %d files / %.0f GB, H.264 %d / %.0f GB, other %d / %.0f GB."
        % (hdr("ledger", age), h.get("count", 0), h.get("gb", 0.0), a.get("count", 0), a.get("gb", 0.0),
           o.get("count", 0), o.get("gb", 0.0)),
        "  already saved by the HEVC files you have: %.0f GB. Still reclaimable: %.0f GB across %d re-encode candidates."
        % (d.get("saved_gb", 0.0), d.get("reclaim_potential_gb", 0.0), d.get("reclaim_candidates", 0)),
    ]


def sec_hnr():
    d, age = load("hnr-horizon")
    if d is None:
        return []
    t = d.get("totals") or {}
    return ["%s seeding posture: %d private torrents below the 1.0 ratio goal, %.0f GB still owed, "
            "%d of them would never get there at their current upload rate, and %d are stuck (not seeding properly)."
            % (hdr("hnr-horizon", age), t.get("below_goal", 0), t.get("remaining_gb", 0.0),
               t.get("never_at_current_rate", 0), t.get("problems", 0))]


def sec_couple():
    d, age = load("couple-compat")
    if d is None:
        return []
    lanes = d.get("lanes") or []
    out = ["%s shared taste: %d titles in the pool, %d match her lanes."
           % (hdr("couple-compat", age), d.get("pool_total", 0), d.get("matched_any", 0))]
    if lanes:
        out.append("  lanes: " + ", ".join("%s %d" % (l.get("label", l.get("key", "?")), l.get("matches", 0))
                                           for l in lanes[:4]))
    dn = d.get("date_night") or []
    if dn:
        out.append("  top date-night pick: %s (%s)." % (dn[0].get("title", "?"), dn[0].get("year", "?")))
    return out


def sec_recs():
    d, age = load("recs")
    if not isinstance(d, list) or not d:
        return []
    return ["%s top recommendations queued for you: " % hdr("recs", age)
            + "; ".join(titled(r) for r in d[:5]) + "."]


def sec_taste():
    d, age = load("taste")
    if d is None:
        return []
    hist = {int(x["rating"]): int(x["count"]) for x in (d.get("histogram") or [])}
    top = sum(v for k, v in hist.items() if k >= 8)
    low = sum(v for k, v in hist.items() if k <= 5)
    out = ["%s ratings: %d films rated; %d scored 8+, %d scored 5 or under."
           % (hdr("taste", age), d.get("total", 0), top, low)]
    dec = d.get("decades") or []
    if dec:
        out.append("  rated by decade: " + ", ".join("%ss %d" % (x["decade"], x["count"]) for x in dec))
    return out


def sec_storage():
    d, age = load("storage")
    if d is None:
        return []
    out = []
    disks = [x for x in (d.get("disks") or []) if x.get("total")]
    if disks:
        out.append("%s disks: " % hdr("storage", age) + ", ".join(
            "%s: %.1f TB free of %.1f TB" % (x.get("letter", "?"), x.get("free", 0) / 1e12, x.get("total", 0) / 1e12)
            for x in disks))
    if d.get("forecast"):
        out.append("  capacity forecast: %s." % d["forecast"])
    p = d.get("parity") or {}
    if p:
        out.append("  SnapRAID parity: %s, last sync %.1f h ago." % (p.get("state", "?"), p.get("last_sync_age_h") or 0.0))
    return out


def sec_library():
    d, age = load("library-stats")
    if d is None:
        return []
    p, r, s = d.get("plex") or {}, d.get("radarr") or {}, d.get("sonarr") or {}
    return ["%s library: Plex holds %d movies and %d TV shows; Radarr tracks %d films (%d on disk, %d monitored "
            "and still missing, %.1f TB of files); Sonarr tracks %d series (%d monitored, %d episodes missing)."
            % (hdr("library-stats", age), p.get("movies", 0), p.get("tv", 0), r.get("total", 0), r.get("have", 0),
               r.get("monitored_missing", 0), (r.get("size_bytes") or 0) / 1e12, s.get("series", 0),
               s.get("monitored", 0), s.get("missing_episodes", 0))]


def sec_plexnow():
    d, age = load("plex-now")
    if d is None:
        return []
    rec = d.get("recent") or []
    out = ["%s Plex right now: %d active stream(s)." % (hdr("plex-now", age), len(d.get("sessions") or []))]
    if rec:
        out.append("  most recently added: " + "; ".join(titled(x) for x in rec[:5]) + ".")
    return out


SECTIONS = [
    ("rhythm", sec_rhythm),
    ("library-stats", sec_library),
    ("ledger", sec_ledger),
    ("hnr-horizon", sec_hnr),
    ("taste", sec_taste),
    ("couple-compat", sec_couple),
    ("recs", sec_recs),
    ("storage", sec_storage),
    ("plex-now", sec_plexnow),
]


def build_digest():
    """(digest_text, contracts_used). A contract that is missing or shaped unexpectedly is NAMED as absent -
    never silently dropped and never invented."""
    today = datetime.date.today()
    lines = ["MEDIA SERVER FACTS DIGEST - snapshot taken %s (all figures are current state or rolling windows)."
             % today.isoformat(), ""]
    used, absent = [], []
    body = []
    for name, fn in SECTIONS:
        try:
            got = fn()
        except Exception as ex:
            got = []
            absent.append("%s (unreadable: %s)" % (name, type(ex).__name__))
        if got:
            used.append(name)
            body.append("\n".join(got))
        elif name not in [a.split(" ")[0] for a in absent]:
            absent.append(name)

    for chunk in body:
        candidate = "\n".join(lines + [chunk])
        if len(candidate) > DIGEST_MAX - 200:
            break
        lines.append(chunk)
    if absent:
        lines.append("")
        lines.append("NO DATA AVAILABLE for: %s (say nothing about these)." % ", ".join(absent))
    # keep only the contracts that actually made it into the text
    text = to_ascii("\n".join(lines))
    used = [u for u in used if ("[%s" % u) in text]
    return text, used


def build_prompt(digest, month):
    return """You are writing the "Monthly Wrapped" brief for the owner of a private home media server
(Plex + Radarr/Sonarr + qBittorrent, run by one enthusiast for his household). Write it for %s.

Below is a FACTS DIGEST compiled from the server's own monitoring contracts. It is the ONLY source you may use.

RULES - follow every one:
- 3 to 5 paragraphs of plain prose, second person ("you"), under 320 words total.
- Separate paragraphs with a blank line. No headings, no bullets, no markdown, no code fences, no title.
- Plain ASCII only. No emoji, no curly quotes, no em dashes.
- Every number you cite must appear in the digest. Invent nothing: no titles, no dates, no percentages, no
  trends, no comparisons to a previous month (you have no previous month to compare against).
- The digest is a snapshot with rolling windows, NOT a calendar-month total. Never write that something
  happened "in %s"; describe the state and what it implies.
- If a topic is listed as having no data, do not mention it at all.
- Warm and personal but concrete - an attentive caretaker showing the owner his own month, not marketing copy.

Cover, in whatever order reads best: the watching rhythm (when and how much the household actually watches),
where his taste sits, how the library has grown and what compression has saved or could still save, and his
seeding posture on the private trackers. Close with one grounded observation, not a call to action.

FACTS DIGEST:
%s

Reply with ONLY the brief itself.""" % (month, month, digest)


def call_claude(prompt):
    """Run exactly one claude -p call and return the narrative text. Raises RuntimeError with an honest reason."""
    if not os.path.isfile(CLAUDE):
        raise RuntimeError("claude binary not found at %s" % CLAUDE)
    env = None
    for attempt in (1, 2, 3):
        try:
            # --strict-mcp-config + empty config: no user/plugin MCP servers for a headless call (2026-09-03: one
            # printed a warning line ahead of the JSON envelope on stdout)
            proc = subprocess.run([CLAUDE, "-p", "--max-turns", "1", "--output-format", "json",
                                   "--strict-mcp-config", "--mcp-config", r"C:\Users\bobdo\wg\audit\mcp-none.json"],
                                  input=prompt, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  encoding="utf-8", errors="replace", timeout=CALL_TIMEOUT_S, cwd=bc.BRAIN)
        except subprocess.TimeoutExpired:
            raise RuntimeError("claude timed out after %ds" % CALL_TIMEOUT_S)
        if proc.returncode != 0:
            raise RuntimeError("claude exited %d: %s" % (proc.returncode, (proc.stderr or "").strip()[:300]))
        try:
            # keep only the envelope line (last line starting with '{') so a stray warning line cannot break the parse
            _lines = [ln for ln in (proc.stdout or "").splitlines() if ln.lstrip().startswith("{")]
            env = json.loads(_lines[-1] if _lines else proc.stdout)
        except Exception as ex:
            raise RuntimeError("claude output was not JSON (%s): %s" % (ex, (proc.stdout or "")[:200]))
        st = env.get("api_error_status") or 0
        if attempt < 3 and (st == 429 or st >= 500):   # transient (529 Overloaded etc.): two more tries, 60s apart
            import time as _time
            _time.sleep(60)
            continue
        if st == 401 and attempt == 1:   # session token may refresh on the second call
            import time as _time
            _time.sleep(30)
            continue
        break
    # Envelope shape (verified 2026-08-14): {"type":"result","subtype":"success","is_error":false,
    #   "result":"<text>","session_id":..,"num_turns":..,"usage":{..},"total_cost_usd":..}
    if env.get("is_error") or env.get("subtype") != "success":
        raise RuntimeError("claude returned an error envelope: subtype=%r api_error_status=%r"
                           % (env.get("subtype"), env.get("api_error_status")))
    text = env.get("result")
    if not isinstance(text, str):
        raise RuntimeError("claude envelope had no string 'result' field")
    text = to_ascii(text).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    # normalise paragraph breaks to exactly one blank line (the card splits on "\n\n")
    paras = [" ".join(p.split()) for p in text.replace("\r\n", "\n").split("\n\n")]
    text = "\n\n".join(p for p in paras if p).strip()
    if len(text) < MIN_NARRATIVE:
        raise RuntimeError("claude returned only %d chars - not a brief" % len(text))
    return text


def gate(force):
    """(should_run, reason, month). See SELF-GATING MONTHLY SEMANTICS in the header."""
    month = datetime.date.today().strftime("%Y-%m")
    if force:
        return True, "--force given", month
    cur = bc.read_json(os.path.join(bc.DATA, "wrapped.json"))
    if not isinstance(cur, dict) or not isinstance(cur.get("data"), dict):
        return True, "no readable wrapped contract exists yet", month
    have = cur["data"].get("month")
    if have != month:
        return True, "existing wrapped covers %s, current month is %s" % (have, month), month
    try:
        age_d = (time.time() - datetime.datetime.fromisoformat(
            str(cur["_meta"]["generated_at"])).timestamp()) / 86400.0
    except Exception:
        return True, "existing wrapped has an unparseable generated_at", month
    if age_d > REGEN_AFTER_DAYS:
        return True, "existing wrapped is %.1f days old (> %d)" % (age_d, REGEN_AFTER_DAYS), month
    return False, "wrapped for %s already exists and is %.1f days old" % (month, age_d), month


def main():
    force = "--force" in sys.argv
    run, why, month = gate(force)
    if not run:
        print("skip (self-gate): %s - nothing rewritten" % why)
        return 0
    print("running: %s" % why)

    if os.path.isfile(LOCK):
        if (time.time() - os.path.getmtime(LOCK)) < LOCK_STALE_S:
            print("FAILED: busy - another Monthly Wrapped claude call is in flight (%s)" % LOCK)
            return 1
        os.remove(LOCK)                     # stale lock from a crashed run

    digest, used = build_digest()
    if not used:
        print("FAILED: no sibling contract data could be read - there is nothing to narrate")
        return 1
    print("digest: %d chars from %d contracts (%s)" % (len(digest), len(used), ", ".join(used)))

    try:
        with open(LOCK, "w") as fh:
            fh.write("busy %d" % os.getpid())
        narrative = call_claude(build_prompt(digest, month))
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass

    data = {"month": month, "narrative": narrative, "model_generated": True, "facts_used": used}
    path = bc.write_contract("wrapped", data)
    print("wrapped written: %s (%s, %d words, %d facts)"
          % (path, month, len(narrative.split()), len(used)))
    print("-" * 78)
    print(narrative)
    print("-" * 78)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # HONEST FAILURE: nonzero, nothing written, the reason said out loud.
        print("FAILED: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
