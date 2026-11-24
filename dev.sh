#!/bin/sh
# Starts backend + web. Open https://<your-LAN-IP>:5173 on your phone (accept the certificate warning once).
cd "$(dirname "$0")"
(cd backend && uv run uvicorn voxli.server:app --host 127.0.0.1 --port 8000 --reload) &
echo "Phone URL: https://$(ipconfig getifaddr en0 2>/dev/null || hostname -I | cut -d' ' -f1):5173"
cd web && npm run dev
