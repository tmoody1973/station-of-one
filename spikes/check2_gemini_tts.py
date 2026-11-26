"""Check 2: Gemini two-speaker TTS through the Google Gemini connector.

Probes:
  A. POST /v1beta/models/gemini-3.8-flash-tts:generateContent  (multi-speaker, prebuilt voices)
  B. POST /v1beta/interactions                                   (same dialogue; does the gateway forward it?)
Saves each clip as a WAV and reports format, size and duration.
Shapes from docs/RESEARCH-NOTES.md §6.1 and §6.3 (https://aistudio.google.com/docs/speech-generation.md).
Cost: two ~10 s clips. Free tier: $0. Paid tier: under $0.01 total.

Run:  sprite exec -s brave-indigo-lion -- bash -c 'cd ~/spikes && python3 check2_gemini_tts.py'
"""
import base64
import json
import os
import time
import wave

from gw import call, connection

MODEL = "gemini-3.8-flash-tts"
HOST, REPORTER = "Host", "Reporter"
HOST_VOICE, REPORTER_VOICE = "Kore", "Charon"  # chosen by ear, Nov 26
STYLE = "brisk, warm, conversational news read"
TURNS = [
    (HOST, "It's nine o'clock. Here's the last hour on your internet. Our lead: Mozilla is ending "
           "support for an older version of Firefox. Here's our reporter."),
    (REPORTER, "Mozilla says Firefox E-S-R one-fifteen reaches end of support on March first, according "
               "to the company's release calendar. Posters on Hacker News say the change mostly hits "
               "schools and businesses that lock their browser versions."),
    (HOST, "Mozilla's support page lists the dates. <short pause> In other news this hour..."),
]
OUT = os.path.expanduser("~/spikes/check2")
os.makedirs(OUT, exist_ok=True)

conn = connection("gemini")
base = conn["gateway_base_url"].rstrip("/")
print("usage_snippet:\n", conn.get("usage_snippet"))


def describe(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)
    print(f"  saved {path}: {len(data)} bytes, first 4 bytes {data[:4]!r}")
    if data[:4] == b"RIFF":
        with wave.open(path) as w:
            print(f"  WAV: {w.getframerate()} Hz, {w.getnchannels()} ch, {w.getsampwidth() * 8}-bit, "
                  f"{w.getnframes() / w.getframerate():.2f} s")


def show_error(status: int, raw: bytes) -> None:
    print(f"  -> {status}: {raw.decode(errors='replace')[:1500]}")


# A. generateContent
req_a = {
    "contents": [{"role": "user", "parts": [
        {"text": text, "speech_metadata": {"speaker": who, "style": STYLE}} for who, text in TURNS]}],
    "generationConfig": {
        "responseModalities": ["AUDIO"],
        "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
            {"speaker": HOST, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": HOST_VOICE}}},
            {"speaker": REPORTER, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": REPORTER_VOICE}}},
        ]}},
    },
}
print("\nA. generateContent request:\n", json.dumps(req_a, indent=1))
t = time.time()
status, headers, raw = call("POST", f"{base}/v1beta/models/{MODEL}:generateContent", req_a, timeout=180)
print(f"A -> {status} in {time.time() - t:.1f}s, response {len(raw)} bytes")
if status == 200:
    resp = json.loads(raw)
    part = resp["candidates"][0]["content"]["parts"][0]
    inline = part.get("inlineData") or part.get("inline_data")
    print("  inlineData.mimeType:", inline.get("mimeType") or inline.get("mime_type"))
    print("  usageMetadata:", json.dumps(resp.get("usageMetadata")))
    print("  other top-level keys:", [k for k in resp if k != "candidates"])
    describe(f"{OUT}/a_generatecontent.wav", base64.b64decode(inline["data"]))
else:
    show_error(status, raw)

# B. Interactions API
req_b = {
    "model": MODEL,
    "input": [{"type": "user_input", "content": [
        {"type": "text", "text": text,
         "annotations": [{"type": "speech_metadata", "speaker": who, "style": STYLE}]} for who, text in TURNS]}],
    "response_format": {"type": "audio"},
    "generation_config": {"speech_config": {"speakers": [
        {"speaker": HOST, "voice": HOST_VOICE}, {"speaker": REPORTER, "voice": REPORTER_VOICE}]}},
}
print("\nB. interactions request: same dialogue, Interactions shape")
t = time.time()
status, headers, raw = call("POST", f"{base}/v1beta/interactions", req_b, timeout=180)
print(f"B -> {status} in {time.time() - t:.1f}s, response {len(raw)} bytes")
if status == 200:
    resp = json.loads(raw)
    print("  top-level keys:", list(resp))
    audio = (resp.get("output_audio") or {}).get("data")
    if not audio:  # documented REST shape: steps[].type == model_output -> content[].type == audio
        for step in resp.get("steps", []):
            if step.get("type") == "model_output":
                for c in step.get("content", []):
                    if c.get("type") == "audio":
                        audio = c.get("data")
    if audio:
        describe(f"{OUT}/b_interactions.wav", base64.b64decode(audio))
    else:
        print("  no audio found; first 1500 chars:", raw.decode()[:1500])
else:
    show_error(status, raw)
