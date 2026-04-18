# Verifty WhatsApp Bot

Microservicio FastAPI que opera el bot de WhatsApp de Verifty: califica leads,
agenda demos y escala al equipo comercial cuando hace falta.

## Stack
- FastAPI + Uvicorn
- Anthropic Claude (Haiku) para conversación
- Supabase (service role) para CRM
- Google Calendar para agendamiento
- Meta WhatsApp Cloud API

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # completa las credenciales
```

Aplica la migración SQL en Supabase:

```bash
psql $SUPABASE_DB_URL -f migrations/001_crm_notifications.sql
```

## Desarrollo

```bash
uvicorn main:app --reload --port 8000
```

## Endpoints
- `GET  /health` — healthcheck
- `GET  /webhook` — verificación de Meta
- `POST /webhook` — recibe mensajes (responde 200 inmediato, procesa en background)
- `POST /handoff/accept` — el CRM avisa que un agente tomó la conversación
- `POST /handoff/message` — el CRM envía un mensaje del agente al lead
- `POST /landing/gate` — form de descarga de plantilla desde verifty.com
- `POST /landing/verify` — verifica OTP y devuelve URL del archivo
- `POST /landing/lead-intent` — forms de contacto / demo-request (no plantillas)
- `GET  /admin/stats/*` — analytics del bot (Bearer token)

## Descargas de plantillas (`/landing/gate`)

Request body (JSON):

```json
{
  "phone":                "573150636348",
  "email":                "juan@empresa.com",
  "name":                 "Juan Pérez",
  "company":              "Empresa SAS",
  "employees":            150,
  "country":              "Colombia",
  "industry":             "construccion",
  "template_slug":        "matriz-ipevr-gtc-45-excel",
  "template_url":         "https://verifty.com/files/matriz-ipevr.xlsx",
  "template_title":       "Matriz IPEVR según GTC 45",
  "template_description": "Matriz de identificación de peligros, evaluación y valoración de riesgos siguiendo la guía GTC 45 de Icontec.",
  "utm_source":           "google",
  "utm_campaign":         "ats-abril-2026",
  "source_url":           "https://verifty.com/recursos/matriz-ipevr"
}
```

- `template_slug` y `template_url` son **requeridos**.
- `template_title` y `template_description` son **opcionales** pero **muy
  recomendados**: cuando el bot detecta que pasaron, genera el primer mensaje
  de WhatsApp post-OTP con LLM específico para esa plantilla (funciona con
  cualquier plantilla del catálogo, no solo las hardcoded).
- Si `template_title` no llega, el bot cae al mapa estático
  (`app/otp/templates_catalog.py`, 5 slugs conocidos).

El backend guarda `template_slug`, `template_title` y `template_description`
en la tabla `otp_codes`. Tras `/landing/verify`, se persisten `template_slug`
y `template_title` en `whatsapp_conversations`, y el contexto completo queda
en `context.downloaded_template`. El agente lo lee en mensajes posteriores
para mantener coherencia de conversación.

## Estructura

```
verifty-bot/
├── main.py
├── requirements.txt
├── .env.example
├── migrations/
│   └── 001_crm_notifications.sql
└── app/
    ├── config.py
    ├── logger.py
    ├── models/webhook.py
    ├── whatsapp/client.py
    ├── crm/client.py
    ├── bot/
    │   ├── agent.py
    │   ├── scorer.py
    │   ├── scheduler.py
    │   └── handoff.py
    └── notifications/notifier.py
```
