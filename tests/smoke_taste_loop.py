# smoke_taste_loop.py - verify-brain check 7 "taste-loop" (wg\GAMEPLAN-TASTE-LOOP-2026-11.md, V-suite). Read-only
# live checks that the loop is intact. Exit 0 = PASS, 2 = WARN (stale / degraded-on-purpose / model regressed),
# 1 = FAIL. Prints one summary line last (verify-brain shows it) after one line per check.
import hashlib, json, os, sys, time

WG = r"C:\Users\bobdo\wg"
sys.path.insert(0, os.path.join(WG, "brain", "producers"))
BASE_SHA256 = "c0b985d38f0f6fee6865dad5ddc90ea90f46e5a06904076c6eee5fc648ae18ff"   # recorded in T0, 2026-11-02
fails, warns, oks = [], [], []


def chk(name, ok, detail, warn_only=False):
    (oks if ok else (warns if warn_only else fails)).append("%s: %s" % (name, detail))
    print("%-5s %s - %s" % ("ok" if ok else ("WARN" if warn_only else "FAIL"), name, detail))


def read(p):
    with open(p, encoding="utf-8-sig") as fh:
        return json.load(fh)


try:
    import taste_ledger as tl
    import taste_core as tc
    sha = hashlib.sha256(open(tl.P("base"), "rb").read()).hexdigest()
    chk("base-untouched", sha == BASE_SHA256, "trakt-ratings.json sha256 %s" % sha[:12])
    off = tl.is_off()
    events, bad = tl.read_events()
    chk("ledger-parse", bad == 0, "%d events, %d bad lines" % (len(events), bad))
    eff = read(tl.P("effective"))
    chk("effective", isinstance(eff, list) and len(eff) >= 488, "%d effective ratings" % len(eff))
    rows, src, _ = tc.ratings_source()
    chk("taste-source", src == "ratings-effective" or off, "taste_core reads %s%s" % (src, " (loop OFF by flag)" if off else ""),
        warn_only=off)
    tl_env = read(os.path.join(WG, "brain", "data", "taste-ledger.json"))
    deg = tl_env["data"]["degraded"]
    chk("taste-ledger", not deg, "degraded=%s %s" % (deg, tl_env["data"]["reason"]), warn_only=off)
    rq = read(os.path.join(WG, "brain", "data", "rate-queue.json"))
    age_h = (time.time() - tl.epoch(rq["_meta"]["generated_at"])) / 3600.0
    chk("rate-queue", age_h < 48, "%d items, full rebuild %.1f h ago" % (len(rq["data"]["items"]), age_h), warn_only=True)
    ev = read(tl.P("eval"))
    chk("eval", not ev.get("regressed"), "rho %s (baseline %s)%s" % ((ev.get("current") or {}).get("rho"),
        (ev.get("baseline") or {}).get("rho"), " - REGRESSED" if ev.get("regressed") else ""), warn_only=True)
    sys.path.insert(0, os.path.join(WG, "dashboard"))
    import taste_verbs  # noqa: F401
    chk("verbs-module", True, "taste_verbs imports")
except Exception as ex:
    chk("smoke", False, "%s: %s" % (type(ex).__name__, ex))

rc = 1 if fails else (2 if warns else 0)
print("taste-loop: %d ok, %d warn, %d fail%s" % (len(oks), len(warns), len(fails),
      (" | " + " ; ".join(fails + warns)) if (fails or warns) else ""))
sys.exit(rc)
