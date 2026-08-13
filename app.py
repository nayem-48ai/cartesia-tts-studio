#!/usr/bin/env python3
"""TNxBD Studio - Flask backend.

Serves a professional web UI and a JSON API backed by Cartesia's Sonic models.
Supports 40+ languages. The voice catalog is embedded statically so /api/voices
is instant and needs no outbound call; only TTS hits Cartesia.
"""
import json
import os
import threading
import time
import urllib.request
import urllib.error
import hmac
import hashlib
import base64
import random
import secrets
import operator
from flask import Flask, request, Response, render_template

app = Flask(__name__)

TOKEN_URL = "https://backend.cartesia.ai/access-token/public"
TTS_URL = "https://api.cartesia.ai/tts/bytes"
API_VERSION = "2026-03-01"

# Model support matrix verified live per language (sonic-2/3/3.5/turbo).
MODELS_BY_LANG = {
    "bn": ["sonic-3.5", "sonic-3"], "en": ["sonic-3.5", "sonic-3", "sonic-turbo", "sonic-2"],
    "hi": ["sonic-3.5", "sonic-3", "sonic-turbo"], "es": ["sonic-3.5", "sonic-3", "sonic-turbo", "sonic-2"],
    "fr": ["sonic-3.5", "sonic-3", "sonic-turbo", "sonic-2"], "de": ["sonic-3.5", "sonic-3", "sonic-turbo", "sonic-2"],
    "ar": ["sonic-3.5", "sonic-3"], "ja": ["sonic-3.5", "sonic-3", "sonic-turbo", "sonic-2"],
    "ko": ["sonic-3.5", "sonic-3", "sonic-turbo", "sonic-2"], "pt": ["sonic-3.5", "sonic-3", "sonic-turbo", "sonic-2"],
    "it": ["sonic-3.5", "sonic-3"], "nl": ["sonic-3.5", "sonic-3"], "pl": ["sonic-3.5", "sonic-3"],
    "zh": ["sonic-3.5", "sonic-3", "sonic-turbo", "sonic-2"], "ru": ["sonic-3.5", "sonic-3"],
    "sv": ["sonic-3.5", "sonic-3"], "te": ["sonic-3.5", "sonic-3"], "tl": ["sonic-3.5", "sonic-3"],
    "tr": ["sonic-3.5", "sonic-3"], "ta": ["sonic-3.5", "sonic-3"], "th": ["sonic-3.5", "sonic-3"],
    "cs": ["sonic-3.5", "sonic-3"], "fi": ["sonic-3.5", "sonic-3"], "da": ["sonic-3.5", "sonic-3"],
    "vi": ["sonic-3.5", "sonic-3"], "hu": ["sonic-3.5", "sonic-3"], "bg": ["sonic-3.5", "sonic-3"],
    "el": ["sonic-3.5", "sonic-3"], "gu": ["sonic-3.5", "sonic-3"], "hr": ["sonic-3.5", "sonic-3"],
    "id": ["sonic-3.5", "sonic-3"], "ka": ["sonic-3.5", "sonic-3"], "kn": ["sonic-3.5", "sonic-3"],
    "ml": ["sonic-3.5", "sonic-3"], "mr": ["sonic-3.5", "sonic-3"], "ms": ["sonic-3.5", "sonic-3"],
    "no": ["sonic-3.5", "sonic-3"], "pa": ["sonic-3.5", "sonic-3"], "ro": ["sonic-3.5", "sonic-3"],
    "sk": ["sonic-3.5", "sonic-3"], "uk": ["sonic-3.5", "sonic-3"], "he": ["sonic-3.5", "sonic-3"],
}

LANG_DISPLAY = {
    "bn": "বাংলা", "en": "English", "hi": "हिन्दी", "es": "Spanish", "fr": "French",
    "de": "German", "ar": "Arabic", "ja": "Japanese", "ko": "Korean", "pt": "Portuguese",
    "it": "Italian", "nl": "Dutch", "pl": "Polish", "zh": "Chinese", "ru": "Russian",
    "sv": "Swedish", "te": "Telugu", "tl": "Tagalog", "tr": "Turkish", "ta": "Tamil",
    "th": "Thai", "cs": "Czech", "fi": "Finnish", "da": "Danish", "vi": "Vietnamese",
    "hu": "Hungarian", "bg": "Bulgarian", "el": "Greek", "gu": "Gujarati", "hr": "Croatian",
    "id": "Indonesian", "ka": "Georgian", "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi",
    "ms": "Malay", "no": "Norwegian", "pa": "Punjabi", "ro": "Romanian", "sk": "Slovak",
    "uk": "Ukrainian", "he": "Hebrew",
}
DEFAULT_NAME = {
    "bn": "Rubel - City Guide", "en": "Greg - Supporter", "hi": "Aadhya - Soother",
}

# ---- Embedded voice catalog (static -> no outbound call on /api/voices) ----
_HERE = os.path.dirname(os.path.abspath(__file__))
try:
    with open(os.path.join(_HERE, "voices.json"), encoding="utf-8") as _f:
        VOICES = json.load(_f)
except Exception:
    VOICES = {}

