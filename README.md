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
curl -X POST https://<your-app>/api/tts \
  -H "Content-Type: application/json" \
  -d '{"language":"bn","model":"sonic-3.5","voice_id":"2ba861ea-7cdc-43d1-8608-4045b5a41de5","text":"আমি দেখলাম আপনি আমাদের নতুন সফটওয়্যার প্ল্যানটা দেখছিলেন।"}' \
  --output out.mp3
```

## Deployment
- **Live (Vercel):** https://cartesia-tts-studio-ejmi4b90s-tnayem48s-projects.vercel.app
  - Web UI + JSON API work for Bangla, English and Hindi.
  - Deployed via `vercel.json` (`@vercel/python` builder running the Flask app).
- **Render:** a free web-service was created, but Render's free build queue
  repeatedly hit the 15-minute build timeout, so Vercel (fast builds) was used
  instead. The same repo deploys to either host.

### Deploy to Vercel (file API)
```bash
# vercel.json wraps app.py (Flask WSGI) as a serverless function
curl -X POST https://api.vercel.com/v13/deployments \
  -H "Authorization: Bearer $VERCEL_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"cartesia-tts-studio","target":"production","version":2,
       "builds":[{"src":"app.py","use":"@vercel/python"}],
       "routes":[{"src":"/.*","dest":"app.py"}],
       "files":[ ... base64 of app.py, requirements.txt, templates/index.html ... ]}'
```
