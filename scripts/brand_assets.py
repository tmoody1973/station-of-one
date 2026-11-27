"""Draw the ONE 1.0 FM favicon (assets/logo-one.png, 180 px) and podcast cover (assets/cover-one.png, 3000 px) in Chrome.
Run: python3 scripts/brand_assets.py assets   (renamed from WONE on Nov 27: real US call signs start with K or W)"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
out = Path(sys.argv[1])
FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Jost:wght@500;700;800&display=swap">'
LOGO = f"""<!doctype html><html><head>{FONTS}<style>html,body{{margin:0;background:transparent}}
.id{{width:180px;height:180px;display:flex;flex-direction:column;font-family:'Archivo Black';border-radius:24px;overflow:hidden}}
.t{{flex:1;background:#111;color:#FFC629;font-size:78px;display:flex;align-items:center;justify-content:center;line-height:1}}
.b{{flex:1;background:#E4002B;color:#fff;font-size:70px;letter-spacing:3px;display:flex;align-items:center;justify-content:center;line-height:1}}</style></head>
<body><div class="id"><div class="t">1.0</div><div class="b">ONE</div></div></body></html>"""
COVER = f"""<!doctype html><html><head>{FONTS}<style>html,body{{margin:0}}
.c{{width:3000px;height:3000px;background:#ece4cf;position:relative;overflow:hidden;font-family:Jost}}
.circle{{position:absolute;width:1500px;height:1500px;border-radius:50%;background:#f4c20d;right:-260px;top:-300px}}
.square{{position:absolute;width:460px;height:460px;background:#d62d20;left:2250px;top:1640px}}
.bar{{position:absolute;width:2600px;height:120px;background:#111;left:-200px;top:1360px;transform:rotate(-12deg)}}
.tri{{position:absolute;left:2470px;top:2180px;width:0;height:0;border-left:330px solid transparent;border-right:330px solid transparent;border-bottom:560px solid #1d4e9e}}
.id{{position:absolute;left:220px;top:240px;display:flex;flex-direction:column;font-family:'Archivo Black';border:18px solid #111}}
.t{{background:#111;color:#FFC629;font-size:420px;padding:20px 120px 0;line-height:1;text-align:center}}
.b{{background:#E4002B;color:#fff;font-size:380px;padding:30px 120px 40px;letter-spacing:16px;line-height:1;text-align:center}}
.title{{position:absolute;left:220px;bottom:520px;font-size:300px;font-weight:800;line-height:.95;color:#111;letter-spacing:-8px}}
.sub{{position:absolute;left:230px;bottom:300px;font-size:88px;font-weight:700;color:#3b3833;letter-spacing:6px}}</style></head>
<body><div class="c"><div class="circle"></div><div class="bar"></div><div class="square"></div><div class="tri"></div>
<div class="id"><div class="t">1.0</div><div class="b">ONE</div></div>
<div class="title">The Hourly<br>Scroll</div><div class="sub">ONE 1.0 FM · machine-edited · synthetic voices</div></div></body></html>"""
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    for name, html, size, transparent in (("logo-one.png", LOGO, 180, True), ("cover-one.png", COVER, 3000, False)):
        pg = b.new_page(viewport={"width": size, "height": size})
        pg.set_content(html, wait_until="networkidle"); pg.wait_for_timeout(800)
        pg.screenshot(path=str(out / name), omit_background=transparent, clip={"x": 0, "y": 0, "width": size, "height": size})
        pg.close()
    b.close()
