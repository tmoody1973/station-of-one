// Spike (b): swap only <main>; the player bar is never touched, so audio and embeds keep playing.
(() => {
  if (window.__wone) return; window.__wone = true;
  const internal = a => a.origin === location.origin && !a.target && !a.hasAttribute("download") &&
    !(a.hash && a.pathname === location.pathname);
  async function go(url, push) {
    try {
      const r = await fetch(url, {headers: {Accept: "text/html"}});
      if (!r.ok) throw new Error(r.status);
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      const next = doc.querySelector("main");
      if (!next) throw new Error("no main");
      document.querySelector("main").replaceWith(document.adoptNode(next));
      document.title = doc.title;
      if (push) history.pushState({}, "", url);
      window.scrollTo(0, 0);
    } catch (e) { location.href = url; }
  }
  document.addEventListener("click", e => {
    const a = e.target.closest("a");
    if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || !internal(a)) return;
    e.preventDefault(); go(a.href, true);
  });
  addEventListener("popstate", () => go(location.href, false));
})();
