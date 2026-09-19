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
import re
import operator
from flask import Flask, request, Response, render_template, redirect

app = Flask(__name__)

# Only the custom domain is public; redirect every other host (vercel.app defaults,
# auto deployment URLs, etc.) to speakee.tnxbd.top so a single canonical site exists.
CANONICAL_HOST = "speakee.tnxbd.top"
ALLOWED_HOSTS = {CANONICAL_HOST, "localhost", "127.0.0.1"}
SITE_URL = "https://" + CANONICAL_HOST

@app.before_request
def enforce_canonical_host():
    host = request.host.split(":")[0]
    if host not in ALLOWED_HOSTS:
        return redirect("https://" + CANONICAL_HOST + request.full_path, code=301)

TOKEN_URL = "https://backend.cartesia.ai/access-token/public"
TTS_URL = "https://api.cartesia.ai/tts/bytes"
STT_URL = "https://api.cartesia.ai/stt"
STT_MODEL = "ink-whisper"
API_VERSION = "2026-03-01"

# ---- Speech-to-text (Cartesia Ink, same free token flow as TTS) ----
# Vercel serverless requests cap at ~4.5MB, so uploads must stay small.
STT_MAX_BYTES = 4 * 1024 * 1024
STT_DEFAULT_LANG = "auto"
STT_AUTO = "auto"
STT_LANGS = (
    "bn", "en", "hi", "ur", "es", "fr", "de", "ar", "ja", "ko", "pt",
    "it", "nl", "pl", "zh", "ru", "tr", "vi", "id", "ms", "ta", "te",
    "mr", "gu", "pa", "ml", "kn", "th", "tl", "uk", "he", "fa", "ne",
    "si", "as",
)
STT_LANG_DISPLAY = {
    "bn": "বাংলা", "en": "English", "hi": "हिन्दी", "ur": "اردو",
    "es": "Spanish", "fr": "French", "de": "German", "ar": "Arabic",
    "ja": "Japanese", "ko": "Korean", "pt": "Portuguese", "it": "Italian",
    "nl": "Dutch", "pl": "Polish", "zh": "Chinese", "ru": "Russian",
    "tr": "Turkish", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay",
    "ta": "Tamil", "te": "Telugu", "mr": "Marathi", "gu": "Gujarati",
    "pa": "Punjabi", "ml": "Malayalam", "kn": "Kannada", "th": "Thai",
    "tl": "Tagalog", "uk": "Ukrainian", "he": "Hebrew", "fa": "Persian",
    "ne": "Nepali", "si": "Sinhala", "as": "Assamese",
}

