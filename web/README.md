# Voxli phone web app

React + TypeScript + Vite, plain CSS (design tokens in `src/style.css`), Lucide icons, Atkinson Hyperlegible (self-hosted in `public/fonts`, SIL OFL licence alongside).
`npm run dev` serves `https://<LAN-IP>:5173` (self-signed; `/ws` and `/api` proxy to the backend on :8000). Add it to the home screen for a standalone app (`public/manifest.webmanifest`).

- `?mock=1` runs a scripted fake conversation (no backend, no mic). Extras: `&speed=2` (faster), `&from=33` (start 33 s into the script), `&mono=1` (mono-mic notice, no Room view), `&asr=local`, `&drop=1` (connection drops at ~30 s and returns). Voice picker and Speak still call `/api/tts` if the backend is up, else use the phone voice.
- Without `?mock=1` the "Start listening" button opens the mic (stereo requested; duplicated mono is detected and sent as 1 channel) and connects to `/ws`.
- Views: People (one card per person), Conversation (chronological feed with overlap brackets), Room (only when stereo direction exists).
- `src/protocol.ts` mirrors `docs/CONTRACT.md`. `src/store.ts` holds all conversation state; `src/tts.ts` voice output (server MP3, phone-voice fallback); `src/mock.ts` the demo script; `public/pcm-worklet.js` the 16 kHz Int16 capture worklet.