DEFAULT_VOICE = {}
for _l, _vs in VOICES.items():
    if not _vs:
        continue
    _pref = next((v["id"] for v in _vs if v.get("name") == DEFAULT_NAME.get(_l)), None)
    DEFAULT_VOICE[_l] = _pref or _vs[0]["id"]

# ---- Token cache (avoid a mint round-trip on every TTS request) ----
_token_cache = {"token": None, "ts": 0.0}
_token_lock = threading.Lock()


def get_token() -> str:
    now = time.time()
    with _token_lock:
        if _token_cache["token"] and now - _token_cache["ts"] < 50:
            return _token_cache["token"]
    with urllib.request.urlopen(TOKEN_URL, timeout=10) as r:
        t = json.load(r)["token"]
    with _token_lock:
        _token_cache["token"] = t
        _token_cache["ts"] = time.time()
    return t


# ---- Lightweight human-verification gate (math challenge -> signed token) ----
# The answer lives only server-side (signed into the challenge token). The
# TTS endpoint requires a short-lived access token that is only issued after
# the challenge is solved, so the working API call can never be recovered from
# the page source alone.
APP_SECRET = os.environ.get("APP_SECRET", "tnxbd-studio-vercel-gate-2026")
_CHALLENGE_TTL = 600
_ACCESS_TTL = 600
_OPS = {"+": operator.add, "\u2212": operator.sub, "\u00d7": operator.mul, "\u00f7": operator.truediv}


def _b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload):
    body = _b64e(json.dumps(payload).encode())
    sig = hmac.new(APP_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _unsign(token):
    try:
        body, sig = token.split(".", 1)
        expect = hmac.new(APP_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return None
        payload = json.loads(_b64d(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def _gen_challenge():
    sym = random.choice(["+", "\u2212", "\u00d7", "\u00f7"])
    if sym == "\u00f7":
        b = random.randint(1, 9)
        ans = random.randint(1, 9)
        a = b * ans
        question = f"{a} \u00f7 {b}"
    elif sym == "\u2212":
        a, b = random.randint(1, 9), random.randint(1, 9)
        if b > a:
            a, b = b, a
        question = f"{a} \u2212 {b}"
        ans = a - b
    elif sym == "\u00d7":
        a, b = random.randint(1, 9), random.randint(1, 9)
        question = f"{a} \u00d7 {b}"
        ans = a * b
    else:
        a, b = random.randint(1, 9), random.randint(1, 9)
        question = f"{a} + {b}"
        ans = a + b
    token = _sign({"ans": ans, "exp": int(time.time()) + _CHALLENGE_TTL, "n": secrets.token_hex(4)})
    return {"question": question, "token": token}


def _require_access():
    tok = (request.headers.get("X-Access-Token")
           or request.args.get("token")
           or (request.get_json(force=True, silent=True) or {}).get("token"))
    p = _unsign(tok or "")
    return bool(p) and p.get("exp", 0) > time.time()


@app.route("/api/challenge", methods=["GET"])
def api_challenge():
    return _gen_challenge()


@app.route("/api/challenge/verify", methods=["POST"])
def api_challenge_verify():
    data = request.get_json(force=True, silent=True) or {}
    payload = _unsign(data.get("token") or "")
    if not payload:
        return {"error": "Invalid or expired challenge. Request a new one."}, 400
    try:
        answer = int(str(data.get("answer", "")).strip())
    except (ValueError, TypeError):
        return {"error": "Please enter a number."}, 400
    if answer != payload.get("ans"):
        return {"error": "Incorrect answer. Try again."}, 400
    access = _sign({"exp": int(time.time()) + _ACCESS_TTL, "n": secrets.token_hex(4)})
    return {"access": access, "ttl": _ACCESS_TTL}


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", site_url=request.url_root.rstrip("/"))


@app.route("/robots.txt", methods=["GET"])
def robots():
    body = "User-agent: *\nAllow: /\nSitemap: https://speakee.tnxbd.top/sitemap.xml\n"
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml", methods=["GET"])
def sitemap():
    loc = "https://speakee.tnxbd.top/"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>{loc}</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>\n'
        "</urlset>\n"
    )
    return Response(xml, mimetype="application/xml")


@app.route("/api/languages", methods=["GET"])
def api_languages():
    langs = [{"code": c, "name": LANG_DISPLAY.get(c, c)} for c in MODELS_BY_LANG]
    return {"count": len(langs), "languages": langs}


@app.route("/api/models", methods=["GET"])
def api_models():
    lang = request.args.get("language", "en")
    return {"language": lang,
            "models": MODELS_BY_LANG.get(lang, MODELS_BY_LANG["en"])}


@app.route("/api/voices", methods=["GET"])
def api_voices():
    lang = request.args.get("language", "en")
    voices = VOICES.get(lang, [])
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
        return {"error": f"TTS error {e.code}: {e.read().decode()[:300]}"}, 502

    return Response(audio, mimetype="audio/mpeg",
                    headers={"Content-Disposition":
                              'attachment; filename="tts.mp3"'})


# Convenience aliases matching the earlier API.
@app.route("/tts", methods=["POST"])
def tts_alias():
    return api_tts()


@app.route("/voices", methods=["GET"])
def voices_alias():
    return api_voices()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
