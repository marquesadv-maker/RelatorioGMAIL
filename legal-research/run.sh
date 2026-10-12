#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || { cp .env.exemplo .env; echo "Preencha DATAJUD_API_KEY no arquivo .env"; }
exec uvicorn app.main:app --host 127.0.0.1 --port 8765
