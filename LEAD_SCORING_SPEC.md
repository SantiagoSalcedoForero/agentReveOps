# Lead Scoring SPEC — v1

**Última actualización:** 2026-04-22
**Status:** Activo
**Implementado en:** verifty-bot (app/bot/scorer.py), verifty-crm (src/lib/leads/lead-scoring.ts)

Este documento es fuente de verdad. Cualquier cambio a la lógica de scoring debe actualizar este archivo Y ambos implementations simultáneamente. Los 20 tests de este SPEC deben pasar en ambos repos.

## Filosofía

Tres componentes independientes que se suman (excepto hard stops). Scoring B2B no es solo "tamaño": es FIT + INTENT + calidad de señal.

## Componente 1 — FIT (0-10 puntos)

### 1.1 Empleados (0-4 pts)
- 500+: 4
- 101-500: 3
- 51-100: 2
- 20-50: 1
- 1-19: 0

### 1.2 Nivel de riesgo / Industria (0-3 pts)
Si viene ARL, usar ARL. Si no, usar industria.

ARL:
- V: 3
- IV: 3
- III: 2
- II: 1
- I: 0

Industria (si no hay ARL):
- Energía, petróleo, gas, minería, química: 3
- Construcción, manufactura pesada, metalmecánica, logística pesada: 3
- Transporte, farmacéutica/industriales: 2
- Manufactura ligera, agricultura industrial: 2
- Retail, servicios profesionales, educación, salud ambulatoria: 1
- Consultoría, tecnología, finanzas (sin operaciones físicas): 0

### 1.3 Contratistas (0-3 pts)
- 50+: 3
- 10-49: 2
- 1-9: 1
- No tiene / no responde: 0

Máximo FIT: 10 pts.

## Componente 2 — INTENT (0-5 puntos)

### 2.1 Calidad del email (0-2 pts)
- Dominio corporativo (no free provider): 2
- Free provider (gmail, hotmail, yahoo, outlook, live, icloud, aol, msn, protonmail, zoho, mail.com): 0

### 2.2 País (0-2 pts)
- Colombia: 2
- México: 2
- España: 1
- Chile: 1
- Argentina: 1
- Resto LATAM hispanohablante (Ecuador, Perú, Bolivia, Uruguay, Costa Rica, Panamá, Venezuela, Guatemala, El Salvador, Honduras, Nicaragua, Rep. Dominicana, Paraguay, Cuba): 0
- Otros: 0 (no hard stop)

### 2.3 Completitud del formulario (0-1 pt)
- Todos los campos clave presentes y coherentes: 1
- Campos faltantes o valores basura: 0

Máximo INTENT: 5 pts.

## Componente 3 — HARD STOPS
Cualquiera → NO_CALIFICA sin importar score.

### HS-1 — Empresa inválida
Nombre de empresa es:
- Literal en: ["independiente", "no aplica", "casa", "privada", "confidencial", "prueba", "test", "particular", "propia", "personal"]
- Solo dígitos (patrón cédula): `^\d+$`
- Vacío o <3 caracteres
- Es igual al nombre o email del contacto

### HS-2 — Triple débil
Email es consumer (free provider) AND empresa no tiene dominio identificable AND FIT ≤ 2.

### HS-3 — Educación básica o individual
Empresa contiene (case-insensitive): "colegio", "escuela", "centro educativo", "preescolar", "jardín infantil", "jardin infantil", "universidad".

## Mapeo Score → Clasificación

Total = FIT + INTENT (0-15):
- 0-4: NO_CALIFICA
- 5-7: TIBIO
- 8-10: CALIFICADO
- 11-15: VIP

## Golden Override

Si email_is_corporate AND empleados >= 100 → mínimo CALIFICADO (aunque score sume menos).

El override NO aplica si hay hard stop activo.

## Free Email Providers (lista canónica)
gmail.com, gmail.co, googlemail.com, googlemail.co, outlook.com, outlook.co, live.com, icloud.com, me.com, mac.com, aol.com, yahoo.com, yahoo.co, ymail.com, rocketmail.com, protonmail.com, proton.me, pm.me, zoho.com, mail.com, msn.com, gmx.com, fastmail.com, hotmail.com, hotmail.co

## Países LATAM hispanohablantes (lista canónica)

Focal (2 pts): CO, MX
Secundario (1 pt): ES, CL, AR
Resto (0 pts, sin hard stop): EC, PE, BO, UY, CR, PA, VE, GT, SV, HN, NI, DO, PY, CU

Cualquier otro país: 0 pts, sin hard stop.
