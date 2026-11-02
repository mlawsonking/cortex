# Unit tests for the taste verbs (V3, the parts that need no live server) and the rate queue / eval maths (V4).
# Temp ledger + temp contract dir + a DEAD Plex port: nothing real is read or written.
import json, os, shutil, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WG = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "producers"))
sys.path.insert(0, os.path.join(WG, "dashboard"))
import taste_ledger as tl          # noqa: E402
import taste_eval as te            # noqa: E402
import rate_queue as rq            # noqa: E402
import taste_verbs as tv           # noqa: E402


class Env(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="taste-verbs-")
        self.keys = ("TASTE_LEDGER_PATH", "TASTE_STATE_PATH", "TASTE_OUT_DIR", "TASTE_BASE_PATH", "TASTE_OFF_PATH",
                     "TASTE_NO_CONTRACT", "TASTE_DATA_DIR", "TASTE_PLEX_URL", "TASTE_NO_KICK")
        self.old = {k: os.environ.get(k) for k in self.keys}
        os.environ.update({
            "TASTE_LEDGER_PATH": os.path.join(self.d, "ledger.jsonl"), "TASTE_STATE_PATH": os.path.join(self.d, "s.json"),
            "TASTE_OUT_DIR": self.d, "TASTE_BASE_PATH": os.path.join(self.d, "base.json"),
            "TASTE_OFF_PATH": os.path.join(self.d, "OFF"), "TASTE_NO_CONTRACT": "1", "TASTE_DATA_DIR": self.d,
            "TASTE_PLEX_URL": "http://127.0.0.1:9", "TASTE_NO_KICK": "1"})
        json.dump([{"rated_at": "2026-07-16T14:03:29.000Z", "rating": 6, "type": "movie",
                    "movie": {"title": "Base", "year": 2000, "ids": {"tmdb": 1}}}], open(os.path.join(self.d, "base.json"), "w"))
        self.actions_off = os.path.join(self.d, "ACTIONS-OFF")
        self.contract("rate-queue", {"items": [{"key": "m:500", "type": "movie", "tmdb_id": 77, "title": "Queued",
                                                "year": 2019, "guess": 8}]})
        self.contract("streaming-best", {"items": [{"type": "tv", "tmdb_id": 900, "title": "SB Show", "year": 2025}]})
        self.contract("missed-gems", {"landed": [], "gems": [{"type": "movie", "tmdb_id": 901, "title": "Gem",
                                                              "year": 2010, "rating_key": "601"}], "shows": []})
        tv._recent = {k: [] for k in tv.LIMITS}
        tv._inflight.clear()

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.d, ignore_errors=True)

    def contract(self, name, data):
        json.dump({"_meta": {"contract": name}, "data": data}, open(os.path.join(self.d, name + ".json"), "w"))

    def lines(self):
        p = os.environ["TASTE_LEDGER_PATH"]
        return len(open(p).read().splitlines()) if os.path.exists(p) else 0

    def rate(self, key, value):
        return tv.rate_title({"key": [key], "value": [value]}, self.actions_off)


