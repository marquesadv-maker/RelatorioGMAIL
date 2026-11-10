#!/usr/bin/env bash
# Instala/atualiza o MarquesPro Mail no servidor. Rode NO SERVIDOR, a partir da pasta do projeto:
#   sudo bash deploy/instalar_servidor.sh
# Nada de senha ou chave fica neste arquivo: a chave da IA é digitada na hora (não aparece na tela).
set -euo pipefail

DEST=/var/www/html/marquespromail
DADOS=/var/lib/marquespro-mail
ENVF=/etc/marquespro-mail.env
ORIGEM="$(cd "$(dirname "$0")/.." && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "Rode com sudo."; exit 1; }

id marquespro-mail >/dev/null 2>&1 || useradd --system --home "$DADOS" --shell /usr/sbin/nologin marquespro-mail
mkdir -p "$DEST" "$DADOS/tokens"

# Código (preserva venv e dados)
for item in gestor_email requirements.txt; do
  rm -rf "${DEST:?}/$item"
  cp -a "$ORIGEM/$item" "$DEST/"
done
# analyzer.py é usado para classificar notificações no mesmo critério da controladoria
[ -f "$ORIGEM/analyzer.py" ] && cp -a "$ORIGEM/analyzer.py" "$DEST/"

python3 -m venv "$DEST/venv"
"$DEST/venv/bin/pip" install --quiet --upgrade pip
"$DEST/venv/bin/pip" install --quiet -r "$DEST/requirements.txt"

# Configuração (criada uma vez; atualizações não sobrescrevem)
if [ ! -f "$ENVF" ]; then
  printf "Chave da API da Anthropic (sk-ant-..., Enter para configurar depois): "
  read -rs CHAVE; echo
  umask 077
  {
    echo "GESTOR_HOST=127.0.0.1"
    echo "GESTOR_PORT=5055"
    echo "GESTOR_DATA_DIR=$DADOS"
    [ -n "$CHAVE" ] && echo "ANTHROPIC_API_KEY=$CHAVE"
  } > "$ENVF"
  chmod 600 "$ENVF"
fi

# Contas do Gmail: autorizadas no computador do escritório e copiadas para cá (ver deploy/LEIA-ME.md)
chown -R marquespro-mail:marquespro-mail "$DADOS"
chown -R root:marquespro-mail "$DEST"; chmod -R g+rX,o-rwx "$DEST"
chmod 700 "$DADOS" "$DADOS/tokens"

install -m 644 "$ORIGEM/deploy/marquespro-mail.service" /etc/systemd/system/marquespro-mail.service
systemctl daemon-reload
systemctl enable marquespro-mail >/dev/null
systemctl restart marquespro-mail
sleep 2
systemctl --no-pager --lines=5 status marquespro-mail || true
echo
echo "Teste local: curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5055/   (esperado: 200)"
