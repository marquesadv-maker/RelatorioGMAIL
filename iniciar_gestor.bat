@echo off
chcp 65001 >nul
title MarquesPro Mail
REM Inicia o Gestor de E-mail MarquesPro em http://127.0.0.1:5055
REM Mantenha esta janela aberta enquanto usar o sistema.

REM Usa a pasta onde este arquivo esta (funciona em qualquer local)
cd /d "%~dp0"

if not exist "gestor_email\__main__.py" (
    echo [ERRO] Pasta gestor_email nao encontrada ao lado deste arquivo.
    echo Extraia o ZIP inteiro na mesma pasta do iniciar_gestor.bat.
    goto fim
)

REM Localiza o Python: caminho do monitor, depois "py", depois "python"
set "PY=C:\Users\advogados\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY="
if not defined PY ( where py >nul 2>&1 && set "PY=py" )
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
    echo [ERRO] Python nao encontrado. Instale em https://www.python.org/downloads/
    goto fim
)
echo Python: %PY%

if not exist "credentials.json" (
    echo [AVISO] credentials.json nao esta nesta pasta: "%CD%"
    echo O sistema abre, mas nao sera possivel conectar contas ate copiar o arquivo.
)

echo Instalando/verificando dependencias...
"%PY%" -m pip install -q -r requirements.txt
if errorlevel 1 echo [AVISO] Falha ao instalar dependencias. Veja a mensagem acima.

echo.
echo Iniciando... o navegador abrira em http://127.0.0.1:5055
echo (Se nao abrir, copie esse endereco no Chrome/Edge com esta janela ABERTA.)
echo.
"%PY%" -m gestor_email
echo.
echo [O sistema foi encerrado] Se houve erro, copie as mensagens acima e envie ao suporte.

:fim
pause