class V3Verbs(Env):
    def test_v3_2_kill_flags(self):
        open(self.actions_off, "w").close()
        for out in (self.rate("m:500", "8"), tv.taste_feedback({"key": ["tv:900"], "signal": ["up"]}, self.actions_off),
                    tv.queue_watch({"rating_key": ["601"]}, self.actions_off)):
            self.assertTrue(out.startswith("ERR: actions are switched off"), out)
        os.remove(self.actions_off)
        open(os.environ["TASTE_OFF_PATH"], "w").close()
        self.assertIn("taste loop is off", self.rate("m:500", "8"))
        self.assertEqual(self.lines(), 0)

    def test_v3_3_refusals_write_nothing(self):
        for v in ("0", "11", "7.5", "x", "", "08", "-1", "1e1", "7 7"):     # (surrounding whitespace is trimmed: " 7" = 7)
            self.assertTrue(self.rate("m:500", v).startswith("ERR"), v)
        for k in ("m:", "x:500", "m:12a", "m:1234567890123", ""):
            self.assertTrue(self.rate(k, "8").startswith("ERR"), k)
        self.assertTrue(self.rate("m:999", "8").startswith("ERR: Plex unreachable"))   # not queued + dead Plex
        self.assertEqual(self.lines(), 0)

    def test_v3_4_and_v3_6_queued_rating_survives_dead_plex(self):
        out = json.loads(self.rate("m:500", "9"))
        self.assertTrue(out["ok"])
        self.assertEqual(out["guess"], 8)
        self.assertEqual(out["plex"], "failed")           # Plex down: the ledger still has it
        ev = tl.read_events()[0][-1]
        self.assertEqual((ev["kind"], ev["value"], ev["tmdb"], ev["rating_key"], ev["guess"]), ("rating", 9, 77, "500", 8))
        und = json.loads(self.rate("m:500", "undo:" + out["event_id"]))
        self.assertTrue(und["ok"])
        self.assertTrue(self.rate("m:500", "undo:" + out["event_id"]).startswith("ERR: already undone"))
        self.assertTrue(self.rate("m:500", "undo:nope").startswith("ERR"))

    def test_v3_4b_skip_notme_bailed(self):
        for v in ("skip", "notme", "bailed"):
            self.assertTrue(json.loads(self.rate("m:500", v))["ok"])
        self.assertEqual([e["kind"] for e in tl.read_events()[0]], ["skip", "notme", "bailed"])

    def test_v3_7_rate_limit(self):
        now = time.time()
        tv._recent["rate-title"] = [now] * 60
        self.assertIn("rate limit", self.rate("m:500", "8"))
        tv._recent["rate-title"] = []
        tv._inflight.add("m:500")
        self.assertIn("already saving", self.rate("m:500", "8"))

    def test_v3_8_feedback_allow_list(self):
        self.assertTrue(tv.taste_feedback({"key": ["tv:12345"], "signal": ["up"]}, self.actions_off).startswith("ERR"))
        self.assertTrue(tv.taste_feedback({"key": ["tv:900"], "signal": ["meh"]}, self.actions_off).startswith("ERR"))
        self.assertTrue(tv.taste_feedback({"key": ["movie:900"], "signal": ["up"]}, self.actions_off).startswith("ERR"))
        self.assertEqual(self.lines(), 0)
        self.assertTrue(json.loads(tv.taste_feedback({"key": ["tv:900"], "signal": ["down"]}, self.actions_off))["ok"])
        self.assertTrue(json.loads(tv.taste_feedback({"key": ["movie:901"], "signal": ["up"]}, self.actions_off))["ok"])
        _, sig, _ = tl.fold(tl.load_base(), tl.read_events()[0])
        self.assertEqual(sig["hidden"], ["tv:900"])
        tv.taste_feedback({"key": ["tv:900"], "signal": ["clear"]}, self.actions_off)
        _, sig, _ = tl.fold(tl.load_base(), tl.read_events()[0])
        self.assertEqual(sig["hidden"], [])

    def test_v3_9_queue_watch_allow_list(self):
        self.assertTrue(tv.queue_watch({"rating_key": ["999"]}, self.actions_off).startswith("ERR"))
        self.assertTrue(tv.queue_watch({"rating_key": ["60a"]}, self.actions_off).startswith("ERR"))
        self.assertTrue(tv.queue_watch({"rating_key": ["601"], "op": ["nuke"]}, self.actions_off).startswith("ERR"))


