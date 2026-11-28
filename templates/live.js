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
  // Plan B2: the whole queue as segments to play in order: a block of songs goes to Apple Music, a voiced item
  // (ID, tease, break) or the newscast plays in our own audio between blocks. Unvoiced items are dropped; the news
  // plays only when the newscast is under 70 minutes old. The first segment carries the offset into it, if joined late.
  const NEWS_FRESH_MS = 70 * 60 * 1000;
  function liveSegments(items, nowMs, newscast) {
    const list = (items || []).map((it) => ({ it, start: Date.parse(it.starts_at) }))
      .filter((x) => !Number.isNaN(x.start)).sort((a, b) => a.start - b.start);
    const fresh = newscast && newscast.src && nowMs - Date.parse(newscast.hour_local) < NEWS_FRESH_MS;
    const segs = [];
    for (const { it, start } of list) {
      const ms = it.kind === "song" ? it.duration_ms || 0 : it.audio_ms || it.duration_ms || 0;
      if (start + ms <= nowMs) continue;  // already over
      const offset = segs.length ? 0 : Math.max(0, Math.floor((nowMs - start) / 1000));
      if (it.kind === "song") {
        if (!it.song_id) continue;
        const last = segs[segs.length - 1];
        if (last && last.kind === "songs") last.songIds.push(String(it.song_id));
        else segs.push({ kind: "songs", songIds: [String(it.song_id)], startTime: offset, starts_at: it.starts_at });
      } else if (it.kind === "news") {
        if (fresh) segs.push({ kind: "voice", src: newscast.src, offset, starts_at: it.starts_at, news: true });
      } else if (it.audio_url) {
        segs.push({ kind: "voice", src: it.audio_url, offset, starts_at: it.starts_at, text: it.text || "" });
      }
    }
    return segs;
  }
  const api = { liveStart, liveSegments };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.woneLive = api;
})(typeof window !== "undefined" ? window : globalThis);
