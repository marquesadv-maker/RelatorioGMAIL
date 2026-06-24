@echo off
REM Script de execução do Gmail Monitor
REM Chamado pelo Agendador de Tarefas do Windows

cd /d "C:\Users\advogados\Claude\2. Docs. Defesa\gmail_monitor"

"C:\Users\advogados\AppData\Local\Python\pythoncore-3.14-64\python.exe" "C:\Users\advogados\Claude\2. Docs. Defesa\gmail_monitor\gmail_monitor.py" >> "C:\Users\advogados\Claude\2. Docs. Defesa\gmail_monitor\logs\execucao.log" 2>&1
