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
  const say = (t) => { msgEl.textContent = t || ""; msgEl.hidden = !t; };

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
      if (station && song) { errors = 0; nowEl.textContent = [song.title, song.artistName].filter(Boolean).join(" · "); }
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
    return true;
  }
  async function failed() {  // a song that won't play here (often: not in this listener's country)
    errors += 1;
    if (errors >= 3) { say("Some songs aren't available in your country."); return; }
    try { await mk.skipToNextItem(); } catch (e) { await failed(); }
  }
  async function join() {  // tune in at the song and second that are live now
    if (joining) return;
    joining = true;
    try {
      const r = await fetch(new URL(station.src, location.href), { cache: "no-cache" });
      if (!r.ok) { say("The schedule isn't available right now."); return; }
      const live = window.woneLive.liveStart((await r.json()).items, Date.now());
      if (!live.songIds.length) { say("Nothing is scheduled right now."); return; }
      errors = 0;
      try { await mk.setQueue({ songs: live.songIds, startTime: live.startTime, startPlaying: true }); } catch (e) { await failed(); }
    } finally { joining = false; }
  }
  async function playStation(next) {
    audio.pause(); embed.replaceChildren(); embed.hidden = true;  // one sound at a time
    say("");
    if (!(await signIn())) return;
    localStorage.setItem("wone-apple", "1");
    station = next; item = next;
    root.classList.add("station");
    label.textContent = next.label || next.title || "Live";
    nowEl.textContent = next.title || "";
    await join();
  }
  function leaveStation() {
    if (!station) return;
    if (mk) mk.pause();
    station = null;
    root.classList.remove("station");
  }
  setInterval(() => {  // the station's clock, progress and end of queue
    if (!station || !mk) return;
    const t = mk.currentPlaybackTime || 0, d = mk.currentPlaybackDuration || 0;
    fill.style.width = d ? `${(t / d) * 100}%` : "0";
    timeEl.textContent = `${fmt(t)} / ${fmt(d)}`;
    icon.setAttribute("d", mk.isPlaying ? PAUSE : PLAY);
    if (window.MusicKit && mk.playbackState === MusicKit.PlaybackStates.completed) join();  // ran out: back to live
  }, 500);
  document.addEventListener("pointerdown", (e) => {  // start loading on touch, so sign-in opens inside the tap
    const p = e.target.closest("[data-play]");
    if (p && p.dataset.play.includes('"station"')) getMK().catch(() => {});
  });
  $("wone-skip-song").addEventListener("click", () => station && mk.skipToNextItem().catch(() => failed()));
  $("wone-live").addEventListener("click", () => station && join());

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
    if (station) return mk.isPlaying ? mk.pause() : mk.play();
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
      const r = await fetch(url, { headers: { Accept: "text/html" } });
      if (!r.ok) throw new Error(String(r.status));
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      const next = doc.querySelector("main"), here = document.querySelector("main");
      const nextBar = doc.getElementById("wone-player");
      if (!next || !here || !nextBar) throw new Error("not a shell page");  // e.g. an archive page built before the shell
      root.dataset.default = nextBar.dataset.default || "{}";  // the bar's ▶ plays this page's own audio
      if (!item) label.textContent = JSON.parse(root.dataset.default).label || "ONE 1.0 FM";
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

  // Station strip (Task 5): News and every music station, what is on now, re-read every minute. Text only:
  // headlines come from scraped posts, so nothing here is ever inserted as HTML.
  const stripEl = document.getElementById("wone-strip");
  async function drawStrip() {
    const row = stripEl && stripEl.querySelector(".strip-row");
    if (!row) return;
    try {
      const r = await fetch(stripEl.dataset.src, { cache: "no-cache" });
      if (!r.ok) return;  // keep whatever is showing
      const chips = (await r.json()).stations.map((st) => {
        const c = document.createElement(st.play ? "button" : "a");
        c.className = "chip";
        if (st.play) c.dataset.play = JSON.stringify(st.play); else c.href = st.page;
        c.title = st.description || "";
        const b = document.createElement("b"); b.textContent = st.name;
        const n = document.createElement("span"); n.textContent = st.on_now || "warming up";
        c.append(b, n);
        return c;
      });
      row.replaceChildren(...chips);
    } catch (err) { /* the strip is a nicety: a failed read leaves the page as it is */ }
  }
  drawStrip();
  setInterval(drawStrip, 60000);

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
