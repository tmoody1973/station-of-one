"""Check 2b: why the voices sound slow, and which voice/style sounds like a newscast.

Same single-speaker newscast paragraph, several voice + style variants through the Gemini
connector (generateContent, the endpoint check 2 proved). Reports words per minute per clip.
Per Google's prompting guide: test with an empty style first; style controls pace.
Cost: ~6 clips of ~20 s each, about $0.03 on the paid tier.

Run:  sprite exec -s brave-indigo-lion -- bash -c 'cd ~/spikes && python3 check2b_voice_pace.py'
"""
import base64
import json
import os
import wave

from gw import call, connection

MODEL = "gemini-3.8-flash-tts"
SCRIPT = ("Good morning. It's nine o'clock. Mozilla says it will end support for Firefox "
          "E-S-R one-fifteen on March first, according to the company's release calendar. "
          "Posters on Hacker News say the change mostly affects schools and businesses that "
          "lock their browser versions. Mozilla's own support page lists the dates.")
BRISK = "brisk, warm, conversational news read"
VARIANTS = [
    ("charon_nostyle", "Charon", ""),
    ("charon_brisk", "Charon", BRISK),
    ("rasalgethi_brisk", "Rasalgethi", BRISK),
    ("iapetus_brisk", "Iapetus", BRISK),
    ("kore_brisk", "Kore", BRISK),
    ("alnilam_brisk", "Alnilam", BRISK),
]
OUT = os.path.expanduser("~/spikes/check2b")
os.makedirs(OUT, exist_ok=True)
words = len(SCRIPT.split())
base = connection("gemini")["gateway_base_url"].rstrip("/")
print(f"script: {words} words")

for name, voice, style in VARIANTS:
    part = {"text": SCRIPT}
    if style:
        part["speech_metadata"] = {"style": style}
    req = {"contents": [{"role": "user", "parts": [part]}],
           "generationConfig": {"responseModalities": ["AUDIO"],
                                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    status, _, raw = call("POST", f"{base}/v1beta/models/{MODEL}:generateContent", req, timeout=180)
    if status != 200:
        print(f"{name:18s} -> {status} {raw.decode()[:300]}")
        continue
    resp = json.loads(raw)
    data = base64.b64decode(resp["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    path = f"{OUT}/{name}.wav"
    open(path, "wb").write(data)
    with wave.open(path) as w:
        secs = w.getnframes() / w.getframerate()
    print(f"{name:18s} voice={voice:10s} style={style or '(none)':38s} {secs:5.1f}s  {words / secs * 60:4.0f} wpm")