# Model support matrix verified live per language (sonic-2/3/3.5/turbo).
MODELS_BY_LANG = {
    "uid": ["sonic-3.5", "sonic-3", "sonic-turbo", "sonic-2"],
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
    "uid": "UID", "bn": "বাংলা", "en": "English", "hi": "हिन्दी", "es": "Spanish", "fr": "French",
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

# ---- Full public voice library (868 voices) for the /library browser ----
try:
    with open(os.path.join(_HERE, "voice_library_all.json"), encoding="utf-8") as _f:
        VOICE_LIBRARY = json.load(_f)
except Exception:
    VOICE_LIBRARY = []

# ---- Token cache (avoid a mint round-trip on every TTS request) ----
_token_cache = {"token": None, "ts": 0.0}
_token_lock = threading.Lock()


def get_token() -> str:
    # If a real Cartesia account key is configured it is used directly (required for
    # private/owned voices); otherwise fall back to the public token endpoint.
    acct = os.environ.get("CARTESIA_API_KEY")
    if acct:
        return acct
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


# ---- Voice-style controls (mirrors play.cartesia.ai) ----
# Cartesia `generation_config` is supported on sonic-3 / sonic-3.5 only.
# Defaults match the playground: speed 1, volume 1, emotion neutral.
GENCFG_MODELS = ("sonic-3", "sonic-3.5")
EMOTIONS = {
    "neutral", "happy", "excited", "enthusiastic", "elated", "euphoric",
    "triumphant", "amazed", "surprised", "flirtatious", "curious", "content",
    "peaceful", "serene", "calm", "grateful", "affectionate", "trust",
    "sympathetic", "anticipation", "mysterious", "angry", "mad", "outraged",
    "frustrated", "agitated", "threatened", "disgusted", "contempt", "envious",
    "sarcastic", "ironic", "sad", "dejected", "melancholic", "disappointed",
    "hurt", "guilty", "bored", "tired", "rejected", "nostalgic", "wistful",
    "apologetic", "hesitant", "insecure", "confused", "resigned", "anxious",
    "panicked", "alarmed", "scared", "proud", "confident", "distant",
    "skeptical", "contemplative", "determined",
}
PRIMARY_EMOTIONS = ("neutral", "calm", "angry", "content", "sad", "scared")
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


@app.route("/library", methods=["GET"])
def library():
    return render_template("library.html", site_url=request.url_root.rstrip("/"))


@app.route("/api/library", methods=["GET"])
def api_library():
    # Normalise each voice to the fields the browser needs.
    out = []
    for v in VOICE_LIBRARY:
        out.append({
            "id": v.get("id"),
            "name": v.get("name"),
            "description": v.get("description") or "",
            "language": v.get("language"),
            "gender": v.get("gender") or "",
            "tag": "Pro" if v.get("is_pro") else "Free",
            "mode": v.get("mode") or "",
            "country": v.get("country") or "",
            "owner": bool(v.get("is_owner")),
        })
    return {"count": len(out), "voices": out}


@app.route("/robots.txt", methods=["GET"])
def robots():
    body = "User-agent: *\nAllow: /\nSitemap: https://speakee.tnxbd.top/sitemap.xml\n"
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml", methods=["GET"])
def sitemap():
    pages = [("/", "1.0"), ("/library", "0.8"), ("/stt", "0.9")]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, pri in pages:
        lines.append(
            '  <url><loc>https://speakee.tnxbd.top%s</loc>'
            '<changefreq>weekly</changefreq><priority>%s</priority></url>' % (path, pri)
        )
    lines.append("</urlset>")
    return Response("\n".join(lines), mimetype="application/xml")


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


@app.route("/stt", methods=["GET"])
def stt_page():
    return render_template("stt.html", site_url=request.url_root.rstrip("/"))


@app.route("/api/stt/languages", methods=["GET"])
def api_stt_languages():
    langs = [{"code": STT_AUTO, "name": "✨ Auto detect"}]
    langs += [{"code": c, "name": STT_LANG_DISPLAY.get(c, c)} for c in STT_LANGS]
    return {"count": len(langs), "languages": langs, "default": STT_DEFAULT_LANG}


def _truthy(v, default=True):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ---- STT engine 1 (primary): Cloudflare whisper-large-v3-turbo ----
# Free, auto-detects language when omitted, handles mixed-language speech,
# optional VAD preprocessing to keep noise out. Token from env (server only).
CF_ACCT_ID = os.environ.get("CF_ACCT_ID", "f1df706095bba37d66e667b6fc546930")
CF_WHISPER_MODEL = "@cf/openai/whisper-large-v3-turbo"


def _cf_stt(audio: bytes, language: str, word_ts: bool, vad: bool):
    token = os.environ.get("CF_AI_TOKEN")
    if not token:
        return None, "STT engine not configured"
    payload = {"audio": base64.b64encode(audio).decode(),
               "vad_filter": bool(vad)}
    if language != STT_AUTO:
        payload["language"] = language
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCT_ID}"
        f"/ai/run/{CF_WHISPER_MODEL}",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        return None, f"STT engine error {e.code}: {e.read().decode()[:200]}"
    if not data.get("success", True):
        errs = data.get("errors") or [{"message": "unknown engine error"}]
        return None, f"STT engine error: {errs[0].get('message', errs)}"[:300]
    res = data.get("result") or {}
    info = res.get("transcription_info") or {}
    out = {"text": (res.get("text") or "").strip(),
           "language": info.get("language") or language,
           "duration": info.get("duration"),
           "engine": "whisper-large-v3-turbo"}
    if info.get("language_probability") is not None:
        out["detection_confidence"] = round(float(info["language_probability"]), 3)
    if word_ts:
        words = []
        for seg in res.get("segments") or []:
            for w in seg.get("words") or []:
                words.append({"word": str(w.get("word") or "").strip(),
                              "start": w.get("start"), "end": w.get("end")})
        words = [w for w in words if w["word"]]
        out["words"] = words
        out["word_count"] = len(words)
    return out, None


