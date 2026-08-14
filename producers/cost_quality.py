#!/usr/bin/env python3
# cost_quality.py - I10 Cost of Quality: what each Radarr quality profile actually COSTS in disk, and what the
# real G:-fill slope is. Read-only, informs policy - this contract has no verb and never will.
#
# WHY THE SLOPE IS COMPUTED HERE AND NOT REUSED: the legacy dashboard forecast (pulse.forecast_gfull) fits a
# least-squares line over the last ~2000 raw samples, which at the ~2min metrics cadence is under 3 DAYS. That is
# why it was seen swinging "16 -> 8 months within an hour" (GAMEPLAN-BRAIN-APP.md, P2 open findings) and why the
# gameplan says not to trust it until I10 replaces it. This producer fits the SAME underlying series but:
#   * aggregates to ONE sample per day (last reading of each day) so sub-daily download/delete churn cannot
#     masquerade as a trend;
#   * fits a trailing 28-day window, so the answer describes the library as it behaves NOW;
#   * step-corrects bulk MOVES. A day that gains more than BULK_STEP_TB is not organic growth - it is a migration
#     (e.g. 2026-07-09 gained 7.8 TB when 250 movies came off D: onto G:). Left in, one such day triples the
#     slope forever. The step is subtracted from every later point and the correction is REPORTED, not hidden.
#
# HONEST DEGRADATION (three cases, and the card renders whichever is true):
#   a. metrics.db carries a usable g_used series -> real slope, forecast_source names the series and the window.
#   b. no usable series but data\storage.json exists -> carry ITS forecast through verbatim, slope stays null.
#      Never recompute a number we cannot support.
#   c. neither -> slope null, note says so plainly, per-profile costs only.
# In ALL cases we append today's G: reading to data\disk-history.jsonl, so the slope only gets better-founded.
#
# Standalone producer, weekly task "Cost of Quality" (Sun 07:10). HONEST EXIT: Radarr unreachable -> exit 1,
# write nothing. Pure stdlib, pure ASCII source.
import json, os, sys, re, time, shutil, sqlite3, datetime, urllib.request, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_contracts as bc

WG = r"C:\Users\bobdo\wg"
RADARR = "http://127.0.0.1:7878/api/v3"
METRICS_DB = os.path.join(WG, "dashboard", "metrics.db")
HISTORY = os.path.join(bc.DATA, "disk-history.jsonl")
GDRIVE = "G:\\"

WINDOW_DAYS = 28          # trailing fit window - "how the library behaves now", not how it behaved in July
MIN_DAYS = 8              # fewer daily points than this is not a trend, it is a rumour
BULK_STEP_TB = 1.0        # a single day gaining more than this is a migration, not organic growth
SANITY_MAX_AVG_GB = 200   # the 2160p profile is capped at 350 MB/min; no profile can honestly average past this
TB = 1e12
GB = 1e9


def api(path):
    with open(os.path.join(WG, "radarr.key")) as fh:
        key = fh.read().strip()
    req = urllib.request.Request(RADARR + path, headers={"X-Api-Key": key})
    return json.load(urllib.request.urlopen(req, timeout=180))


def daily_series():
    """Last g_used/g_free reading of each day from the dashboard's metrics.db. Read-only: the live dashboard
    writer owns this file, so we open it mode=ro and never hold it. Returns [] on any problem (case b/c)."""
    if not os.path.isfile(METRICS_DB):
        return []
    uri = "file:%s?mode=ro" % METRICS_DB.replace("\\", "/")
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=10)
        try:
            rows = conn.execute("SELECT ts, g_used, g_free FROM metrics "
                                "WHERE g_used IS NOT NULL ORDER BY ts").fetchall()
        finally:
            conn.close()
    except Exception:
        return []
    by_day = {}
    for ts, used, free in rows:
        by_day[datetime.date.fromtimestamp(ts)] = (float(used), free)
    return sorted(by_day.items())


def fit(series):
    """Least-squares GB/week over the trailing window, with bulk moves step-corrected out.
    Returns (slope_gb_per_week, days_used, steps_removed, first_day, last_day) or None."""
    if len(series) < MIN_DAYS:
        return None
    cutoff = series[-1][0] - datetime.timedelta(days=WINDOW_DAYS)
    win = [(d, v) for d, v in series if d >= cutoff]
    if len(win) < MIN_DAYS:
        win = series                      # young series: use everything we have rather than claim nothing
    corr = 0.0
    steps = 0
    prev = None
    xs, ys = [], []
    day0 = win[0][0]
    for d, (used, _free) in win:
        if prev is not None and (used - prev) > BULK_STEP_TB * TB:
            corr += used - prev
            steps += 1
        prev = used
        xs.append(float((d - day0).days))
        ys.append(used - corr)
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if not denom:
        return None
    slope_per_day = (n * sxy - sx * sy) / denom          # bytes/day
    return (slope_per_day * 7.0 / GB, n, steps, win[0][0], win[-1][0])


