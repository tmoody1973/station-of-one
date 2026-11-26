#!/usr/bin/env bash
# Check 4: can the Sprite run the heavy tools?
#  (a) ffmpeg joins two clips, normalizes loudness, writes a mono MP3 with embedded chapters
#  (b) a headless browser renders one 1080x1920 frame
# Uses generated test tones only. No API calls, no keys.
# Run:  sprite exec -s brave-indigo-lion --stdin -- bash -s < spikes/check4_heavy_tools.sh
# Commands follow docs/RESEARCH-NOTES.md §6.12 (ffmpeg) and Playwright's install docs.
set -euo pipefail
W=~/spikes/check4; mkdir -p "$W"; cd "$W"
t() { date +%s.%N; }
el() { python3 -c "print(f'{$2-$1:.1f}s')"; }

echo "== (a) ffmpeg"
s=$(t)
if ! command -v ffmpeg >/dev/null; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg > /dev/null
fi
echo "install: $(el $s $(t))  $(ffmpeg -version | head -1)"

# Two "chapters" in Gemini's output format: 24 kHz, mono, 16-bit WAV.
ffmpeg -y -loglevel error -f lavfi -i "sine=frequency=440:duration=3" -ar 24000 -ac 1 -c:a pcm_s16le seg_000.wav
ffmpeg -y -loglevel error -f lavfi -i "sine=frequency=660:duration=4.5" -ar 24000 -ac 1 -c:a pcm_s16le seg_001.wav
head -c 4 seg_000.wav; echo "  <- first 4 bytes (RIFF = already WAV)"

# Chapter file from real segment durations (chapter_per_file is not in ffmpeg 8.0.1).
printf 'ffconcat version 1.0\nfile seg_000.wav\nfile seg_001.wav\n' > list.txt
{
  echo ';FFMETADATA1'
  echo 'title=Spike newscast'
  start=0; i=0
  for f in seg_000.wav seg_001.wav; do
    d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
    end=$(python3 -c "print($start + round($d*1000))")
    printf '[CHAPTER]\nTIMEBASE=1/1000\nSTART=%s\nEND=%s\ntitle=Chapter %s\n' "$start" "$end" "$i"
    start=$end; i=$((i+1))
  done
} > chapters.ffmeta

s=$(t)
ffmpeg -y -loglevel error -f concat -safe 0 -i list.txt -i chapters.ffmeta \
  -map 0:a -map_metadata 1 -map_chapters 1 \
  -af loudnorm=I=-16:TP=-1.5:LRA=11 \
  -ar 44100 -ac 1 -c:a libmp3lame -b:a 64k -id3v2_version 3 newscast.mp3
echo "join+loudnorm+encode: $(el $s $(t))  size: $(stat -c %s newscast.mp3) bytes"
ffprobe -v error -show_chapters -of compact=p=0 newscast.mp3
ffprobe -v error -show_entries stream=sample_rate,channels:format=duration -of compact=p=0 newscast.mp3
python3 - <<'PY'
# Look for the raw ID3v2 CHAP/CTOC frames in the file header.
b = open("newscast.mp3", "rb").read(4096)
print("ID3 header:", b[:3], "| CTOC frame:", b"CTOC" in b, "| CHAP frames:", b.count(b"CHAP"))
PY

echo "== (b) headless browser"
s=$(t)
[ -d venv ] || uv venv -q venv
. venv/bin/activate
uv pip install -q playwright
playwright install --with-deps chromium > install-browser.log 2>&1 || { echo "browser install FAILED"; tail -20 install-browser.log; exit 1; }
echo "install: $(el $s $(t))  $(playwright --version)"

cat > frame.html <<'HTML'
<!doctype html><html><body style="margin:0;width:1080px;height:1920px;background:#141414;color:#fff;
font-family:sans-serif;display:flex;align-items:center;justify-content:center;font-size:96px">
2,140 posts read</body></html>
HTML
s=$(t)
python3 - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1080, "height": 1920})
    pg.goto("file://" + __import__("os").path.abspath("frame.html"))
    pg.screenshot(path="frame.png")
    b.close()
PY
echo "render one frame: $(el $s $(t))"
python3 -c "import struct;d=open('frame.png','rb').read(24);print('frame.png size:',struct.unpack('>II',d[16:24]))"
echo "== disk"; du -sh "$W" ~/.cache/ms-playwright 2>/dev/null; df -h / | tail -1
