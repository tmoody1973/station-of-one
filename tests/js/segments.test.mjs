// Plan B2 Task 5: a clock station's queue as segments to play in order. Run: node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const { liveSegments } = createRequire(import.meta.url)("../../templates/live.js");
const T0 = Date.parse("2026-11-27T22:00:00+00:00");
const at = (s) => new Date(T0 + s * 1000).toISOString().replace(".000Z", "+00:00");
const Q = [
  { starts_at: at(0), kind: "news", duration_ms: 165000 },
  { starts_at: at(165), kind: "id", audio_url: "/audio/radio/x/id.mp3", audio_ms: 6000, duration_ms: 8000 },
  { starts_at: at(173), kind: "song", song_id: "1", duration_ms: 240000 },
  { starts_at: at(413), kind: "song", song_id: "2", duration_ms: 240000 },
  { starts_at: at(653), kind: "break", audio_url: "/audio/radio/x/b.mp3", audio_ms: 24000, duration_ms: 25000 },
  { starts_at: at(678), kind: "song", song_id: "3", duration_ms: 200000 },
  { starts_at: at(878), kind: "break", duration_ms: 25000 },            // not voiced
  { starts_at: at(903), kind: "song", song_id: "4", duration_ms: 200000 },
];
const FRESH = { src: "/audio/2026-11-27T16.mp3", hour_local: "2026-11-27T16:00:00-06:00" };   // = T0

test("segments in order", () => {
  const s = liveSegments(Q, T0 + 10 * 1000, FRESH);
  assert.deepEqual(s.map((x) => x.kind), ["voice", "voice", "songs", "voice", "songs"]);
  assert.equal(s[0].src, FRESH.src);
  assert.equal(s[0].offset, 10);
  assert.deepEqual(s[2].songIds, ["1", "2"]);
  assert.deepEqual(s[4].songIds, ["3", "4"]);                          // the unvoiced break between them is dropped
});

test("join mid-break", () => {
  const s = liveSegments(Q, T0 + (653 + 12) * 1000, FRESH);
  assert.equal(s[0].kind, "voice");
  assert.equal(s[0].src, "/audio/radio/x/b.mp3");
  assert.equal(s[0].offset, 12);
  assert.deepEqual(s[1], { kind: "songs", songIds: ["3", "4"], startTime: 0, starts_at: at(678), last_at: at(903) });
});

test("join mid-song", () => {
  const s = liveSegments(Q, T0 + (413 + 30) * 1000, FRESH);
  assert.deepEqual(s[0], { kind: "songs", songIds: ["2"], startTime: 30, starts_at: at(413), last_at: at(413) });
});

test("stale news is skipped", () => {
  const old = { src: "/audio/old.mp3", hour_local: "2026-11-27T14:00:00-06:00" };   // two hours old
  assert.equal(liveSegments(Q, T0 + 10 * 1000, old)[0].src, "/audio/radio/x/id.mp3");
  assert.equal(liveSegments(Q, T0 + 10 * 1000, null)[0].src, "/audio/radio/x/id.mp3");
});
