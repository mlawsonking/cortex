# taste_eval.py - proof the nucleus learns (wg\GAMEPLAN-TASTE-LOOP-2026-11.md s7). A FIXED holdout (every explicit
# movie rating whose sha1(tmdb id) % 5 == 0 - stable as ratings grow, new ratings join it at the same 20% rate) is
# scored by a taste_core profile built from the OTHER 80%. Reports Spearman rho(match, rating), top-quintile
# precision (share of the predicted-top 20% he rated 8+), and a match -> rating calibration table that the rate
# queue uses for its hidden "Cortex guessed" number (+ the MAE of that guess on the holdout). The live MAE comes from
# the rate verb's own guesses (ledger events carry the guess shown to - and hidden from - michael until he rated).
# TMDB cache only in practice (rated films are cached 180 d). Writes wg\audit\taste-eval.json; the taste-ledger
# contract republishes it. A weekly history point is appended when the last is >= 6 days old (or --point).
# A rho drop > 0.05 from the previous point sets regressed=true (daily-audit WARN) - nothing is auto-reverted.
import argparse, hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brain_contracts as bc
import taste_core as tc
import taste_ledger as tl

REGRESS_DROP = 0.05
BINS = 5


def in_holdout(tmdb):
    return int(hashlib.sha1(str(int(tmdb)).encode("ascii")).hexdigest(), 16) % 5 == 0


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = ranks(a), ranks(b)
    n = float(len(a))
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return round(cov / (va * vb), 4) if va and vb else None


def calibrate(pairs):
    """pairs [(match, rating)] -> [[match_mid, mean_rating], ...] over BINS quantile bins, monotone non-decreasing."""
    pairs = sorted(pairs)
    if len(pairs) < BINS * 3:
        return []
    out = []
    for b in range(BINS):
        chunk = pairs[b * len(pairs) // BINS:(b + 1) * len(pairs) // BINS]
        out.append([round(sum(m for m, _ in chunk) / len(chunk), 4), round(sum(r for _, r in chunk) / len(chunk), 3)])
    for i in range(1, len(out)):                      # pool adjacent violators (keep it monotone)
        if out[i][1] < out[i - 1][1]:
            avg = round((out[i][1] + out[i - 1][1]) / 2.0, 3)
            out[i][1] = out[i - 1][1] = avg
    return out


def guess_from(table, match):
    """Interpolate a 1-10 integer guess from the calibration table (clamped at the ends)."""
    if not table:
        return None
    if match <= table[0][0]:
        v = table[0][1]
    elif match >= table[-1][0]:
        v = table[-1][1]
    else:
        v = table[-1][1]
        for (m0, r0), (m1, r1) in zip(table, table[1:]):
            if m0 <= match <= m1:
                v = r0 + (r1 - r0) * ((match - m0) / (m1 - m0) if m1 > m0 else 0.0)
                break
    return int(max(1, min(10, round(v))))


def live_mae(events, n=30):
    void = tl.voided_ids(events)
    xs = [abs(int(e["value"]) - int(e["guess"])) for e in events
          if e.get("kind") == "rating" and e.get("src") == "dash" and e["id"] not in void
          and isinstance(e.get("guess"), int) and isinstance(e.get("value"), int)]
    xs = xs[-n:]
    return (round(sum(xs) / float(len(xs)), 2), len(xs)) if xs else (None, 0)


def evaluate(log=print):
    rows, source, _ = tc.ratings_source()
    movies = [r for r in rows if r.get("type", "movie") == "movie" and (r.get("movie") or {}).get("ids", {}).get("tmdb")]
    hold = [r for r in movies if in_holdout(r["movie"]["ids"]["tmdb"])]
    train = [r for r in rows if r not in hold]
    t = tc.Taste(log=lambda *a: None).build(tc.api_key("tmdb"), rows=train)
    pairs = []
    for r in hold:
        try:
            f = t.tmdb.details("movie", int(r["movie"]["ids"]["tmdb"]), tc.STATIC_TTL_D)
        except Exception:
            continue
        pairs.append((t.score(f)[0], float(r["rating"])))
    ms, rs = [p[0] for p in pairs], [p[1] for p in pairs]
    rho = spearman(ms, rs)
    top = sorted(pairs, reverse=True)[:max(1, len(pairs) // 5)]
    p_top = round(sum(1 for _, r in top if r >= tc.LOVE) / float(len(top)), 4) if top else None
    table = calibrate(pairs)
    mae = round(sum(abs(guess_from(table, m) - r) for m, r in pairs) / float(len(pairs)), 3) if table and pairs else None
    base_love = round(sum(1 for r in rs if r >= tc.LOVE) / float(len(rs)), 4) if rs else None
    log("eval (%s): train %d, holdout %d scored, rho %s, top-quintile precision %s (holdout base rate %s), guess MAE %s"
        % (source, len(train), len(pairs), rho, p_top, base_love, mae))
    return {"date": time.strftime("%Y-%m-%d"), "rho": rho, "p_top": p_top, "base_love_rate": base_love, "mae": mae,
            "n_train": len(train), "n_holdout": len(pairs), "source": source}, table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--point", action="store_true", help="append a history point now regardless of age")
    a = ap.parse_args()
    path = tl.P("eval")
    state = bc.read_json(path) or {}
    try:
        point, table = evaluate()
    except Exception as ex:
        print("FATAL: eval failed (%s: %s)" % (type(ex).__name__, ex))
        return 1
    hist = state.get("history") or []
    if not state.get("baseline"):
        state["baseline"] = point
    last = hist[-1] if hist else None
    age_d = (time.time() - time.mktime(time.strptime(last["date"], "%Y-%m-%d"))) / 86400.0 if last else 999
    if a.point or age_d >= 6:
        hist.append(point)
        prev = hist[-2] if len(hist) >= 2 else None
        state["regressed"] = bool(prev and prev.get("rho") is not None and point.get("rho") is not None
                                  and point["rho"] < prev["rho"] - REGRESS_DROP)
        if state["regressed"]:
            print("WARN: taste model regressed: rho %s -> %s" % (prev["rho"], point["rho"]))
    state["history"] = hist[-52:]
    state["current"] = point
    state["calibration"] = table
    events, _ = tl.read_events()
    state["live_mae"], state["live_n"] = live_mae(events)
    tl.write_json(path, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
