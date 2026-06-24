@echo off
REM Registra o Gmail Monitor como tarefa agendada diaria as 08:00
REM Execute este arquivo como Administrador

set SCRIPT_DIR=C:\Users\advogados\Claude\2. Docs. Defesa\gmail_monitor
set LAUNCHER=%SCRIPT_DIR%\executar_monitor.bat
set PYTHON=C:\Users\advogados\AppData\Local\Python\pythoncore-3.14-64\python.exe
set MONITOR=%SCRIPT_DIR%\gmail_monitor.py

REM Remove tarefa existente (ignora erro se nao existir)
schtasks /Delete /TN "GmailMonitor" /F >nul 2>&1

REM Cria nova tarefa diaria as 08:00
schtasks /Create /TN "GmailMonitor" ^
  /TR "cmd /c \"%LAUNCHER%\"" ^
  /SC DAILY /ST 08:00 ^
  /F /RL HIGHEST ^
  /RU "%USERNAME%"

if %errorlevel%==0 (
    echo.
    echo ============================================
    echo  Tarefa agendada com sucesso!
    echo ============================================
    echo  Execucao:  todos os dias as 08:00
    echo  Relatorios: %SCRIPT_DIR%\Relatorios\
    echo  Logs:       %SCRIPT_DIR%\logs\execucao.log
    echo.
    echo  Para testar agora:
    echo    schtasks /Run /TN "GmailMonitor"
    echo ============================================
) else (
    echo.
    echo FALHA ao agendar tarefa.
    echo Execute este arquivo como Administrador:
    echo   Botao direito -> Executar como administrador
)
pause
