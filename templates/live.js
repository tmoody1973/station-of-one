// ONE 1.0 FM: what's live on a clock station (Plan C). Given the station's published queue and the time now,
// the song on air and every song after it, plus how many seconds into the first one to start.
// Spoken items (IDs, breaks, news) are left out: in Plan C the stream is songs only (voice comes in Plan B2).
(function (root) {
  function liveStart(items, nowMs) {
    const songs = (items || [])
      .filter((it) => it.kind === "song" && it.song_id)
      .map((it) => ({ id: String(it.song_id), start: Date.parse(it.starts_at), end: Date.parse(it.starts_at) + (it.duration_ms || 0) }))
      .filter((s) => !Number.isNaN(s.start))
      .sort((a, b) => a.start - b.start);
    const live = songs.filter((s) => s.end > nowMs);
    if (!live.length) return { songIds: [], startTime: 0 };
    return { songIds: live.map((s) => s.id), startTime: Math.max(0, Math.floor((nowMs - live[0].start) / 1000)) };
  }
  const api = { liveStart };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.woneLive = api;
})(typeof window !== "undefined" ? window : globalThis);
