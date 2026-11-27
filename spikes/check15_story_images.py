"""Check 15: story images. Proves the two new request shapes before production code uses them.

1. Apify apify~cheerio-scraper: preview photo (og:image / twitter:image) of recent aired-story links.
2. Gemini gemini-3.1-flash-image: one Bauhaus illustration, 16:9.
Run on the Sprite: uv run python spikes/check15_story_images.py
"""
import base64
import json
import time
from pathlib import Path

from station.gateway import Gateway
from station.steps.scrape import run_actor

SOCIAL = ("reddit.com", "bsky.app", "news.ycombinator.com", "x.com", "twitter.com")
PAGE_FUNCTION = """async function pageFunction(context) {
  const { $, request } = context;
  const pick = (sel) => $(sel).attr('content') || null;
  return { url: request.url, image: pick('meta[property="og:image"]') || pick('meta[name="twitter:image"]') };
}"""

gw = Gateway()
urls = []
for nc in sorted(Path("data/runs").glob("2026-11-2*T*/newscast.json"), reverse=True):
    for s in json.loads(nc.read_text())["stories"]:
        u = s["sources"][0]["url"] if s["sources"] else ""
        if u.startswith("http") and not any(h in u for h in SOCIAL) and u not in urls:
            urls.append(u)
    if len(urls) >= 8:
        break
urls = urls[:8]
print("urls:", *urls, sep="\n  ")

t = time.time()
try:
  run = run_actor(gw, "apify~cheerio-scraper", {
      "startUrls": [{"url": u} for u in urls], "pageFunction": PAGE_FUNCTION, "maxCrawlingDepth": 0,
      "linkSelector": "", "proxyConfiguration": {"useApifyProxy": True}}, cap_usd=0.10)
  print(f"apify {run.status} in {time.time() - t:.1f}s, cost ${run.usd:.4f}, {len(run.items)} items")
  for it in run.items:
    print(f"  {it.get('image')!s:100.100}  <- {it.get('url')}")
except Exception as e:
  print("apify failed:", str(e)[:160])

prompt = ("An abstract Bauhaus composition on a cream paper background, using only primary red, yellow, blue and "
          "black: bold circles, squares, triangles and bars, flat colour, strong geometry, loosely suggesting the "
          "theme of this news headline: 'Microsoft says hackers used an AI tool against tech systems'. "
          "Rules: no people, no faces, no hands, no text, no letters, no numbers, no logos; "
          "flat graphic art, not a photograph.")
t = time.time()
resp = gw.json("POST", "gemini", "/v1beta/models/gemini-3.1-flash-image:generateContent", {
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "16:9", "imageSize": "1K"}}},
    timeout=180)
parts = resp["candidates"][0]["content"]["parts"]
img = next(p["inlineData"] for p in parts if "inlineData" in p)
data = base64.b64decode(img["data"])
out = Path("/tmp/check15." + img["mimeType"].split("/")[1].replace("jpeg", "jpg"))
out.write_bytes(data)
print(f"gemini {img['mimeType']} {len(data)} bytes in {time.time() - t:.1f}s -> {out}")
print("usage:", json.dumps(resp.get("usageMetadata")), "model:", resp.get("modelVersion"))
