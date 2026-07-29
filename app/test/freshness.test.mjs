// Node test for the honesty state machine. These four states are the whole contract with the user: if freshness()
// ever returns 'fresh' for data that is old, or hides an undated payload, every card in the app starts lying.
// Run: node test\freshness.test.mjs   (plain node - no test framework, nothing added to the dependency budget)
import { freshness, humanAge } from '../src/lib/contracts.svelte.js';

let fails = 0;
function eq(actual, expected, label) {
  const ok = actual === expected;
  if (!ok) fails++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}  (got ${JSON.stringify(actual)}${ok ? '' : ', want ' + JSON.stringify(expected)})`);
}

const now = Date.parse('2026-07-29T12:00:00-05:00');
const at = (iso, slo) => freshness({ generated_at: iso, slo_seconds: slo }, now);

// inside its SLO -> fresh
eq(at('2026-07-29T11:50:00-05:00', 900).state, 'fresh', 'ten minutes old against a 15m SLO is fresh');
// past its SLO -> stale, never "fresh enough"
eq(at('2026-07-29T11:40:00-05:00', 900).state, 'stale', 'twenty minutes old against a 15m SLO is stale');
// exactly at the boundary is not yet stale
eq(at('2026-07-29T11:45:00-05:00', 900).state, 'fresh', 'exactly at the SLO boundary is still fresh');
// no schedule exists -> snapshot, regardless of age. It must never read as fresh and never as stale.
eq(at('2026-07-03T14:00:00-05:00', null).state, 'snapshot', 'a 26-day-old producer with no schedule is a snapshot');
eq(at('2026-07-29T11:59:00-05:00', null).state, 'snapshot', 'a one-minute-old producer with no schedule is STILL a snapshot');
eq(at('2026-07-29T11:59:00-05:00', undefined).state, 'snapshot', 'a missing slo_seconds is treated as no schedule');
// undated data is an error, never assumed current
eq(at('not-a-date', 900).state, 'error', 'an unparseable generated_at is an error');
eq(freshness({ slo_seconds: 900 }, now).state, 'error', 'a missing generated_at is an error');
eq(freshness(null, now).state, 'error', 'missing _meta entirely is an error');
// a clock skewed into the future must not produce a negative age
eq(at('2026-07-29T12:05:00-05:00', 900).ageSeconds, 0, 'a future timestamp clamps to zero age, not negative');
// age arithmetic
eq(Math.round(at('2026-07-29T11:00:00-05:00', 900).ageSeconds), 3600, 'one hour old measures 3600s');
eq(humanAge(10), 'just now', 'humanAge: seconds');
eq(humanAge(600), '10m ago', 'humanAge: minutes');
eq(humanAge(7200), '2.0h ago', 'humanAge: hours');
eq(humanAge(1148400), '13.3d ago', 'humanAge: days (the real unwatched-pool age)');
eq(humanAge(null), '?', 'humanAge: unknown stays unknown');

console.log(fails === 0 ? '\nALL PASS' : `\n${fails} FAILURE(S)`);
process.exit(fails === 0 ? 0 : 1);
