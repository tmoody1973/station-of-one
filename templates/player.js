// One audio player for the page: play/pause, ±15 s, seek to a story's chapter, follow chapters.
(function () {
  var audio = document.getElementById("player-audio");
  var player = document.getElementById("player");
  var playBtn = document.getElementById("play");
  var nowEl = document.getElementById("now-chapter");
  var fill = document.getElementById("bar-fill");
  var bar = document.getElementById("bar");
  var timeEl = document.getElementById("time");
  var chapters = JSON.parse(player.getAttribute("data-chapters") || "[]");

  function fmt(s) { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }
  function chapterAt(ms) {
    for (var i = chapters.length - 1; i >= 0; i--) if (ms >= chapters[i].start_ms) return chapters[i];
    return null;
  }
  function play() { audio.play(); }

  playBtn.addEventListener("click", function () { audio.paused ? play() : audio.pause(); });
  document.querySelectorAll("[data-skip]").forEach(function (b) {
    b.addEventListener("click", function () { audio.currentTime += Number(b.getAttribute("data-skip")); });
  });
  document.querySelectorAll("[data-start-ms]").forEach(function (b) {
    b.addEventListener("click", function () { audio.currentTime = Number(b.getAttribute("data-start-ms")) / 1000; play(); });
  });
  document.querySelectorAll("[data-play-src]").forEach(function (b) {
    b.addEventListener("click", function () {
      var src = b.getAttribute("data-play-src");
      if (audio.getAttribute("src") !== src) {
        audio.setAttribute("src", src);
        chapters = JSON.parse(b.getAttribute("data-chapters") || "[]");
      }
      play();
    });
  });
  bar.addEventListener("click", function (e) {
    if (!audio.duration) return;
    var r = bar.getBoundingClientRect();
    audio.currentTime = (e.clientX - r.left) / r.width * audio.duration;
  });
  audio.addEventListener("timeupdate", function () {
    var c = chapterAt(audio.currentTime * 1000);
    if (c) nowEl.textContent = "Now: " + c.title + " · chapter " + (chapters.indexOf(c) + 1) + " of " + chapters.length;
    if (audio.duration) fill.style.width = (audio.currentTime / audio.duration * 100) + "%";
    timeEl.textContent = fmt(audio.currentTime) + " / " + fmt(audio.duration);
  });
  // A link to /index.html#t=95 starts at 95 seconds (chapter links, PRD P10).
  var m = location.hash.match(/t=(\d+)/);
  if (m) audio.addEventListener("loadedmetadata", function () { audio.currentTime = Number(m[1]); }, { once: true });
})();