# ---- STT engine 2 (fallback): Cartesia ink-whisper, explicit language ----
def _cartesia_stt(audio: bytes, name: str, mime: str, language: str, word_ts: bool):
    token = get_token()
    boundary = "stt-%s" % secrets.token_hex(8)

    def _field(nm, val):
        return (f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{nm}"\r\n\r\n{val}\r\n').encode()

    parts = [_field("model", STT_MODEL), _field("language", language)]
    if word_ts:
        parts.append(
            (f"--{boundary}\r\nContent-Disposition: form-data; "
             f'name="timestamp_granularities[]"\r\n\r\nword\r\n').encode())
    parts.append(
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
         f'filename="{name}"\r\nContent-Type: {mime}\r\n\r\n').encode()
        + audio + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        STT_URL, data=body, method="POST",
        headers={"Cartesia-Version": API_VERSION, "x-api-key": token,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        return None, f"STT error {e.code}: {e.read().decode()[:300]}"

    out = {"text": (data.get("text") or "").strip(),
           "language": data.get("language", language),
           "duration": data.get("duration"),
           "request_id": data.get("request_id"),
           "engine": "ink-whisper"}
    if word_ts and isinstance(data.get("words"), list):
        out["words"] = [{"word": w.get("word"), "start": w.get("start"),
                         "end": w.get("end")} for w in data["words"]]
        out["word_count"] = len(out["words"])
    return out, None


@app.route("/api/stt", methods=["POST"])
def api_stt():
    # multipart form (file + options) so browsers AND realtime chunk
    # recorders can POST audio directly, same style as /api/tts.
    # language="auto" (default) detects the spoken language per request.
    language = (request.form.get("language") or request.args.get("language")
                or STT_DEFAULT_LANG).strip().lower()
    if language != STT_AUTO and language not in STT_LANGS:
        return {"error": f"unsupported language '{language}'"}, 400
    word_ts = _truthy(request.form.get("word_timestamps",
                                      request.args.get("word_timestamps", "1")))
    vad = _truthy(request.form.get("vad_filter",
                                  request.args.get("vad_filter", "1")))

    f = request.files.get("file")
    if f is None or not (f.filename or "").strip():
        return {"error": "missing 'file': upload audio as multipart form field 'file'"}, 400
    audio = f.read()
    if not audio:
        return {"error": "empty audio file"}, 400
    if len(audio) > STT_MAX_BYTES:
        return {"error": f"audio too large ({len(audio)} bytes): keep clips under 4MB"}, 413

    out, err = _cf_stt(audio, language, word_ts, vad)
    if err and language != STT_AUTO:
        # Fallback keeps explicit-language requests working if the
        # primary engine is throttled or unconfigured.
        name = os.path.basename(f.filename or "audio").strip() or "audio"
        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[-80:] or "audio"
        out, err = _cartesia_stt(audio, name, f.mimetype or "audio/webm",
                                 language, word_ts)
    if err:
        return {"error": err}, 502
    return out


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
    if language == "uid":
        voice_id = (voice_id or "").strip()
        if not re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", voice_id):
            return {"error": "Invalid custom voice ID. Paste a valid UUID voice id (copy one from the Voice Library)."}, 400
    sample_rate = int(body.get("sample_rate", 44100))
    fmt = (body.get("format") or "mp3").lower()
    if fmt not in ("mp3", "wav"):
        fmt = "mp3"

    # Voice-style controls (POST body first, URL query as fallback so
    # playground-style share links like ?speed=0.9&volume=1.5&emotion=sad
    # keep working). Same ranges/defaults as play.cartesia.ai.
    def _num(name, default, lo, hi):
        raw = body.get(name, request.args.get(name, default))
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return None, f"invalid '{name}': must be a number"
        if not (lo <= val <= hi):
            return None, f"invalid '{name}': must be between {lo} and {hi}"
        return val, None

    speed, err = _num("speed", 1, 0.6, 1.5)
    if err:
        return {"error": err}, 400
    volume, err = _num("volume", 1, 0.5, 2.0)
    if err:
        return {"error": err}, 400
    emotion = str(body.get("emotion", request.args.get("emotion", "neutral")) or "neutral").strip().lower()
    if emotion not in EMOTIONS:
        return {"error": f"invalid 'emotion': '{emotion}'. Use one of: " + ", ".join(sorted(EMOTIONS))}, 400

    token = get_token()
    if fmt == "wav":
        output_format = {"container": "wav", "encoding": "pcm_s16le",
                         "sample_rate": sample_rate}
        mime, ext = "audio/wav", "wav"
    else:
        output_format = {"container": "mp3", "encoding": "mp3",
                         "sample_rate": sample_rate}
        mime, ext = "audio/mpeg", "mp3"
    payload = {
        "model_id": model,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "output_format": output_format,
    }
    if language != "uid":
        payload["language"] = language
    # generation_config works on sonic-3/3.5. It is always sent for those
    # models; for older models (sonic-2/turbo) it is only sent when the user
    # explicitly picked non-default values (user priority first).
    if model in GENCFG_MODELS or speed != 1 or volume != 1 or emotion != "neutral":
        payload["generation_config"] = {
            "speed": speed, "volume": volume, "emotion": emotion,
        }
    payload = json.dumps(payload).encode()

    req = urllib.request.Request(
        TTS_URL, data=payload, method="POST",
        headers={"Cartesia-Version": API_VERSION, "x-api-key": token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        return {"error": f"TTS error {e.code}: {e.read().decode()[:300]}"}, 502

    return Response(audio, mimetype=mime,
                    headers={"Content-Disposition":
                              'attachment; filename="tts.%s"' % ext})


# Convenience aliases matching the earlier API.
@app.route("/tts", methods=["POST"])
def tts_alias():
    return api_tts()


@app.route("/voices", methods=["GET"])
def voices_alias():
    return api_voices()


@app.route("/robots.txt", methods=["GET"])
def robots_txt():
    body = "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % SITE_URL
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml", methods=["GET"])
def sitemap_xml():
    pages = ["/", "/library", "/stt"]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in pages:
        lines.append("  <url><loc>%s%s</loc></url>" % (SITE_URL, p))
    lines.append("</urlset>")
    return Response("\n".join(lines), mimetype="application/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
