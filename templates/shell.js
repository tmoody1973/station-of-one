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

  function play(next) {
    if (next) {
      load(next);
      if (next.kind === "embed") return;
      if (next.start != null) {
        const go = () => { audio.currentTime = Number(next.start) || 0; };
        audio.readyState ? go() : audio.addEventListener("loadedmetadata", go, { once: true });
      }
    } else if (!item) {
      const d = JSON.parse(root.dataset.default || "{}");
      return d.src ? play(d) : undefined;  // the page's own newscast, from #t= if given
    }
    audio.play().catch(() => {});
  }

  window.wone = { play, pause: () => audio.pause(), seek: (s) => { audio.currentTime = s; }, now: () => item };

  $("wone-play").addEventListener("click", () => (audio.paused ? play() : audio.pause()));
  document.addEventListener("click", (e) => {  // delegated: works on first loads and after page swaps
    const stage = e.target.closest("[data-stage-embed]");  // a big player that lives on its page (music picks)
    if (stage) {
      audio.pause(); embed.replaceChildren(); embed.hidden = true;  // one thing at a time
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
    if (!audio.duration) return;
    const r = bar.getBoundingClientRect();
    audio.currentTime = ((e.clientX - r.left) / r.width) * audio.duration;
  });
  audio.addEventListener("play", () => icon.setAttribute("d", PAUSE));
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
      if (!next || !here) throw new Error("no main");
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

  const d = JSON.parse(root.dataset.default || "{}");  // show what ▶ will play, without playing it
  if (d.label) label.textContent = d.label;
  const t = location.hash.match(/t=(\d+)/);  // /index.html#t=95 starts the newscast at 95 s
  if (t && d.src) root.dataset.default = JSON.stringify({ ...d, start: Number(t[1]) });
})();
