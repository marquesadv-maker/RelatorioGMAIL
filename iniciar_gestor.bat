@echo off
REM Inicia o Gestor de E-mail MarquesPro em http://127.0.0.1:5055
REM Mantenha esta janela aberta enquanto usar o sistema.

cd /d "C:\Users\advogados\Claude\2. Docs. Defesa\gmail_monitor"

"C:\Users\advogados\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m pip install -q -r requirements.txt
"C:\Users\advogados\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m gestor_email
pause
