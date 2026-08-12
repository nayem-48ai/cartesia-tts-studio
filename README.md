# TNxBD Studio

A professional, multilingual AI text-to-speech web app backed by **Cartesia Sonic**
models. Generate lifelike speech in **40+ languages** and download MP3 audio from a
clean web UI or a simple JSON API.

## Live site

> **https://tnxbd-tts.vercel.app**

- Web UI: scrollable language chips (Bangla, English, Hindi, Spanish, French,
  German, Arabic, Japanese, Korean, Chinese, Russian, and more), model + voice
  pickers, live character counter, a custom audio player with **seekable progress
  bar + current/total timer**, and MP3 download. Light/dark mode included.
- API: `POST /api/tts` → MP3, `GET /api/voices?language=bn`,
  `GET /api/models?language=bn`, `GET /api/languages`.
- No API key required by the caller — the app mints a short-lived public Cartesia
  token per request, and the voice catalog is embedded statically for instant loads.

## Local run
```bash
pip install -r requirements.txt
python app.py          # http://127.0.0.1:8080
```

## API example
```bash
curl -X POST https://tnxbd-tts.vercel.app/api/tts \
  -H "Content-Type: application/json" \
  -d '{"language":"bn","model":"sonic-3.5","voice_id":"2ba861ea-7cdc-43d1-8608-4045b5a41de5","text":"আমি দেখলাম আপনি আমাদের নতুন সফটওয়্যার প্ল্যানটা দেখছিলেন।"}' \
  --output out.mp3
```

## Deployment
- **Live (Vercel):** https://tnxbd-tts.vercel.app (project renamed from the
  original `cartesia-tts-studio`).
- Deployed via the Deployments file API using the `@vercel/python` builder
  (`vercel.json` wraps `app.py` as a serverless function).
- **Render:** a free web-service was attempted, but Render's free build queue
  repeatedly hit the 15-minute build timeout, so Vercel (fast builds) is used.

### Deploy to Vercel (file API)
```bash
curl -X POST https://api.vercel.com/v13/deployments \
  -H "Authorization: Bearer $VERCEL_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"tnxbd-tts","target":"production","version":2,
       "builds":[{"src":"app.py","use":"@vercel/python"}],
       "routes":[{"src":"/.*","dest":"app.py"}],
       "files":[ ... base64 of app.py, voices.json, requirements.txt, templates/index.html ... ]}'
```
