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
  let mk = null, mkReady = null, station = null, errors = 0, joining = false;
  let gen = 0, lastStart = 0, rejoinAt = 0;  // gen: a newer tap or sound cancels a tune-in still in progress (review I2)
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
    mk.addEventListener("nowPlayingItemDidChange", ({ item: song }) => {
      if (station && song) {
        errors = 0;
        nowEl.textContent = [song.title, song.artistName].filter(Boolean).join(" · ");
        document.dispatchEvent(new CustomEvent("wone:song"));  // the strip and the station page follow what plays
      }
    });
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
      // The client skips IDs and breaks, so it runs ahead of the schedule: after the queue runs out, carry on
      // after the last song already queued, never back to songs just heard (I5).
      if (fromEnd && lastStart) items = items.filter((it) => Date.parse(it.starts_at) > lastStart);
      const live = window.woneLive.liveStart(items, Date.now());
      if (!live.songIds.length) { say("Nothing is scheduled right now."); return; }
      if (fromEnd) live.startTime = 0;
      const queued = new Set(live.songIds);
      lastStart = Math.max(...items.filter((it) => queued.has(String(it.song_id))).map((it) => Date.parse(it.starts_at)));
      errors = 0;
      audio.pause(); embed.replaceChildren(); embed.hidden = true;  // one sound at a time, right before Apple's audio starts
      try { await mk.setQueue({ songs: live.songIds, startTime: live.startTime, startPlaying: true }); } catch (e) { await failed(e); }
    } finally { joining = false; }
  }
  async function playStation(next) {
    const my = ++gen;
    say("");
    if (!(await signIn()) || my !== gen) return;  // a newer tap (the newscast, a preview) wins
    localStorage.setItem("wone-apple", "1");
    station = next; item = next;
    root.classList.add("station");
    label.textContent = next.label || next.title || "Live";
    nowEl.textContent = next.title || "";
    lastStart = 0;
    rejoinAt = 0;
    await join(false, my);
  }
  function leaveStation() {
    gen += 1;  // also cancels a tune-in still waiting on sign-in
    if (!station) return;
    if (mk) mk.pause();
    station = null;
    item = null;
    root.classList.remove("station");
  }
  setInterval(() => {  // the station's clock, progress and end of queue
    if (!station || !mk) return;
    const t = mk.currentPlaybackTime || 0, d = mk.currentPlaybackDuration || 0;
    fill.style.width = d ? `${(t / d) * 100}%` : "0";
    timeEl.textContent = `${fmt(t)} / ${fmt(d)}`;
    icon.setAttribute("d", playing() ? PAUSE : PLAY);
    if (window.MusicKit && mk.playbackState === MusicKit.PlaybackStates.completed && Date.now() >= rejoinAt) {
      rejoinAt = Date.now() + 30000;  // once per finish, then every 30 s at most (I4)
      join(true);
    }
  }, 500);
  document.addEventListener("pointerdown", (e) => {  // start loading on touch, so sign-in opens inside the tap
    const p = e.target.closest("[data-play]");
    if (p && p.dataset.play.includes('"station"')) getMK().catch(() => {});
  });
  $("wone-skip-song")?.addEventListener("click", () => station && mk.skipToNextItem().catch((e) => failed(e)));  // absent on older pages (C1)
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
    play, pause: () => (station ? mk.pause() : audio.pause()), seek: (s) => { audio.currentTime = s; }, now: () => item,
    connect: signIn,
    disconnect: async () => { leaveStation(); try { await getMK(); await mk.unauthorize(); } catch (e) { /* nothing to undo */ } },
    connected: async () => { try { return (await getMK()).isAuthorized; } catch (e) { return false; } },
  };

  $("wone-play").addEventListener("click", () => {
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
      if (!next || !here || !nextBar) throw new Error("not a shell page");  // e.g. an archive page built before the shell
      root.dataset.default = nextBar.dataset.default || "{}";  // the bar's ▶ plays this page's own audio
      if (!item) label.textContent = JSON.parse(root.dataset.default).label || "ONE 1.0 FM";
      // Each page carries its own layout rules in <style>: swap them with the content, or the new content is drawn
      // with the previous page's layout (Tarik, Nov 27). Stylesheet links already loaded (fonts) are kept as they are.
      document.head.querySelectorAll("style").forEach((n) => n.remove());
      const have = new Set([...document.head.querySelectorAll("link[rel=stylesheet]")].map((l) => l.href));
      doc.head.querySelectorAll("link[rel=stylesheet]").forEach((l) => { if (!have.has(l.href)) document.head.append(document.adoptNode(l)); });
      doc.head.querySelectorAll("style").forEach((n) => document.head.append(document.adoptNode(n)));
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
  let stripData = null, panelOpen = false;
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
  function renderStrip() {
    const row = stripEl && stripEl.querySelector(".strip-row");
    if (!row || !stripData) return;
    let panel = stripEl.querySelector(".strip-panel");
    if (!panel) { panel = el("div", "wrap strip-panel"); stripEl.append(panel); }  // pages built before this change
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
    if (!e.target.closest("[data-strip-more]")) return;
    panelOpen = !panelOpen;
    renderStrip();
  });
  document.addEventListener("wone:song", () => renderStrip());
  drawStrip();
  setInterval(drawStrip, 60000);
  setInterval(renderStrip, 15000);  // the clock moves on between reads

  // A clock station's page lists its songs with start and end times; the browser marks what's on now and hides
  // what has finished, so "On now" stays true between the hourly rebuilds. Text only (titles are Apple's data).
  function markNow() {
    const rows = [...document.querySelectorAll("main [data-starts]")];
    if (!rows.length) return;
    const t = Date.now(), at = (r, k) => Date.parse(r.dataset[k]);
    const cur = rows.find((r) => at(r, "starts") <= t && t < at(r, "ends"));
    rows.forEach((r) => { r.classList.toggle("past", at(r, "ends") <= t); r.classList.toggle("now", r === cur); });
    const box = document.getElementById("onnow"), show = cur || rows.find((r) => at(r, "starts") > t);
    if (!box || !show) return;
    box.querySelector(".lbl").textContent = cur ? "On now" : "Up next";
    box.querySelector("h2").textContent = show.dataset.title;
    box.querySelector(".by").textContent = show.dataset.by;
    const a = box.querySelector("a.am");
    if (a && show.dataset.apple) a.href = show.dataset.apple;
  }
  markNow();
  setInterval(markNow, 30000);
  document.addEventListener("wone:page", markNow);

  // The page keeps clear of the bar, whatever its height (a docked video makes it tall on a phone).
  new ResizeObserver(() => { document.body.style.paddingBottom = `${root.offsetHeight + 16}px`; }).observe(root);

  const d = JSON.parse(root.dataset.default || "{}");  // show what ▶ will play, without playing it
  if (d.label) label.textContent = d.label;
  const t = location.hash.match(/t=(\d+)/);  // /index.html#t=95 starts the newscast at 95 s
  if (t && d.src) root.dataset.default = JSON.stringify({ ...d, start: Number(t[1]) });
})();
