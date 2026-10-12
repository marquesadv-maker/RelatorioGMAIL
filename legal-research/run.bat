@echo off
setlocal
cd /d "%~dp0"
title Legal Research Local
echo ============================================
echo  Legal Research Local - iniciando...
echo ============================================

where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo [ERRO] Python nao encontrado. Instale em https://www.python.org/downloads/
  echo        e marque "Add Python to PATH" durante a instalacao.
  pause
  exit /b 1
)

if not exist .venv (
  echo Criando ambiente virtual...
  %PY% -m venv .venv || ( echo [ERRO] Falha ao criar o ambiente virtual. & pause & exit /b 1 )
)
call .venv\Scripts\activate.bat
echo Instalando dependencias (pode levar 1-2 minutos na primeira vez)...
python -m pip install --disable-pip-version-check -q -r requirements.txt || ( echo [ERRO] Falha ao instalar dependencias. Verifique a conexao com a internet. & pause & exit /b 1 )

if not exist .env (
  copy .env.exemplo .env >nul
  echo [AVISO] Arquivo .env criado. Cole a chave do DataJud em DATAJUD_API_KEY
  echo         ^(https://datajud-wiki.cnj.jus.br/api-publica/acesso/^) para importar processos do CNJ.
)

set PORT=8765
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul && (
  echo [AVISO] A porta %PORT% ja esta em uso. Usando a porta 8766.
  set PORT=8766
)

echo Iniciando servidor em http://localhost:%PORT% ...
start "Legal Research - servidor" /min cmd /c "call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% || pause"

rem espera o servidor responder (ate 60 s)
set /a tent=0
:espera
set /a tent+=1
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/api/fontes/status -TimeoutSec 2) | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 goto pronto
if %tent% geq 30 (
  echo [ERRO] O servidor nao respondeu em 60 s. Veja a janela "Legal Research - servidor" para a mensagem de erro.
  pause
  exit /b 1
)
timeout /t 2 /nobreak >nul
goto espera

:pronto
echo Servidor pronto. Abrindo http://localhost:%PORT%
start "" "http://localhost:%PORT%"
echo.
echo Deixe a janela "Legal Research - servidor" aberta enquanto usar o sistema.
echo Para encerrar, feche aquela janela.
pause
