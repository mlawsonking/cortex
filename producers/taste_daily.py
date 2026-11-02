# taste_daily.py - the taste loop's daily chain (task "Rate Queue", 05:40, before the morning surfaces):
#   1. taste_ledger.py  ingest Plex ratings made with the remote + compile ratings-effective / taste-signals
#   2. taste_eval.py    holdout accuracy + the guess calibration (a weekly history point when due)
#   3. rate_queue.py    full rescore of the rate queue (leverage, household filter, guesses)
#   4. plex_rows.py     sync the four Plex home-screen collections (Missed Gems / Streaming Best: On Your Shelf)
# Every step runs even if an earlier one failed (each falls back honestly on its own); the process exit code is the
# WORST step code, so the task-health watchdog sees any failure. One log line per step -> wg\audit\taste-daily.log.
import os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = r"C:\Users\bobdo\wg\audit\taste-daily.log"
PY = os.path.join(os.path.dirname(sys.executable), "python.exe")
STEPS = ["taste_ledger.py", "taste_eval.py", "rate_queue.py", "plex_rows.py"]


def main():
    worst = 0
    lines = []
    for s in STEPS:
        t0 = time.time()
        try:
            p = subprocess.run([PY if os.path.exists(PY) else sys.executable, os.path.join(HERE, s)], cwd=HERE,
                               capture_output=True, text=True, timeout=1500, creationflags=0x08000000)
            rc, tail = p.returncode, ((p.stdout or "") + (p.stderr or "")).strip().splitlines()[-1:] or [""]
        except Exception as ex:
            rc, tail = 1, ["%s: %s" % (type(ex).__name__, ex)]
        worst = rc if rc and (worst == 0 or rc == 1) else worst
        lines.append("%s %s rc=%d %.0fs %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), s, rc, time.time() - t0, tail[0][:220]))
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except Exception:
        pass
    print("\n".join(lines))
    return worst


if __name__ == "__main__":
    sys.exit(main())
