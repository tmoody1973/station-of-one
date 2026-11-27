"""Check 19: which approach keeps audio and an embed playing across page changes, Back and Forward.
Run: python3 spikes/check19_shell.py   (system Chrome, against the bucket's _checks/shell/ pages)"""
from playwright.sync_api import sync_playwright

BASE = "https://patient-mountain-3400.fly.storage.tigris.dev/_checks/shell"
STATE = """() => { const a = document.getElementById('au');
  return {path: location.pathname.split('/').slice(-2).join('/'), h1: document.querySelector('h1').textContent,
          paused: a.paused, t: Math.round(a.currentTime * 10) / 10, ytLoads: window.ytLoads || 0,
          same_audio: window.__au === a} }"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])
    for variant in ("a", "b"):
        pg = b.new_page()
        pg.goto(f"{BASE}/{variant}/index.html", wait_until="networkidle")
        pg.evaluate("() => { window.__au = document.getElementById('au'); return window.__au.play() }")
        pg.wait_for_timeout(2000)
        rows = [("start", pg.evaluate(STATE))]
        for name in ("Story page", "Jazz page", "Home", "Story page", "Jazz page"):
            pg.get_by_role("link", name=name).click()
            pg.wait_for_function(f"() => document.querySelector('h1').textContent === '{name}'", timeout=10000)
            pg.wait_for_timeout(1200)
            rows.append((f"click {name}", pg.evaluate(STATE)))
        for step in ("back", "back", "forward"):
            getattr(pg, f"go_{step}")()
            pg.wait_for_timeout(1500)
            rows.append((step, pg.evaluate(STATE)))
        print(f"== approach {variant}")
        for label, s in rows:
            print(f"  {label:18s} {s['path']:14s} h1={s['h1']:11s} paused={s['paused']!s:5s} t={s['t']:5} ytLoads={s['ytLoads']} same_audio={s['same_audio']}")
        pg.close()
    b.close()
