// ONE 1.0 FM site shell: one player bar for every page (plan 2026-11-27-site-shell, decision 010).
// Any element with data-play='{"src", "title", "label", "start", "chapters", "kind"}' plays through it.
// Kinds: newscast/story/table (our audio), preview (Apple's 30 s clip, plays once, never advances),
// embed (a YouTube/Bandcamp player docked in the bar). Nothing plays without a tap.
(() => {
  if (window.wone) return;  // the bar lives outside <main>; page swaps never run this twice
  const $ = (id) => document.getElementById(id);
  const root = $("wone-player");
  if (!root) return;
  const audio = $("wone-audio"), bar = $("wone-bar"), fill = $("wone-fill"), timeEl = $("wone-time");
  const label = $("wone-label"), nowEl = $("wone-now"), icon = $("wone-icon"), embed = $("wone-embed");
  const PLAY = "M4 2l12 7-12 7z", PAUSE = "M4 2h4v14H4zM10 2h4v14h-4z";
  let item = null;
  const BASE = new URL(".", (document.currentScript && document.currentScript.src) || location.href);
  const MUSICKIT = "https://js-cdn.music.apple.com/musickit/v3/musickit.js";
  const msgEl = $("wone-msg");
  // Pages built before the strip or bar changed carry old styles for them: give those pages the current ones.
  if (![...document.querySelectorAll("style")].some((n) => n.textContent.includes("wone-shell-css"))) {
    const link = document.createElement("link");
    link.rel = "stylesheet"; link.href = new URL("shell.css", BASE).href;
    document.head.append(link);
  }
  document.head.querySelectorAll("style").forEach((n) => { n.dataset.wonePage = "1"; });  // the page's own styles, before any script adds one
  let mk = null, mkReady = null, station = null, errors = 0, joining = false;
  let gen = 0, lastStart = 0, rejoinAt = 0;  // gen: a newer tap or sound cancels a tune-in still in progress (review I2)
  // Plan B2: a station's IDs, breaks and news play in their own player, between Apple Music blocks, never over a song.
  // (The bar's shared <audio> means "the listener chose something else" and would leave the station.)
  const voice = new Audio();
  voice.preload = "auto";
  let segs = [], inVoice = false;
  const say = (t) => { if (!msgEl) return; msgEl.textContent = t || ""; msgEl.hidden = !t; };  // older pages have no msg line (C1)
  const playing = () => (mk.isPlaying ?? (mk.playbackState === MusicKit.PlaybackStates.playing));  // isPlaying unconfirmed (I6)

  const fmt = (s) => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  const chapterAt = (ms) => ((item && item.chapters) || []).filter((c) => ms >= c.start_ms).pop();

  function load(next) {
    if (next.kind === "embed") {
      audio.pause();
      const f = document.createElement("iframe");
      f.src = next.src; f.title = next.title || ""; f.allow = "autoplay; encrypted-media; fullscreen";
      f.referrerPolicy = "strict-origin-when-cross-origin";
      f.style.height = next.height || (/youtube/.test(next.src) ? "202px" : "120px");  // Bandcamp's small player is 120 px
      embed.replaceChildren(f); embed.hidden = false;
    } else {
      embed.replaceChildren(); embed.hidden = true;
      if (!item || item.src !== next.src) audio.src = next.src;
    }
    item = next;
    label.textContent = next.label || "ONE 1.0 FM";
    nowEl.textContent = next.title || "";
  }

  // A clock station (Plan C): full songs through the listener's own Apple Music, joined live. MusicKit loads only
  // after a tap; the token in /data/musickit.json is the public, origin-locked web token (decision 012).
  const loadScript = (src) => new Promise((ok, no) => {
    const s = document.createElement("script"); s.src = src; s.async = true; s.onload = ok; s.onerror = no; document.head.append(s);
  });
  async function musicKit() {
    const r = await fetch("/data/musickit.json", { cache: "no-cache" });
    if (!r.ok) throw new Error("no web token");
    const cfg = await r.json();
    if (!window.woneLive) await loadScript(new URL("live.js", BASE).href);
    if (!window.MusicKit) {
      const ready = new Promise((ok) => document.addEventListener("musickitloaded", ok, { once: true }));
      await loadScript(MUSICKIT);
      await ready;
    }
    await MusicKit.configure(cfg);
    mk = MusicKit.getInstance();
    mk.addEventListener("nowPlayingItemDidChange", () => showSong());
    mk.addEventListener("mediaPlaybackError", () => station && failed());
    return mk;
  }
  // Connect / Disconnect in settings. The status comes from a flag this browser keeps, so visiting settings
  // never loads Apple's script (MusicKit loads only after a tap).
  const showApple = () => document.querySelectorAll("[data-apple-status]").forEach((el) => {
    el.textContent = localStorage.getItem("wone-apple") === "1" ? "Connected" : "Not connected";
  });
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-apple]");
    if (!b) return;
    if (b.dataset.apple === "connect") { if (await signIn()) localStorage.setItem("wone-apple", "1"); }
    else { await window.wone.disconnect(); localStorage.removeItem("wone-apple"); }
    showApple();
  });
  document.addEventListener("pointerdown", (e) => { if (e.target.closest("[data-apple='connect']")) getMK().catch(() => {}); });
  document.addEventListener("wone:page", showApple);
  showApple();
  const getMK = () => (mkReady = mkReady || musicKit().catch((e) => { mkReady = null; throw e; }));

  async function signIn() {
    try { await getMK(); } catch (e) { say("Full songs aren't available right now."); return false; }
    try { await mk.authorize(); } catch (e) {
      say("Full songs need an Apple Music subscription. Previews still play on each station's page.");
      return false;
    }
    if (mk.isAuthorized === false) { say("Full songs need an Apple Music subscription."); return false; }
    return true;
  }
  async function failed(err) {  // a song that won't play here
    if (err && err.name === "NotAllowedError") { say("Tap ▶ to start."); return; }  // the browser wants a tap, not a skip (I3)
    errors += 1;
    if (errors >= 3) {
      say("Some songs won't play here: they may not be available in your country, or your Apple Music subscription may not be active.");
      return;
    }
    try { await mk.skipToNextItem(); } catch (e) { await failed(e); }
  }
  async function join(fromEnd = false, my = gen) {  // tune in at the song and second that are live now
    if (joining || !station) return;
    joining = true;
    try {
      const r = await fetch(new URL(station.src, location.href), { cache: "no-cache" });
      if (my !== gen) return;
      if (!r.ok) { say("The schedule isn't available right now."); return; }
      let items = (await r.json()).items || [];
      if (my !== gen) return;
      // After the segments run out, carry on after the last one already played, never back to what was just heard (I5).
      if (fromEnd && lastStart) items = items.filter((it) => Date.parse(it.starts_at) > lastStart);
      const news = stripData && (stripData.stations || []).find((st) => st.id === "news");
      segs = window.woneLive.liveSegments(items, Date.now(), news && news.play ? { src: news.play.src, hour_local: news.hour_local } : null);
      if (!segs.length) { say("Nothing is scheduled right now."); return; }
      if (fromEnd) { segs[0].startTime = 0; segs[0].offset = 0; }
      errors = 0;
    } finally { joining = false; }
    await nextSegment(my);
  }
  async function nextSegment(my = gen) {  // play the next segment: a block of songs in Apple Music, or a voice item here
    if (my !== gen || !station) return;
    const seg = segs.shift();
    if (!seg) { rejoinAt = Date.now() + 30000; return join(true, my); }  // the published queue ran out: fetch what's next
    lastStart = Date.parse(seg.last_at || seg.starts_at);  // a block resumes after its last song, never inside it (I5)
    audio.pause(); embed.replaceChildren(); embed.hidden = true;  // one sound at a time
    if (seg.kind === "songs") {
      inVoice = false; voice.pause();
      try { await mk.setQueue({ songs: seg.songIds, startTime: seg.startTime, startPlaying: true }); } catch (e) { await failed(e); }
      return;
    }
    if (mk && playing()) mk.pause();  // Apple's audio stops before ours starts
    inVoice = true;
    nowEl.textContent = seg.news ? "News" : seg.text || station.title || "";
    voice.src = new URL(seg.src, location.href).href;
    const at = () => { try { voice.currentTime = seg.offset || 0; } catch (e) { /* not seekable yet */ } };
    voice.readyState ? at() : voice.addEventListener("loadedmetadata", at, { once: true });
    try { await voice.play(); } catch (e) { inVoice = false; return nextSegment(my); }  // can't play it: skip, never stall
  }
  const voiceDone = () => { if (inVoice) { inVoice = false; nextSegment(); } };
  voice.addEventListener("ended", voiceDone);
  voice.addEventListener("error", voiceDone);
  async function playStation(next) {
    const my = ++gen;
    say("");
    if (!(await signIn()) || my !== gen) return;  // a newer tap (the newscast, a preview) wins
    localStorage.setItem("wone-apple", "1");
    station = next; item = next;
    root.classList.add("station");
    label.textContent = next.label || next.title || "Live";
    nowEl.textContent = next.title || "";
    shownSong = null;
    lastStart = 0;
    rejoinAt = 0;
    await join(false, my);
  }
  function leaveStation() {
    gen += 1;  // also cancels a tune-in still waiting on sign-in
    if (!station) return;
    if (mk) mk.pause();
    voice.pause(); inVoice = false; segs = [];
    station = null;
    item = null;
    root.classList.remove("station");
  }
  let shownSong = null;
  function showSong() {  // name what Apple says is playing now; its change event can come late or not at all
    const song = mk && mk.nowPlayingItem;
    const id = song ? String(song.id) : null;
    if (!station || inVoice || !song || id === shownSong) return;
    shownSong = id;
    errors = 0;
    nowEl.textContent = [song.artistName, song.title].filter(Boolean).join(" · ");  // Artist · Title, as in the strip
    document.dispatchEvent(new CustomEvent("wone:song"));  // the strip and the station page follow what plays
  }
  setInterval(() => {  // the station's clock, progress and end of queue
    if (!station || !mk) return;
    showSong();
    const t = inVoice ? voice.currentTime || 0 : mk.currentPlaybackTime || 0;
    const d = inVoice ? voice.duration || 0 : mk.currentPlaybackDuration || 0;
    fill.style.width = d ? `${(t / d) * 100}%` : "0";
    timeEl.textContent = `${fmt(t)} / ${fmt(d)}`;
    icon.setAttribute("d", (inVoice ? !voice.paused : playing()) ? PAUSE : PLAY);
    if (!inVoice && window.MusicKit && mk.playbackState === MusicKit.PlaybackStates.completed && Date.now() >= rejoinAt) {
      rejoinAt = Date.now() + (segs.length ? 3000 : 30000);  // once per finish; an empty queue retries every 30 s at most (I4)
      segs.length ? nextSegment() : join(true);
    }
  }, 500);
  document.addEventListener("pointerdown", (e) => {  // start loading on touch, so sign-in opens inside the tap
    const p = e.target.closest("[data-play]");
    if (p && p.dataset.play.includes('"station"')) getMK().catch(() => {});
  });
  $("wone-skip-song")?.addEventListener("click", () => {  // absent on older pages (C1)
    if (!station) return;
    if (inVoice) { voice.pause(); return voiceDone(); }  // skip the break: on to the next block
    mk.skipToNextItem().catch((e) => failed(e));
  });
  $("wone-live")?.addEventListener("click", () => { if (station) { lastStart = 0; join(); } });

  function play(next) {
    if (next && next.kind === "station") return playStation(next);
    leaveStation();
    if (next) {
      load(next);
      if (next.kind === "embed") return;
      if (next.start != null) {
        const go = () => { audio.currentTime = Number(next.start) || 0; };
        audio.readyState ? go() : audio.addEventListener("loadedmetadata", go, { once: true });
      }
    } else if (!item || item.kind === "embed") {  // a docked video gives way: one thing plays at a time
      embed.replaceChildren(); embed.hidden = true; item = null;
      const d = JSON.parse(root.dataset.default || "{}");
      return d.src ? play(d) : undefined;  // the page's own newscast, from #t= if given
    }
    audio.play().catch(() => {});
  }

  window.wone = {
    play, pause: () => (station ? (inVoice ? voice.pause() : mk.pause()) : audio.pause()), seek: (s) => { audio.currentTime = s; }, now: () => item,
    state: () => ({ inVoice, voicePaused: voice.paused, voiceTime: voice.currentTime, segments: segs.length }),  // for tests and the page
    connect: signIn,
    disconnect: async () => { leaveStation(); try { await getMK(); await mk.unauthorize(); } catch (e) { /* nothing to undo */ } },
    connected: async () => { try { return (await getMK()).isAuthorized; } catch (e) { return false; } },
  };

  $("wone-play").addEventListener("click", () => {
    if (station && inVoice) return voice.paused ? voice.play().catch(() => {}) : voice.pause();
    if (station) return playing() ? mk.pause() : mk.play();
    return audio.paused ? play() : audio.pause();
  });
  document.addEventListener("click", (e) => {  // delegated: works on first loads and after page swaps
    const stage = e.target.closest("[data-stage-embed]");  // a big player that lives on its page (music picks)
    if (stage) {
      leaveStation(); audio.pause(); embed.replaceChildren(); embed.hidden = true;  // one thing at a time
      const f = document.createElement("iframe");
      f.src = stage.dataset.stageEmbed; f.title = stage.dataset.title || "";
      f.allow = "autoplay; encrypted-media; fullscreen"; f.referrerPolicy = "strict-origin-when-cross-origin";
      stage.replaceWith(f);
      return;
    }
    const p = e.target.closest("[data-play]");
    if (p) { e.preventDefault(); play(JSON.parse(p.dataset.play)); return; }
    const s = e.target.closest("[data-skip]");
    if (s && item && item.kind !== "embed") audio.currentTime += Number(s.dataset.skip);
  });
  bar.addEventListener("click", (e) => {
    if (station || !audio.duration) return;
    const r = bar.getBoundingClientRect();
    audio.currentTime = ((e.clientX - r.left) / r.width) * audio.duration;
  });
  audio.addEventListener("play", () => { leaveStation(); icon.setAttribute("d", PAUSE); });
  audio.addEventListener("pause", () => icon.setAttribute("d", PLAY));
  audio.addEventListener("timeupdate", () => {
    const c = chapterAt(audio.currentTime * 1000);
    if (c && item.chapters.length > 1) nowEl.textContent = `${item.title ? item.title + " · " : ""}${c.title}`;
    if (audio.duration) fill.style.width = `${(audio.currentTime / audio.duration) * 100}%`;
    timeEl.textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration)}`;
  });

  // Page swaps (decision 010): fetch the next page and replace only <main>, so the player bar, the
  // masthead and the strip never reload and audio keeps playing. Anything unusual is a normal page load.
  const NORMAL = /\.(xml|mp3|mp4|m4a|png|jpg|jpeg|zip|pdf)$/i;
  const swappable = (a) => a.origin === location.origin && !a.target && !a.hasAttribute("download") &&
    !a.hasAttribute("data-no-swap") && !NORMAL.test(a.pathname) &&
    !(a.hash && a.pathname === location.pathname && a.search === location.search);
  async function go(url, push) {
    try {
      const r = await fetch(url, { headers: { Accept: "text/html" }, cache: "no-cache" });
      if (!r.ok) throw new Error(String(r.status));
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      const next = doc.querySelector("main"), here = document.querySelector("main");
      const nextBar = doc.getElementById("wone-player");
      if (!next || !here || !nextBar) throw new Error("not a shell page");
      if (!doc.querySelector(".strip-panel")) throw new Error("older page");  // its old styles would restyle the bar and strip  // e.g. an archive page built before the shell
      root.dataset.default = nextBar.dataset.default || "{}";  // the bar's ▶ plays this page's own audio
      if (!item) label.textContent = JSON.parse(root.dataset.default).label || "ONE 1.0 FM";
      // Each page carries its own layout rules in <style>: swap them with the content, or the new content is drawn
      // with the previous page's layout (Tarik, Nov 27). Stylesheet links already loaded (fonts) are kept as they are.
      document.head.querySelectorAll("style[data-wone-page]").forEach((n) => n.remove());  // ours only, never MusicKit's
      const have = new Set([...document.head.querySelectorAll("link[rel=stylesheet]")].map((l) => l.href));
      doc.head.querySelectorAll("link[rel=stylesheet]").forEach((l) => { if (!have.has(l.href)) document.head.append(document.adoptNode(l)); });
      doc.head.querySelectorAll("style").forEach((n) => { n.dataset.wonePage = "1"; document.head.append(document.adoptNode(n)); });
      here.replaceWith(document.adoptNode(next));
      document.title = doc.title;
      const line = doc.querySelector("header.site .line"), mine = document.querySelector("header.site .line");
      if (mine) mine.textContent = line ? line.textContent : "";
      if (push) history.pushState({ wone: true }, "", url);
      window.scrollTo(0, 0);
      document.dispatchEvent(new CustomEvent("wone:page", { detail: { url } }));
    } catch (err) {
      location.href = url;  // never leave a blank page
    }
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[href]");
    if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || !swappable(a)) return;
    e.preventDefault();
    go(a.href, true);
  });
  addEventListener("popstate", () => go(location.href, false));

  // Station strip (KCRW pattern, structure only): an "on air" mark; per station a name box with ▶ that plays it
  // (or opens its page when it has no live stream) and what's on now (a link to its page); "More station info"
  // opens a panel with each station's description and what's next. A clock station's now/next come from its
  // schedule by the clock, or from the player's own song while this browser plays it, so the strip always names
  // what you hear. Text only: titles come from feeds and Apple, so nothing here is inserted as HTML.
  const stripEl = document.getElementById("wone-strip");
  let stripData = null, panelOpen = false, stripSig = "";
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const songLine = (s) => [s.artist, s.title].filter(Boolean).join(" · ");
  function stationNow(st) {
    if (!st.schedule) return { now: st.now || { title: st.on_now || "" }, next: st.next };
    const sched = st.schedule, t = Date.now();
    const here = station && st.play && st.play.src === station.src && mk && mk.nowPlayingItem;
    let i = here ? sched.findIndex((s) => s.song_id === String(mk.nowPlayingItem.id)) : -1;
    if (here && i < 0) {  // the player is ahead of the published schedule: name what's actually playing
      const it = mk.nowPlayingItem;
      return { now: { at: "", title: [it.artistName, it.title].filter(Boolean).join(" · "), art: "" }, next: null };
    }
    if (i < 0) i = sched.findIndex((s) => Date.parse(s.starts_at) <= t && t < Date.parse(s.ends_at));
    if (i < 0) {
      const n = sched.find((s) => Date.parse(s.starts_at) > t);
      return { now: n ? { at: n.at, title: "Up next: " + songLine(n), art: n.art } : { at: "", title: "Nothing scheduled right now" }, next: null };
    }
    const nx = sched[i + 1];
    return { now: { at: sched[i].at, title: songLine(sched[i]), art: sched[i].art }, next: nx ? { at: nx.at, title: songLine(nx), art: nx.art } : null };
  }
  function fillNow() {  // the Music hub's "on now" lines: the same answer as the strip (music hub plan, Task 2)
    if (!stripData) return;  // not loaded yet: the page keeps the text it was built with
    document.querySelectorAll("main [data-now-of]").forEach((a) => {
      const st = (stripData.stations || []).find((x) => x.id === a.dataset.nowOf);
      if (st) a.textContent = stationNow(st).now.title || "";
    });
  }
  function renderStrip() {
    fillNow();
    const row = stripEl && stripEl.querySelector(".strip-row");
    if (!row || !stripData) return;
    let panel = stripEl.querySelector(".strip-panel");
    if (!panel) { panel = el("div", "wrap strip-panel"); stripEl.append(panel); }  // pages built before this change
    const sig = JSON.stringify((stripData.stations || []).map((st) => [st.id, st.name, st.page, st.play && st.play.src, stationNow(st)]));
    if (sig === stripSig && row.childElementCount) return;  // nothing changed: keep the buttons (and any tap or focus on them)
    stripSig = sig;
    const items = [el("span", "onair", "on air")], cols = [];
    let schedulePage = null;
    for (const st of stripData.stations || []) {
      const { now, next } = stationNow(st);
      const box = el(st.play ? "button" : "a", "st-name");
      if (st.play) box.dataset.play = JSON.stringify(st.play); else box.href = st.page;
      box.append(el("span", "nm", st.name), el("span", "tri", st.play ? "▶" : "→"));
      box.setAttribute("aria-label", st.play ? `Play ${st.name}` : `Open ${st.name}`);
      const nowLink = el("a", "st-now", now.title || "");
      nowLink.href = st.page;
      const wrap = el("div", "st");
      wrap.append(box, nowLink);
      items.push(wrap);
      const col = el("div", "sp");
      const h = el("h3", null, st.name);
      h.append(el("span", "pill", "on air"));
      col.append(h);
      if (now.art) { const img = el("img"); img.src = now.art; img.alt = ""; img.loading = "lazy"; img.referrerPolicy = "no-referrer"; col.append(img); }
      if (now.at) col.append(el("span", "at", now.at));
      const title = el("a", "sp-title", now.title || "");
      title.href = st.page;
      col.append(title, el("p", null, st.description || ""));
      if (next) col.append(el("h4", null, "Next up"), el("span", "at", next.at || ""), el("span", "sp-next", next.title || ""));
      const links = el("div", "sp-links");
      const page = el("a", null, "Station page"); page.href = st.page; links.append(page);
      if (st.schedule) {
        schedulePage = st.page.replace(/index\.html$/, "meeting/index.html");
        const pd = el("a", null, "The program director"); pd.href = schedulePage; links.append(pd);
        const how = el("a", null, "How it's programmed");
        how.href = st.page.replace(/index\.html$/, "how-it-works/index.html");  // /radio/<id>/ -> /radio/<id>/how-it-works/
        links.append(how);
      }
      col.append(links);
      cols.push(col);
    }
    const more = el("button", "more", panelOpen ? "▴ Less station info" : "▾ More station info");
    more.dataset.stripMore = "1";
    more.setAttribute("aria-expanded", String(panelOpen));
    items.push(more);
    if (stripData.playlists) { const a = el("a", "strip-link", "Playlists"); a.href = stripData.playlists; items.push(a); }
    if (schedulePage) { const a = el("a", "strip-link", "Schedule"); a.href = schedulePage; items.push(a); }
    row.replaceChildren(...items);
    panel.replaceChildren(...cols);
    panel.hidden = !panelOpen;
  }
  async function drawStrip() {
    if (!stripEl) return;
    try {
      const r = await fetch(stripEl.dataset.src, { cache: "no-cache" });
      if (!r.ok) return;  // keep whatever is showing
      stripData = await r.json();
      renderStrip();
    } catch (err) { /* the strip is a nicety: a failed read leaves the page as it is */ }
  }
  document.addEventListener("click", (e) => {
    const more = e.target.closest("[data-strip-more]");
    if (!more) return;
    panelOpen = !panelOpen;  // toggle in place: focus stays on the button
    more.textContent = panelOpen ? "▴ Less station info" : "▾ More station info";
    more.setAttribute("aria-expanded", String(panelOpen));
    const panel = stripEl.querySelector(".strip-panel");
    if (panel) panel.hidden = !panelOpen;
  });
  document.addEventListener("wone:song", () => renderStrip());
  drawStrip();
  setInterval(drawStrip, 60000);
  setInterval(renderStrip, 15000);  // the clock moves on between reads

  // A clock station's page lists its songs with start and end times; the browser marks what's on now and hides
  // what has finished, so "On now" stays true between the hourly rebuilds. Text only (titles are Apple's data).
  function markNow() {  // a clock station's tracklist (KCRW pattern): the song on now on top, what played below, later ones hidden
    document.querySelectorAll("main [data-station-src]").forEach((list) => {
      const rows = [...list.querySelectorAll("[data-starts]")];
      if (!rows.length) return;
      const t = Date.now(), at = (r, k) => Date.parse(r.dataset[k]);
      let cur = null;
      if (station && station.src === list.dataset.stationSrc && mk && mk.nowPlayingItem) {  // listening here: the song you hear
        const id = String(mk.nowPlayingItem.id);
        cur = rows.filter((r) => r.dataset.song === id).sort((a, b) => Math.abs(at(a, "starts") - t) - Math.abs(at(b, "starts") - t))[0] || null;
      }
      if (station && station.src === list.dataset.stationSrc && inVoice) {  // listening here, between songs: the break you hear
        cur = rows.filter((r) => r.dataset.kind === "voice").sort((a, b) => Math.abs(at(a, "starts") - t) - Math.abs(at(b, "starts") - t))[0] || cur;
      }
      if (!cur) cur = rows.find((r) => at(r, "starts") <= t && t < at(r, "ends")) || null;
      const edge = cur ? at(cur, "starts") : t;
      const next = cur ? null : rows.filter((r) => at(r, "starts") > t).sort((a, b) => at(a, "starts") - at(b, "starts"))[0] || null;
      rows.forEach((r) => {
        r.classList.toggle("now", r === cur);
        r.classList.toggle("next", r === next);
        r.classList.toggle("future", r !== cur && r !== next && at(r, "starts") > edge);
        const lbl = r.querySelector(".at");
        if (lbl) lbl.textContent = r === cur ? "Now" : r === next ? `Up next · ${r.dataset.at}` : (r.dataset.at || "");
      });
      const box = document.getElementById("onnow"), show = cur || next;
      if (!box || !show) return;
      box.querySelector(".lbl").textContent = cur ? "On now" : "Up next";
      box.querySelector("h2").textContent = show.dataset.title;
      box.querySelector(".by").textContent = show.dataset.by;
      const a = box.querySelector("a.am");
      if (a && show.dataset.apple) a.href = show.dataset.apple;
    });
  }
  markNow();
  setInterval(markNow, 30000);
  document.addEventListener("wone:page", markNow);
  document.addEventListener("wone:page", fillNow);
  document.addEventListener("wone:song", markNow);

  // The page keeps clear of the bar, whatever its height (a docked video makes it tall on a phone).
  new ResizeObserver(() => { document.body.style.paddingBottom = `${root.offsetHeight + 16}px`; }).observe(root);

  const d = JSON.parse(root.dataset.default || "{}");  // show what ▶ will play, without playing it
  if (d.label) label.textContent = d.label;
  const t = location.hash.match(/t=(\d+)/);  // /index.html#t=95 starts the newscast at 95 s
  if (t && d.src) root.dataset.default = JSON.stringify({ ...d, start: Number(t[1]) });
})();
