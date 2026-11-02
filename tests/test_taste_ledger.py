# Unit tests for the taste loop's ledger + taste_core integration (gameplan V1 + V2). stdlib unittest; every case
# points the TASTE_* env overrides at a temp dir, so real data is never touched. Run:
#   python -m unittest discover -s C:\Users\bobdo\wg\brain\tests -v
import hashlib, json, os, shutil, sys, tempfile, threading, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "producers"))
import taste_ledger as tl          # noqa: E402
import taste_core as tc            # noqa: E402

REAL_BASE = r"C:\Users\bobdo\wg\audit\trakt-ratings.json"
BASE_SHA256 = "c0b985d38f0f6fee6865dad5ddc90ea90f46e5a06904076c6eee5fc648ae18ff"   # recorded in T0, 2026-11-02


def base_row(tmdb, rating, title="T", year=2000, rated_at="2026-07-16T14:03:29.000Z"):
    return {"rated_at": rated_at, "rating": rating, "type": "movie",
            "movie": {"title": title, "year": year, "ids": {"tmdb": tmdb}}}


class Env(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="taste-test-")
        self.old = {k: os.environ.get(k) for k in ("TASTE_LEDGER_PATH", "TASTE_STATE_PATH", "TASTE_OUT_DIR",
                                                    "TASTE_BASE_PATH", "TASTE_OFF_PATH", "TASTE_NO_CONTRACT")}
        os.environ["TASTE_LEDGER_PATH"] = os.path.join(self.d, "ledger.jsonl")
        os.environ["TASTE_STATE_PATH"] = os.path.join(self.d, "state.json")
        os.environ["TASTE_OUT_DIR"] = self.d
        os.environ["TASTE_BASE_PATH"] = os.path.join(self.d, "base.json")
        os.environ["TASTE_OFF_PATH"] = os.path.join(self.d, "OFF")
        os.environ["TASTE_NO_CONTRACT"] = "1"
        self.write_base([base_row(1, 6, "Six"), base_row(2, 9, "Nine")])

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.d, ignore_errors=True)

    def write_base(self, rows):
        with open(os.environ["TASTE_BASE_PATH"], "w", encoding="utf-8") as fh:
            json.dump(rows, fh)

    def rate(self, tmdb, v, ts=None, typ="movie", src="dash"):
        ev = {"kind": "rating", "src": src, "type": typ, "tmdb": tmdb, "value": v, "title": "x%d" % tmdb}
        if ts:
            ev["ts"] = ts
        return tl.append(ev)

    def eff_map(self):
        eff, _, _ = tl.fold(tl.load_base(), tl.read_events()[0])
        return {tl.key_of(r["type"], (r.get("movie") or r.get("show"))["ids"]["tmdb"]): r["rating"] for r in eff}


