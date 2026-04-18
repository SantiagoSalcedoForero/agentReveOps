# Deploy del bot de Verifty a Oracle Cloud (OCI)

## Antes de arrancar — prerequisitos

1. **VM en OCI** (Ubuntu 22.04 o 24.04 LTS recomendado, ARM Ampere A1 gratis o x86)
2. **Dominio apuntando a la VM** (ej: `bot.verifty.com` → A record → IP pública de la VM)
3. **Puertos 80 y 443 abiertos**:
   - En OCI: Networking → Virtual Cloud Networks → tu VCN → Security List → Ingress Rules → agregar TCP 80 y 443 desde `0.0.0.0/0`
   - En la VM: `sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw allow 22`
4. **SSH al servidor**: `ssh ubuntu@IP_DE_LA_VM`

## Paso a paso

### 1. Conéctate a la VM

```bash
ssh ubuntu@TU_IP_DE_OCI
```

### 2. Instala Docker

```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Docker
curl -fsSL https://get.docker.com | sudo sh

# Compose plugin
sudo apt install -y docker-compose-plugin

# Permitir docker sin sudo (aplica en próxima sesión)
sudo usermod -aG docker ubuntu
newgrp docker

# Verificar
docker --version
docker compose version
```

### 3. Clona el repo (o sube los archivos)

**Opción A — desde git (recomendado si ya tienes el repo):**
```bash
cd ~
git clone TU_REPO_URL verifty-bot
cd verifty-bot
```

**Opción B — rsync desde tu mac:**
```bash
# Desde tu Mac, en la carpeta del proyecto:
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  ./ ubuntu@TU_IP:/home/ubuntu/verifty-bot/
```

### 4. Configura el dominio

Edita `Caddyfile` y reemplaza `bot.verifty.com` por tu dominio real. Cambia también el email de Let's Encrypt.

```bash
nano Caddyfile
```

### 5. Crea el archivo `.env` en la VM

```bash
nano .env
```

Pega el contenido de tu `.env` local (el que ya funciona). **⚠️ Asegúrate que contiene:**
- `WHATSAPP_ACCESS_TOKEN` (el permanente)
- `SUPABASE_SERVICE_ROLE_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET`
- Resto de vars del `.env.example`

### 6. Build + up

```bash
docker compose up -d --build
```

Primera vez: tarda 2-5 min (build image + Let's Encrypt cert).

### 7. Verifica que arrancó

```bash
# Containers corriendo
docker compose ps

# Logs en vivo
docker compose logs -f bot

# Health desde fuera
curl https://TU_DOMINIO/health
# → {"status":"ok","timestamp":"..."}
```

### 8. Actualiza el webhook de Meta

En `developers.facebook.com/apps/918415297679189/whatsapp-business/wa-settings`:
- Callback URL: `https://TU_DOMINIO/webhook`
- Verify token: `verifty-bot-verify-2026`
- Click "Verificar y guardar"
- Verifica que `messages` sigue suscrito

### 9. Apaga ngrok local y desconecta el bot de tu laptop

```bash
# En tu Mac
pkill -f "uvicorn main:app"
pkill -f "ngrok http 8000"
```

## Comandos útiles post-deploy

```bash
# Ver logs del bot
docker compose logs -f bot

# Ver logs de Caddy (acceso HTTPS)
docker compose logs -f caddy

# Reiniciar todo
docker compose restart

# Actualizar el bot después de cambios de código
cd ~/verifty-bot
git pull   # o rsync desde local
docker compose up -d --build

# Ver uso de recursos
docker stats

# Ver espacio en disco
df -h
docker system df

# Limpiar imágenes viejas
docker system prune -af --volumes
```

## Auto-start al reiniciar la VM

El `restart: unless-stopped` en `docker-compose.yml` ya hace que los containers se levanten solos al reiniciar la VM. No necesitas systemd extra.

## Backups de Caddy (certs)

Los certificados de Let's Encrypt están en volúmenes Docker. Si necesitas migrar la VM:

```bash
docker run --rm -v verifty-bot_caddy_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/caddy_data.tar.gz /data
```

## Troubleshooting

| Síntoma | Causa probable | Fix |
|---------|---------------|-----|
| `curl https://dominio/health` no responde | DNS no resuelve o puertos cerrados | `dig TU_DOMINIO` y revisar iptables/OCI security list |
| Caddy no saca certificado | Puerto 80 cerrado o DNS no propagado | Espera 10 min, revisa `docker compose logs caddy` |
| Bot responde 502 | Contenedor `bot` caído | `docker compose logs bot` |
| Meta webhook verify falla | Token no coincide o URL mal | Revisa `.env` y URL exacta con `/webhook` al final |
| El bot no envía mensajes | Token de Meta inválido | `curl` al endpoint de Graph con el token, si 401 → regenera |
