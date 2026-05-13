#!/usr/bin/env bash
# Sube el código a la VM de OCI vía rsync y reinicia los contenedores.
# Uso: ./deploy/sync.sh usuario@ip
#
# Ejemplo: ./deploy/sync.sh ubuntu@129.146.xxx.xxx
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Uso: $0 usuario@ip"
  exit 1
fi

TARGET="$1"
REMOTE_DIR="/home/ubuntu/verifty-bot"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/oci_verifty_bot}"

echo "→ Subiendo código a $TARGET:$REMOTE_DIR"
RSYNC_RSH="ssh -i $SSH_KEY" rsync -avz --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude '*.log' \
  --exclude '.DS_Store' \
  --exclude '.env' \
  ./ "$TARGET:$REMOTE_DIR/"

echo "→ Rebuild + restart remoto"
ssh -i "$SSH_KEY" "$TARGET" "cd $REMOTE_DIR && docker compose up -d --build"

echo "→ Logs:"
ssh -i "$SSH_KEY" "$TARGET" "cd $REMOTE_DIR && docker compose logs --tail=30 bot"

echo "✅ Listo"