class V1Ledger(Env):
    def test_v1_1_concurrent_appends(self):
        def worker(n):
            for i in range(125):
                tl.append({"kind": "skip", "type": "movie", "tmdb": 1000 + n * 1000 + i})
        ts = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        evs, bad = tl.read_events()
        self.assertEqual(bad, 0)
        self.assertEqual(len(evs), 1000)
        self.assertEqual(len({e["id"] for e in evs}), 1000)

    def test_v1_1b_cross_process_appends(self):
        import subprocess
        prod = os.path.join(os.path.dirname(HERE), "producers")
        code = ("import sys; sys.path.insert(0, sys.argv[2]); import taste_ledger as tl\n"
                "for i in range(100): tl.append({'kind': 'skip', 'type': 'movie', 'tmdb': int(sys.argv[1]) * 1000 + i + 1})")
        ps = [subprocess.Popen([sys.executable, "-c", code, str(n), prod]) for n in range(1, 5)]
        self.assertEqual([p.wait() for p in ps], [0, 0, 0, 0])
        evs, bad = tl.read_events()
        self.assertEqual((len(evs), bad, len({e["id"] for e in evs})), (400, 0, 400))

    def test_v1_2_latest_wins_and_undo_chain(self):
        self.rate(1, 8, ts="2026-08-01T10:00:00-06:00", src="plex")
        dash = self.rate(1, 9, ts="2026-11-01T10:00:00-06:00")
        self.assertEqual(self.eff_map()["movie:1"], 9)
        u = tl.append({"kind": "undo", "undoes": dash["id"]})
        self.assertEqual(self.eff_map()["movie:1"], 8)
        tl.append({"kind": "undo", "undoes": u["id"]})
        self.assertEqual(self.eff_map()["movie:1"], 9)

    def test_v1_2b_older_event_does_not_beat_newer_base(self):
        self.write_base([base_row(1, 6, rated_at="2026-07-16T14:03:29.000Z")])
        self.rate(1, 3, ts="2026-01-01T00:00:00-06:00", src="plex")
        self.assertEqual(self.eff_map()["movie:1"], 6)

    def test_v1_2c_undo_of_unbased_rating_removes_it(self):
        ev = self.rate(77, 7)
        tl.append({"kind": "undo", "undoes": ev["id"]})
        self.assertNotIn("movie:77", self.eff_map())

    def test_v1_3_real_base_untouched(self):
        self.assertEqual(hashlib.sha256(open(REAL_BASE, "rb").read()).hexdigest(), BASE_SHA256)

    def test_v1_4_effective_shape(self):
        self.rate(5, 10, typ="tv")
        self.rate(6, 4)
        tl.compile_all(log=lambda *a: None)
        eff = json.load(open(os.path.join(self.d, "ratings-effective.json"), encoding="utf-8"))
        seen = set()
        for r in eff:
            self.assertIn(r["type"], ("movie", "show"))
            ent = r.get("movie") if r["type"] == "movie" else r.get("show")
            self.assertIsInstance(ent["ids"]["tmdb"], int)
            self.assertTrue(1 <= r["rating"] <= 10)
            self.assertIn("rated_at", r)
            k = (r["type"], ent["ids"]["tmdb"])
            self.assertNotIn(k, seen)
            seen.add(k)
        self.assertEqual(len(eff), 4)

    def test_v1_5_corrupt_line_skipped(self):
        self.rate(3, 7)
        with open(os.environ["TASTE_LEDGER_PATH"], "a", encoding="utf-8") as fh:
            fh.write('{"kind":"rating","src":"dash","ty\n')
        self.rate(4, 8)
        data = tl.compile_all(log=lambda *a: None)
        self.assertEqual(data["bad_lines"], 1)
        self.assertEqual(data["counts"]["effective"], 4)

    def test_v1_6_missing_ledger_and_off_flag(self):
        data = tl.compile_all(log=lambda *a: None)
        self.assertFalse(data["degraded"])
        self.assertEqual(data["counts"]["effective"], 2)
        self.rate(9, 9)
        open(os.environ["TASTE_OFF_PATH"], "w").close()
        data = tl.compile_all(log=lambda *a: None)
        self.assertTrue(data["degraded"])
        self.assertIn("TASTE-LEDGER-OFF", data["reason"])
        self.assertEqual(data["counts"]["effective"], 2)

    def test_v1_7_conflict_stop_writes_nothing(self):
        self.write_base([base_row(i, 5) for i in range(1, 30)])
        rated = [("movie", i, str(i), "t", 2000, 9.0, 1785000000) for i in range(1, 30)]
        with self.assertRaises(SystemExit) as cm:
            tl.ingest(rated=rated, log=lambda *a: None)
        self.assertEqual(cm.exception.code, 2)
        self.assertFalse(os.path.exists(os.environ["TASTE_LEDGER_PATH"]))
        self.assertFalse(os.path.exists(os.environ["TASTE_STATE_PATH"]))

    def test_v1_8_ingest_idempotent(self):
        rated = [("movie", 1, "11", "Six", 2000, 6.0, 1785000000), ("movie", 50, "12", "New", 2001, 8.0, 1785000001)]
        new, rep = tl.ingest(rated=rated, log=lambda *a: None)
        self.assertEqual(len(new), 1)
        self.assertEqual(rep["same"], 1)
        new2, _ = tl.ingest(rated=rated, log=lambda *a: None)
        self.assertEqual(len(new2), 0)
        later = rated + [("movie", 51, "13", "Remote", 2002, 7.0, 1785000999)]
        new3, rep3 = tl.ingest(rated=later, log=lambda *a: None)
        self.assertEqual([e["src"] for e in new3], ["tv-remote"])

    def test_v1_8b_bulk_rewrite_burst_stops(self):
        tl.ingest(rated=[("movie", 1, "11", "Six", 2000, 6.0, 1785000000)], log=lambda *a: None)
        burst = [("movie", 100 + i, str(100 + i), "t", 2000, 7.0, 1785001000 + i) for i in range(30)]
        with self.assertRaises(SystemExit) as cm:
            tl.ingest(rated=burst, log=lambda *a: None)
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(len(tl.read_events()[0]), 0)
        new, _ = tl.ingest(rated=burst, log=lambda *a: None, accept_burst=True)
        self.assertEqual(len(new), 30)

    def test_v1_9_soft_kinds_never_ratings(self):
        tl.append({"kind": "thumb", "type": "movie", "tmdb": 100, "value": "up"})
        tl.append({"kind": "thumb", "type": "tv", "tmdb": 101, "value": "down"})
        tl.append({"kind": "notme", "type": "movie", "tmdb": 102})
        tl.append({"kind": "skip", "type": "movie", "tmdb": 103})
        tl.append({"kind": "bailed", "type": "movie", "tmdb": 104})
        eff, sig, _ = tl.fold(tl.load_base(), tl.read_events()[0])
        keys = {tl.key_of(r["type"], (r.get("movie") or r.get("show"))["ids"]["tmdb"]) for r in eff}
        self.assertFalse(keys & {"movie:100", "tv:101", "movie:102", "movie:103", "movie:104"})
        self.assertEqual([d["key"] for d in sig["thumbs_up"]], ["movie:100"])
        self.assertEqual(sig["hidden"], ["tv:101"])
        self.assertEqual([d["key"] for d in sig["household"]], ["movie:102"])
        self.assertEqual([d["key"] for d in sig["bailed"]], ["movie:104"])

    def test_v1_9b_thumb_clear_and_rated_bail(self):
        tl.append({"kind": "thumb", "type": "movie", "tmdb": 100, "value": "down"})
        tl.append({"kind": "thumb", "type": "movie", "tmdb": 100, "value": "clear"})
        tl.append({"kind": "bailed", "type": "movie", "tmdb": 104})
        self.rate(104, 6)
        _, sig, _ = tl.fold(tl.load_base(), tl.read_events()[0])
        self.assertEqual(sig["hidden"], [])
        self.assertEqual(sig["bailed"], [])      # an explicit rating supersedes the bail

    def test_v1_10_validation_refuses_bad_values(self):
        for v in (0, 11, 7.5, "x", None, True):
            with self.assertRaises(ValueError):
                tl.append({"kind": "rating", "type": "movie", "tmdb": 1, "value": v})
        for bad in ({"kind": "rating", "type": "film", "tmdb": 1, "value": 5},
                    {"kind": "rating", "type": "movie", "tmdb": -1, "value": 5},
                    {"kind": "rating", "type": "movie", "tmdb": 1, "value": 5, "rating_key": "12a"},
                    {"kind": "nope", "type": "movie", "tmdb": 1},
                    {"kind": "thumb", "type": "movie", "tmdb": 1, "value": "meh"},
                    {"kind": "undo"}):
            with self.assertRaises(ValueError):
                tl.append(bad)
        self.assertFalse(os.path.exists(os.environ["TASTE_LEDGER_PATH"]))