def carried_forecast():
    """Case b: the storage contract already has a forecast string. Carry it verbatim; parse a year figure out of
    it only if it is unambiguous. We never invent precision the source did not have."""
    env = bc.read_json(os.path.join(bc.DATA, "storage.json"))
    try:
        txt = (env["data"].get("forecast") or "").strip()
    except Exception:
        return None, None
    if not txt:
        return None, None
    m = re.search(r"([\d.]+)\s*(year|month)", txt)
    yrs = None
    if m:
        v = float(m.group(1))
        yrs = round(v if m.group(2) == "year" else v / 12.0, 2)
    return txt, yrs


def append_history(free_b, total_b):
    """Start/extend our own disk history. Append-only, one line per run, so the slope is computable from a series
    this repo owns even if the dashboard's metrics.db is ever rotated or lost."""
    line = json.dumps({"date": datetime.date.today().isoformat(),
                       "g_free_gb": round(free_b / GB, 1),
                       "g_total_gb": round(total_b / GB, 1)}, ensure_ascii=False)
    os.makedirs(bc.DATA, exist_ok=True)
    with open(HISTORY, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")


def main():
    movies = api("/movie")
    profiles = {p["id"]: p["name"] for p in api("/qualityprofile")}
    if not movies or not profiles:
        print("FAILED: Radarr returned %d movies / %d profiles - not credible" % (len(movies), len(profiles)))
        return 1

    films = collections.Counter()
    size = collections.Counter()
    biggest = collections.defaultdict(list)
    for m in movies:
        if not m.get("hasFile"):
            continue
        pid = m.get("qualityProfileId")
        b = m.get("sizeOnDisk") or 0
        films[pid] += 1
        size[pid] += b
        biggest[pid].append((b, m.get("title") or "?"))

    rows = []
    for pid, count in films.items():
        top = sorted(biggest[pid], reverse=True)[:3]
        rows.append({
            "profile": profiles.get(pid, "profile %s (deleted)" % pid),
            "films": count,
            "total_gb": round(size[pid] / GB, 1),
            "avg_gb": round(size[pid] / GB / count, 2),
            "biggest": [{"title": t, "gb": round(b / GB, 2)} for b, t in top],
        })
    rows.sort(key=lambda r: -r["total_gb"])

    # Sanity gate: the 2160p profile is capped at 350 MB/min, so ~40 GB is a long 4K film. An average past
    # SANITY_MAX_AVG_GB means the byte math is wrong (GiB/GB confusion, double-count) - refuse to emit.
    for r in rows:
        if r["avg_gb"] > SANITY_MAX_AVG_GB:
            print("FAILED: profile '%s' averages %.1f GB/film - byte math is wrong, refusing to emit"
                  % (r["profile"], r["avg_gb"]))
            return 1

    usage = shutil.disk_usage(GDRIVE)
    append_history(usage.free, usage.total)

    series = daily_series()
    f = fit(series)
    if f:
        case = "a"
        slope, ndays, steps, d0, d1 = f
        forecast_source = ("metrics.db metrics(ts,g_used) daily last-sample, least-squares over %s..%s "
                           "(%d daily points, %d-day window)" % (d0.isoformat(), d1.isoformat(), ndays, WINDOW_DAYS))
        if slope > 0:
            years = round(usage.free / GB / slope / 52.18, 2)
            note = "G: grows about %.0f GB/week at the current rate, so ~%.1f years of headroom." % (slope, years)
        else:
            years = None
            note = "G: usage is flat or shrinking over this window, so no fill date can honestly be projected."
        if steps:
            note += (" %d bulk-move day(s) inside the window were step-corrected out (a day gaining over %.0f TB "
                     "is a migration, not organic growth)." % (steps, BULK_STEP_TB))
        carried, _ = carried_forecast()
        if carried:
            note += " The legacy dashboard forecast currently reads '%s' - it fits under 3 days of raw samples." % carried
    else:
        carried, years = carried_forecast()
        if carried:
            case = "b"
            slope = None
            forecast_source = "storage contract"
            note = ("No usable disk history here, so the storage contract's own forecast is carried through "
                    "verbatim: '%s'. Not recomputed." % carried)
        else:
            case = "c"
            slope = None
            years = None
            forecast_source = "none"
            note = "no history series exists - per-profile costs only"
        note += " data\\disk-history.jsonl is now being appended each run so a real slope becomes computable."

    data = {
        "profiles": rows,
        "movies_total_gb": round(sum(size.values()) / GB, 1),
        "g_free_gb": round(usage.free / GB, 1),
        "g_total_gb": round(usage.total / GB, 1),
        "slope_gb_per_week": None if slope is None else round(slope, 1),
        "full_in_years": years,
        "forecast_source": forecast_source,
        "note": note,
    }
    path = bc.write_contract("cost-of-quality", data)
    print("cost-of-quality written: %s" % path)
    print("  case %s | %d profiles | %d films | %.1f GB of movies | G: %.1f TB free of %.1f TB"
          % (case, len(rows), sum(films.values()), data["movies_total_gb"],
             usage.free / TB, usage.total / TB))
    for r in rows:
        print("  %-22s %5d films %9.1f GB  avg %6.2f GB  biggest %s"
              % (r["profile"][:22], r["films"], r["total_gb"], r["avg_gb"],
                 r["biggest"][0]["title"][:34] if r["biggest"] else "-"))
    print("  slope %s GB/week | full in %s years | source: %s"
          % (data["slope_gb_per_week"], data["full_in_years"], forecast_source))
    print("  note: %s" % note)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
