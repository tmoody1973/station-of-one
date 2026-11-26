"""Table Step 0: the same Anchor/Uncle exchange in four Gemini voice pairs, for Tarik to pick.
Run on the Sprite: uv run python spikes/table_voice_samples.py data/table/2026-11-26"""
import base64
import json
import subprocess
import sys
from pathlib import Path

from station.gateway import Gateway
from station.steps.voice import PATH, _voice

STYLE = {"Anchor": "calm, careful public-radio host; warm, measured, brisk",
         "Uncle": "confident and playful know-it-all at a backyard barbecue, a little conspiratorial, brisk"}
PAIRS = {"A": ("Iapetus", "Algenib"), "B": ("Erinome", "Fenrir"), "C": ("Sadaltager", "Puck"), "D": ("Schedar", "Gacrux")}

run = Path(sys.argv[1])
parts = json.loads((run / "script.json").read_text())["parts"]
turns = [*parts[1]["turns"], *parts[2]["turns"]]  # opening + round 1
out_dir = run / "voice_samples"
out_dir.mkdir(exist_ok=True)
gw = Gateway()
for name, (anchor, uncle) in PAIRS.items():
    req = {"contents": [{"role": "user", "parts": [{"text": t["text"], "speech_metadata": {"speaker": t["speaker"], "style": STYLE[t["speaker"]]}} for t in turns]}],
           "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
               {"speaker": "Anchor", "voiceConfig": _voice(anchor)}, {"speaker": "Uncle", "voiceConfig": _voice(uncle)}]}}}}
    resp = gw.json("POST", "gemini", PATH, req, timeout=180)
    wav = out_dir / f"pair_{name}.wav"
    wav.write_bytes(base64.b64decode(resp["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]))
    mp3 = out_dir / f"table_voices_{name}_{anchor}_{uncle}.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-b:a", "96k", str(mp3)], check=True)
    print(mp3.name, round(int(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
                                              capture_output=True, text=True).stdout.split(".")[0])), "s")
