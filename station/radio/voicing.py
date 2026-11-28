"""Voice the queue's spoken items ahead of air (Plan B2, Task 4): for each ID, tease and break in the next two hours
that has no audio yet, write its words (breaks.script_for), voice them in the station's host voice (Gemini), store
an MP3 in the bucket and link it from the queue row. Identical words are voiced once. A failure leaves the item
unvoiced (the browser skips it); it never touches the songs."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from station.config import Prefs
from station.radio.breaks import script_for
from station.radio.model import StationConfig
from station.steps.publish import cache_control, put_object
from station.steps.voice import synthesize_request

SPOKEN = ("id", "id_tease", "break", "backsell")
VOICE_AHEAD = timedelta(hours=2)
BUDGET_S = 240  # per station per run: the build lock goes stale at 20 minutes (review I2)
MAX_FAILURES = 2  # after this many failed items, the rest wait for the next run


def gemini_tts(gw, text: str, host: dict) -> tuple[bytes, float]:
    """MP3 bytes and seconds for one host read: a Gemini prebuilt voice with a language (the form Tarik auditioned)."""
    req = {"contents": [{"parts": [{"text": text}]}],
           "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
               "languageCode": host.get("language", "en-US"), "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": host["voice"]}}}}}
    with tempfile.TemporaryDirectory() as tmp:
        wav, mp3 = Path(tmp) / "v.wav", Path(tmp) / "v.mp3"
        secs = synthesize_request(gw, req, wav)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "128k", str(mp3)], check=True)
        return mp3.read_bytes(), secs


def _song(db, cid: str | None) -> dict | None:
    if not cid:
        return None
    r = db.execute("SELECT COALESCE(matched_artist, artist), COALESCE(matched_title, title) FROM candidates WHERE id = ?", (cid,)).fetchone()
    return {"candidate_id": cid, "artist": r[0], "title": r[1]} if r else None


def voice_spoken(gw, db: sqlite3.Connection, station: StationConfig, prefs: Prefs, now: datetime,
                 tts=None, put=None, facts=None, budget_s: float = BUDGET_S) -> dict:
    tts = tts or (lambda text, host: gemini_tts(gw, text, host))
    put = put or (lambda key, data: put_object(gw, prefs.hosting.bucket, key, data, "audio/mpeg", cache_control(key)))
    facts = facts or (lambda cid: [])
    host = station.host or {"voice": prefs.voices.host, "language": "en-US"}
    tz = ZoneInfo(prefs.station.timezone)
    rows = db.execute(f"SELECT starts_at, kind, duration_ms FROM queue WHERE station_id = ? AND kind IN ({','.join('?' * len(SPOKEN))}) "
                      "AND starts_at >= ? AND starts_at < ? AND audio_url IS NULL ORDER BY starts_at",
                      (station.id, *SPOKEN, now.isoformat(), (now + VOICE_AHEAD).isoformat())).fetchall()
    voiced, notes, made, failures = 0, [], {}, 0
    deadline = time.monotonic() + budget_s
    for starts_at, kind, slot_ms in rows:
        if time.monotonic() >= deadline or failures >= MAX_FAILURES:
            notes.append(f"voicing stopped ({'time budget used' if failures < MAX_FAILURES else 'repeated failures'}): "
                         "the rest wait for the next run")
            break
        try:
            prev = [s for s in (_song(db, c) for (c,) in reversed(db.execute(
                "SELECT candidate_id FROM queue WHERE station_id = ? AND kind = 'song' AND starts_at < ? ORDER BY starts_at DESC LIMIT 2",
                (station.id, starts_at)).fetchall())) if s]
            nxt = db.execute("SELECT candidate_id FROM queue WHERE station_id = ? AND kind = 'song' AND starts_at > ? ORDER BY starts_at LIMIT 1",
                             (station.id, starts_at)).fetchone()
            item = {"kind": kind, "starts_at": datetime.fromisoformat(starts_at).astimezone(tz).isoformat()}  # local hour for IDs/teases
            script = script_for(gw, db, station, item, prev, _song(db, nxt[0]) if nxt else None, prefs,
                                facts(prev[-1]["candidate_id"]) if prev else [], target_s=(slot_ms or 0) / 1000 or None)
            if not script["text"]:
                continue
            key = f"audio/radio/{station.id}/" + hashlib.sha1(f"{host['voice']}|{host.get('language')}|{script['text']}".encode()).hexdigest()[:16] + ".mp3"
            if key not in made:
                old = db.execute("SELECT audio_ms FROM queue WHERE station_id = ? AND audio_url = ?", (station.id, "/" + key)).fetchone()
                if old:
                    made[key] = old[0]  # the same words were voiced before: reuse the file
                else:
                    mp3, secs = tts(script["text"], host)
                    put(key, mp3)
                    made[key] = round(secs * 1000)
            db.execute("UPDATE queue SET text = ?, sources = ?, audio_url = ?, audio_ms = ? WHERE station_id = ? AND starts_at = ?",
                       (script["text"], json.dumps(script["sources"]), "/" + key, made[key], station.id, starts_at))
            voiced += 1
        except Exception as e:  # noqa: BLE001 — one item's voice must never stop the station; the browser skips it
            failures += 1
            notes.append(f"voice failed for {kind} at {starts_at}: {type(e).__name__}: {str(e)[:120]}")
    db.commit()
    return {"voiced": voiced, "notes": notes}
