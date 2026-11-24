# Voxli phone web app

React + TypeScript + Vite, plain CSS. `npm run dev` serves `https://<LAN-IP>:5173` (self-signed; `/ws` proxies to the backend on :8000).

- `?mock=1` runs a scripted fake conversation (no backend, no mic). Extras: `&speed=2` (faster), `&mono=1` (mono-mic banner, no directions), `&asr=local`, `&drop=1` (connection drops at ~30 s and returns).
- Without `?mock=1` the "Start listening" button opens the mic (stereo requested; duplicated mono is detected and sent as 1 channel) and connects to `/ws`.
- `src/protocol.ts` mirrors `docs/CONTRACT.md` (read-only here). `src/store.ts` holds all conversation state; `src/mock.ts` the demo script; `public/pcm-worklet.js` the 16 kHz Int16 capture worklet.
