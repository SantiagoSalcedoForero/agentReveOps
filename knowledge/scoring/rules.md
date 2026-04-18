# Scoring del Lead — Escala 1-15 (alineada con CRM)

## Estructura del `score_breakdown` (idéntica al CRM Verifty)

```json
{
  "puntosTrabajadores": 0,
  "puntosRiesgo": 0,
  "puntosContratistas": 0,
  "puntosNumeroContratistas": 0
}
```

Total máximo: **15 puntos**

## Tabla de puntos

### puntosTrabajadores (0-5 pts)
| Empleados | Puntos |
|-----------|--------|
| < 20 | 1 |
| 20-100 | 2 |
| 100-300 | 3 |
| 300-1000 | 4 |
| +1000 | 5 |

### puntosRiesgo (ARL / nivel de riesgo operativo) (0-4 pts)
| Nivel | Puntos |
|-------|--------|
| ARL 1-2 (admin, oficina) | 1 |
| ARL 3 (manufactura ligera) | 2 |
| ARL 4 (construcción, transporte) | 3 |
| ARL 5 (minería, petróleo, alto riesgo) | 4 |

### puntosContratistas (0-3 pts)
| ¿Maneja contratistas? | Puntos |
|----------------------|--------|
| No | 0 |
| Sí, pocos (< 5) | 1 |
| Sí, varios (5-20) | 2 |
| Sí, muchos (+20) | 3 |

### puntosNumeroContratistas (0-3 pts)
Complementario al anterior: mide trabajadores contratistas activos.
| Trabajadores contratistas | Puntos |
|---------------------------|--------|
| < 10 | 1 |
| 10-50 | 2 |
| +50 | 3 |

## Umbrales de decisión del bot

| Score | Acción |
|-------|--------|
| ≥ 10 | **Calificado caliente** → agendar reu inmediata |
| 6-9 | Calificado → seguir calificando + ofrecer demo |
| 3-5 | Lead débil → intentar cerrar con precios planes 1-3 si aplica |
| 0-2 | Descartar o pasar a nurturing |

## Regla estratégica clave (del negocio)

**Si `empleados > 20` AND `has_contractors == true` → convertir a reunión SÍ O SÍ.**

Independiente del score, esa combinación es ICP perfecto.

## Bonus: empresa-país estratégico

No cuenta en los 15 puntos pero se usa para priorizar en CRM:
- Colombia, México, España → +1 bonus de prioridad
- Resto de mercados atendidos → 0

## Reglas de branching por score

1. **Score ≥ 10 (caliente):** BOOKING_READY inmediato
2. **Score 6-9 + plan 1-3 (< 250 trabajadores):** bot da precio del plan que aplica, intenta cerrar, si persiste → BOOKING_READY
3. **Score 6-9 + plan 4+ (≥ 250 trabajadores):** NO dar precio, solo vender valor → BOOKING_READY
4. **Score 3-5:** manejar objeciones, calificar más, no empujar reu aún
5. **Score 0-2 + no-ICP:** cerrar amablemente, sin handoff
