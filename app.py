#!/usr/bin/env python3
"""Cartesia TTS Studio - Flask backend.

Serves a professional web UI and a JSON API backed by Cartesia's Sonic models.
Languages: Bangla (bn), English (en), Hindi (hi).
"""
import json
import re
import threading
import urllib.request
from flask import Flask, request, Response, render_template

app = Flask(__name__)

TOKEN_URL = "https://backend.cartesia.ai/access-token/public"
TTS_URL = "https://api.cartesia.ai/tts/bytes"
CATALOG_URL = ("https://www.cartesia.ai/_astro/voices-catalog.C5Lr5Mrb.js"
               "?dpl=dpl_Cmdf7RW7WxQphKmqQx2WxqzC1XhH")
API_VERSION = "2026-03-01"

# Model support matrix verified live against the API.
MODELS_BY_LANG = {
    "bn": ["sonic-3.5", "sonic-3"],
    "en": ["sonic-3.5", "sonic-3", "sonic-turbo", "sonic-2"],
    "hi": ["sonic-3.5", "sonic-3", "sonic-turbo"],
}
DEFAULT_VOICE = {
    "bn": "2ba861ea-7cdc-43d1-8608-4045b5a41de5",  # Rubel - City Guide
    "en": "a0e99841-438c-4a64-b679-ae501e7d6091",  # Greg - Supporter
    "hi": "f91ab3e6-5071-4e15-b016-cde6f2bcd222",  # Aadhya - Soother
}
LANG_NAMES = {"bn": "Bangla", "en": "English", "hi": "Hindi"}

_voices_cache = {"data": None, "ts": 0}
_voices_lock = threading.Lock()


def get_token() -> str:
    with urllib.request.urlopen(TOKEN_URL, timeout=10) as r:
        return json.load(r)["token"]


def load_voices():
    """Fetch and parse the public voice catalog (cached in memory)."""
    with _voices_lock:
        import time
        if _voices_cache["data"] and time.time() - _voices_cache["ts"] < 3600:
            return _voices_cache["data"]
    try:
        js = urllib.request.urlopen(CATALOG_URL, timeout=15).read().decode()
        rows = re.findall(
            r'id:`([0-9a-f-]{36})`,name:`([^`]*)`,gender:`([^`]*)`,'
            r'language:`([^`]*)`', js)
        by_lang = {}
        for i, n, g, l in rows:
            by_lang.setdefault(l, []).append(
                {"id": i, "name": n, "gender": g})
        with _voices_lock:
            _voices_cache["data"] = by_lang
            _voices_cache["ts"] = time.time()
        return by_lang
    except Exception:
        # Fallback snapshot if the catalog is unreachable.
        return {
            "bn": [
                {"id": "59ba7dee-8f9a-432f-a6c0-ffb33666b654",
                 "name": "Pooja - Everyday Assistant", "gender": "feminine"},
                {"id": "2ba861ea-7cdc-43d1-8608-4045b5a41de5",
                 "name": "Rubel - City Guide", "gender": "masculine"},
            ],
            "en": [{"id": "a0e99841-438c-4a64-b679-ae501e7d6091",
                    "name": "Greg - Supporter", "gender": "masculine"}],
            "hi": [{"id": "f91ab3e6-5071-4e15-b016-cde6f2bcd222",
                    "name": "Aadhya - Soother", "gender": "feminine"}],
        }


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html",
                           languages=LANG_NAMES,
                           models=MODELS_BY_LANG,
                           defaults=DEFAULT_VOICE)


@app.route("/api/models", methods=["GET"])
def api_models():
    lang = request.args.get("language", "en")
    return {"language": lang,
            "models": MODELS_BY_LANG.get(lang, MODELS_BY_LANG["en"])}


@app.route("/api/voices", methods=["GET"])
def api_voices():
    lang = request.args.get("language", "en")
    voices = load_voices().get(lang, [])
    return {"language": lang, "count": len(voices), "voices": voices}


@app.route("/api/tts", methods=["POST"])
def api_tts():
    body = request.get_json(force=True, silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return {"error": "missing 'text'"}, 400

    language = body.get("language", "en")
    if language not in MODELS_BY_LANG:
        return {"error": f"unsupported language '{language}'"}, 400
    model = body.get("model") or MODELS_BY_LANG[language][0]
    if model not in MODELS_BY_LANG[language]:
        return {"error": f"model '{model}' not supported for '{language}'"}, 400

    voice_id = body.get("voice_id") or DEFAULT_VOICE.get(language)
    sample_rate = int(body.get("sample_rate", 44100))

    token = get_token()
    payload = json.dumps({
        "model_id": model,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "output_format": {"container": "mp3", "encoding": "mp3",
                          "sample_rate": sample_rate},
        "language": language,
    }).encode()

    req = urllib.request.Request(
        TTS_URL, data=payload, method="POST",
        headers={"Cartesia-Version": API_VERSION, "x-api-key": token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        return {"error": f"cartesia {e.code}: {e.read().decode()[:300]}"}, 502

    return Response(audio, mimetype="audio/mpeg",
                    headers={"Content-Disposition":
                              'attachment; filename="tts.mp3"'})


# Convenience aliases matching the earlier README/API.
@app.route("/tts", methods=["POST"])
def tts_alias():
    return api_tts()


@app.route("/voices", methods=["GET"])
def voices_alias():
    return api_voices()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