class StubTMDB(object):
    def __init__(self, feats):
        self.feats = feats

    def details(self, kind, tid, ttl):
        return self.feats[(kind, int(tid))]


def feat(kind, tid, title, genres, kw, directors=(), cast=()):
    return {"kind": kind, "id": tid, "title": title, "genres": list(genres), "keywords": list(kw),
            "directors": list(directors), "cast": list(cast), "vote_average": 8.0, "vote_count": 5000,
            "original_language": "en", "year": 2015}


class V2TasteCore(Env):
    def test_v2_1_source_resolution(self):
        rows = [base_row(i, 8) for i in range(1, 401)]
        with open(os.path.join(self.d, "ratings-effective.json"), "w") as fh:
            json.dump(rows, fh)
        with open(os.path.join(self.d, "taste-signals.json"), "w") as fh:
            json.dump({"hidden": ["movie:9"]}, fh)
        r, src, sig = tc.ratings_source()
        self.assertEqual(src, "ratings-effective")
        self.assertEqual(sig["hidden"], ["movie:9"])
        open(os.environ["TASTE_OFF_PATH"], "w").close()
        self.assertEqual(tc.ratings_source()[1], "trakt-ratings")
        os.remove(os.environ["TASTE_OFF_PATH"])
        with open(os.path.join(self.d, "ratings-effective.json"), "w") as fh:
            json.dump(rows[:399], fh)                       # too small -> distrust it
        self.assertEqual(tc.ratings_source()[1], "trakt-ratings")
        os.remove(os.path.join(self.d, "ratings-effective.json"))
        self.assertEqual(tc.ratings_source()[1], "trakt-ratings")

    def test_v2_2_blocked_titles_excluded(self):
        t = tc.Taste(log=lambda *a: None)
        t.blocked = {"movie:42": "hidden by your thumbs-down", "tv:7": "marked not-me (household)"}
        self.assertEqual(t.excluded(feat("movie", 42, "x", ["Drama"], [])), "hidden by your thumbs-down")
        self.assertIsNotNone(t.excluded(feat("tv", 7, "x", ["Drama"], [])))
        self.assertIsNone(t.excluded(feat("tv", 42, "x", ["Drama"], [])))      # same id, other medium

    def _taste_with(self, feats):
        t = tc.Taste(log=lambda *a: None)
        t.tmdb = StubTMDB(feats)
        t.genre_w = {"Drama": 0.2, "Crime": 0.3}
        return t

    def test_v2_3_and_v2_5_tv_rating_becomes_seed_and_lifts_neighbours(self):
        seed = feat("tv", 10, "Heist Show", ["Crime", "Drama"], ["heist", "bank robbery", "crew"], ["Ann Maker"])
        cand = feat("tv", 11, "Other Heist", ["Crime", "Drama"], ["heist", "crew", "vault"], [])
        t = self._taste_with({("tv", 10): seed})
        before = t.score(cand)[0]
        t._ledger_tv([{"type": "show", "rating": 10, "show": {"title": "Heist Show", "ids": {"tmdb": 10}}}])
        self.assertIn(10, t.rated_tv_ids)
        self.assertEqual([s["title"] for s in t.seeds], ["Heist Show"])
        after, because, _, _ = t.score(cand)
        self.assertGreaterEqual(after, before)
        self.assertGreater(after, before)
        self.assertIn("Heist Show", because)

    def test_v2_5b_kids_lane_tv_rating_ignored(self):
        kid = feat("tv", 20, "Gabby's Dollhouse", ["Animation", "Kids", "Family"], ["dollhouse"])
        t = self._taste_with({("tv", 20): kid})
        t._ledger_tv([{"type": "show", "rating": 10, "show": {"title": "Gabby", "ids": {"tmdb": 20}}}])
        self.assertEqual(t.seeds, [])
        self.assertEqual(t.dislikes, [])

    def test_v2_6_soft_signals(self):
        up = feat("movie", 30, "Liked", ["Thriller"], ["spy"], ["Dir Up"])
        down = feat("movie", 31, "Nope", ["Horror"], ["gore"], ["Dir Down"])
        t = self._taste_with({("movie", 30): up, ("movie", 31): down})
        t.signals = {"thumbs_up": [{"type": "movie", "tmdb": 30}], "thumbs_down": [{"type": "movie", "tmdb": 31}]}
        t._soft_signals()
        self.assertEqual(t.seeds[0]["weight"], tc.THUMB_UP_W)
        self.assertEqual(t.dislikes[0]["w"], tc.SOFT_DISLIKE_W)
        self.assertGreater(t.person_w["Dir Up"], 0)
        self.assertLess(t.person_w["Dir Down"], 0)


if __name__ == "__main__":
    unittest.main()
