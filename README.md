# Cartesia TTS Studio

A professional, multilingual AI text-to-speech web app backed by **Cartesia Sonic**
models. Generate lifelike **Bangla, English and Hindi** speech and download MP3 audio
from a clean web UI or a simple JSON API.

## Features
- Web UI: language tabs (Bangla / English / Hindi), model + voice pickers, live
  character counter, audio player + MP3 download, light/dark mode.
- API: `POST /api/tts` → MP3, `GET /api/voices?language=bn`, `GET /api/models?language=bn`.
- No API key required by the caller — the app mints a short-lived public Cartesia
  token per request.

## Local run
```bash
pip install -r requirements.txt
python app.py          # http://127.0.0.1:8080
```

## API example
```bash
curl -X POST https://<your-app>.onrender.com/api/tts \
  -H "Content-Type: application/json" \
  -d '{"language":"bn","model":"sonic-3.5","voice_id":"2ba861ea-7cdc-43d1-8608-4045b5a41de5","text":"আমি দেখলাম আপনি আমাদের নতুন সফটওয়্যার প্ল্যানটা দেখছিলেন।"}' \
  --output out.mp3
```
