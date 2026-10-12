@echo off
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate
pip install -q -r requirements.txt
if not exist .env ( copy .env.exemplo .env & echo Preencha DATAJUD_API_KEY no arquivo .env )
start "" http://localhost:8765
uvicorn app.main:app --host 127.0.0.1 --port 8765
