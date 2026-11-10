# Publicar o MarquesPro Mail no servidor

Servidor: pasta `/var/www/html/marquespromail`, serviço `marquespro-mail` (porta 5055, só no próprio servidor).

## ⚠ Antes de abrir para a internet
O MarquesPro Mail **não tem login próprio**: quem alcançar a porta vê as caixas de e-mail conectadas.
Por isso ele só escuta em `127.0.0.1` e deve ser publicado **somente** com o **Cloudflare Access** ligado
(Zero Trust → Access → Applications → política "Permitir" apenas os e-mails do escritório). Sem isso, não crie o hostname público.

## 1. Instalar no servidor
```bash
# no computador do escritório (copia o projeto)
scp -r gestor_email deploy requirements.txt analyzer.py marquespro@192.168.31.131:/tmp/mpmail/
# no servidor
ssh marquespro@192.168.31.131
cd /tmp/mpmail && sudo bash deploy/instalar_servidor.sh   # pergunta a chave da IA (digitação oculta)
```
Atualizações futuras: repita os mesmos comandos (preserva a chave, as contas e o cache).

## 2. Conectar o Gmail
O Google exige autorizar no navegador. Faça no **computador do escritório**, com o programa local:
1. Rode `iniciar_gestor.bat`, abra Configurações → Contas e conecte cada conta (cada uma autoriza a própria).
2. Copie as autorizações para o servidor:
```bash
scp gestor_email/dados/tokens/*.json marquespro@192.168.31.131:/tmp/tokens/
ssh marquespro@192.168.31.131 'sudo install -o marquespro-mail -g marquespro-mail -m 600 /tmp/tokens/*.json /var/lib/marquespro-mail/tokens/ && rm -r /tmp/tokens && sudo systemctl restart marquespro-mail'
```
Não rode o mesmo token no computador e no servidor ao mesmo tempo por muito tempo: o ideal é que só o servidor sincronize.

## 3. Chave da IA
Digitada na instalação (arquivo `/etc/marquespro-mail.env`, permissão 600). Para trocar:
`sudo nano /etc/marquespro-mail.env` (linha `ANTHROPIC_API_KEY=`) e `sudo systemctl restart marquespro-mail`.

## 4. Cloudflare Tunnel
No túnel que já atende o domínio, adicione um hostname (ex.: `mail.marquesss.com.br`) → `http://localhost:5055`
e proteja com Cloudflare Access (item acima).

## 5. Conferir
`sudo systemctl status marquespro-mail` · `journalctl -u marquespro-mail -n 50` · no navegador, o selo verde "Gmail sincronizado".