class V4Queue(Env):
    def test_v4_2_household_content(self):
        self.assertTrue(rq.household_content(["Drama"], "G", True))
        self.assertTrue(rq.household_content(["Comedy"], "TV-Y7", True))
        self.assertTrue(rq.household_content(["Family", "Comedy"], "PG", True))
        self.assertTrue(rq.household_content(["Animation"], "PG-13", False))
        self.assertIsNone(rq.household_content(["Animation"], "PG-13", True))
        self.assertIsNone(rq.household_content(["Drama", "Crime"], "R", False))

    def test_v4_3_answered_set(self):
        now = time.time()
        sig = {"household": [{"key": "movie:5"}], "bailed": [{"key": "movie:6"}],
               "skipped": [{"key": "movie:7", "until": now + 10}, {"key": "movie:8", "until": now - 10}]}
        done = rq.answered(sig, {"movie:1"}, now)
        self.assertEqual(done, {"movie:1", "movie:5", "movie:6", "movie:7"})

    def test_v4_context_model(self):
        plays = [{"title_key": "kid", "device": "roku", "hour": 7}] * 90 + \
                [{"title_key": "adult", "device": "roku", "hour": 22}] * 10 + \
                [{"title_key": "adult", "device": "bedroom", "hour": 22}] * 30
        c = rq.Context(plays, {"kid": 0, "adult": 1}, {"roku": "MKUltra"})
        self.assertLess(c.p("roku", 7), 0.1)
        self.assertGreater(c.p("bedroom", 22), 0.9)
        self.assertGreater(c.p("roku", 22), c.p("roku", 7))
        self.assertIn("MKUltra", c.explain("roku", 7))

    def test_v4_6_quick_removes_answered(self):
        os.environ.pop("TASTE_NO_CONTRACT")
        item = {"key": "m:500", "type": "movie", "tmdb_id": 77, "leverage": 0.6}
        item2 = dict(item, key="m:501", tmdb_id=78)
        data = {"backlog": {"total": 2, "high_leverage": 2, "beyond_high": 0, "household_hidden": 0, "bailed": 0,
                            "rated_7d": 0, "rated_30d": 0, "streak_days": 0, "median_moves": 1},
                "items": [item, item2], "household": []}
        written = {}
        orig_read, orig_write, orig_data = rq.bc.read_json, rq.bc.write_contract, rq.bc.DATA
        rq.bc.DATA = self.d
        rq.bc.write_contract = lambda name, d, generated_at_ts=None, source=None: written.update({name: d})
        json.dump({"_meta": {"generated_at": "2026-11-02T05:40:00-06:00"}, "data": data},
                  open(os.path.join(self.d, "rate-queue.json"), "w"))
        try:
            ev = tl.append({"kind": "rating", "src": "dash", "type": "movie", "tmdb": 77, "value": 7})
            self.assertEqual(rq.quick(), 0)
            d = written["rate-queue"]
            self.assertEqual([r["key"] for r in d["items"]], ["m:501"])
            self.assertEqual(d["backlog"]["total"], 1)
            self.assertEqual(d["backlog"]["rated_7d"], 1)
            self.assertEqual(d["backlog"]["streak_days"], 1)
            # undo -> the next quick run restores the row from the stash, in leverage order
            json.dump({"_meta": {"generated_at": "2026-11-02T05:40:00-06:00"}, "data": d},
                      open(os.path.join(self.d, "rate-queue.json"), "w"))
            tl.append({"kind": "undo", "src": "dash", "undoes": ev["id"]})
            self.assertEqual(rq.quick(), 0)
            d = written["rate-queue"]
            self.assertEqual(sorted(r["key"] for r in d["items"]), ["m:500", "m:501"])
            self.assertEqual(d["backlog"]["total"], 2)
        finally:
            rq.bc.write_contract, rq.bc.DATA = orig_write, orig_data

    def test_v4_7_eval_maths(self):
        self.assertEqual(te.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertEqual(te.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        stable = {t: te.in_holdout(t) for t in range(1, 2000)}
        self.assertTrue(0.15 < sum(stable.values()) / 1999.0 < 0.25)
        self.assertEqual(stable, {t: te.in_holdout(t) for t in range(1, 2000)})     # deterministic
        pairs = [(i / 100.0, 5 + (i % 5)) for i in range(100)]
        table = te.calibrate(pairs)
        self.assertEqual(len(table), 5)
        self.assertEqual([r for _, r in table], sorted(r for _, r in table))           # monotone
        g = [te.guess_from(table, m / 10.0) for m in range(0, 11)]
        self.assertEqual(g, sorted(g))
        self.assertTrue(all(1 <= x <= 10 for x in g))

    def test_v4_live_mae(self):
        tl.append({"kind": "rating", "src": "dash", "type": "movie", "tmdb": 3, "value": 6, "guess": 8})
        e = tl.append({"kind": "rating", "src": "dash", "type": "movie", "tmdb": 4, "value": 9, "guess": 8})
        self.assertEqual(te.live_mae(tl.read_events()[0]), (1.5, 2))
        tl.append({"kind": "undo", "src": "dash", "undoes": e["id"]})
        self.assertEqual(te.live_mae(tl.read_events()[0]), (2.0, 1))


if __name__ == "__main__":
    unittest.main()
