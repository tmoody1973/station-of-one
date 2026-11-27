// Plan C Task 2: what's live in a clock station's queue. Run: node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const { liveStart } = createRequire(import.meta.url)("../../templates/live.js");
const T0 = Date.parse("2026-11-27T22:00:00+00:00");
const at = (s) => new Date(T0 + s * 1000).toISOString().replace(".000Z", "+00:00");
const QUEUE = [
  { starts_at: at(0), kind: "id", song_id: null, duration_ms: 8000 },
  { starts_at: at(8), kind: "song", song_id: "1", duration_ms: 240000 },
  { starts_at: at(248), kind: "song", song_id: "2", duration_ms: 240000 },
  { starts_at: at(488), kind: "break", song_id: null, duration_ms: 30000 },
  { starts_at: at(518), kind: "song", song_id: "3", duration_ms: 200000 },
  { starts_at: at(718), kind: "song", song_id: null, duration_ms: 200000 },
  { starts_at: at(918), kind: "song", song_id: "5", duration_ms: 200000 },
];

test("joins mid-song", () => {
  assert.deepEqual(liveStart(QUEUE, T0 + (248 + 90) * 1000), { songIds: ["2", "3", "5"], startTime: 90 });
});

test("joins next song at zero during a break", () => {
  assert.deepEqual(liveStart(QUEUE, T0 + 500 * 1000), { songIds: ["3", "5"], startTime: 0 });
});

test("nothing after the last song", () => {
  assert.deepEqual(liveStart(QUEUE, T0 + 5000 * 1000), { songIds: [], startTime: 0 });
});

test("skips spoken items and missing ids", () => {
  assert.deepEqual(liveStart(QUEUE, T0 + 1000), { songIds: ["1", "2", "3", "5"], startTime: 0 });
});

test("uses UTC ISO times as instants, not text", () => {
  const local = QUEUE.map((it) => ({ ...it, starts_at: new Date(Date.parse(it.starts_at)).toLocaleString("sv-SE", { timeZone: "America/Chicago" }).replace(" ", "T") + "-06:00" }));
  assert.deepEqual(liveStart(local, T0 + (248 + 90) * 1000), { songIds: ["2", "3", "5"], startTime: 90 });
});
