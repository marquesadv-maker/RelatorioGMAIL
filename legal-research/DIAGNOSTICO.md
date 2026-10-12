# Se o localhost não abrir

1. **Python instalado?** Abra o Prompt de Comando e digite `python --version`. Se der erro, instale em https://www.python.org/downloads/ marcando "Add Python to PATH". Feche e abra o `run.bat` de novo.
2. **A janela preta fechou sozinha?** Rode o `run.bat` pelo Prompt de Comando (arraste o arquivo para a janela e Enter) para ler a mensagem de erro.
3. **A página diz "não é possível acessar"?** Aguarde: na primeira execução a instalação leva 1 a 2 minutos. O novo `run.bat` só abre o navegador quando o servidor responde.
4. **Porta ocupada?** O script troca automaticamente para http://localhost:8766. Veja a porta impressa na janela.
5. **Antivírus ou firewall** pode bloquear o `python.exe`. Permita o acesso apenas para "redes privadas"; o servidor escuta só em 127.0.0.1.
6. **Teste manual**, no Prompt de Comando dentro da pasta:
   ```
   .venv\Scripts\activate
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
   ```
   Depois abra http://127.0.0.1:8765 no navegador. A mensagem de erro, se houver, aparece nessa janela.
