"""Catálogo único de planes y precios de Verifty SST.

Fuente de verdad para WhatsApp bot, webchat VERA y cotizaciones email.
Inmutable en runtime — frozen dataclasses, sin acceso a DB ni .env.
Verifty Flow queda fuera de este módulo (opera con handoff a demo).

Modelo M3.5 — TRABAJADORES TOTALES
===================================
Cada plan tiene un límite de "trabajadores totales con SG-SST gestionado",
que es la suma de:
  max_empleados_sin_acceso  — trabajadores sin login (info SST en el sistema)
  max_cuentas               — trabajadores con login (responsable SST, supervisor...)

El bot recomienda por trabajadores TOTALES.
El campo técnico max_empleados_sin_acceso queda como detalle interno.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums y tipos
# ---------------------------------------------------------------------------

class Ciclo(str, Enum):
    MENSUAL = "mensual"
    ANUAL   = "anual"


# ---------------------------------------------------------------------------
# Estructuras de datos
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanBase:
    codigo:                   str           # "BASIC" | "STARTER" | "PRO" | "PLUS" | "CORPORATIVO"
    nombre:                   str           # "Basic", "Starter", ...
    precio_mensual_cop:       Optional[int] # None para Corporativo
    max_empleados_sin_acceso: Optional[int] # trabajadores sin login; None = ilimitado
    max_sedes:                int
    max_cuentas:              int           # trabajadores con login a la app
    almacenamiento_gb:        float
    incluye_ipevr:            bool          # Matriz IPEVR GTC-45 disponible desde STARTER
    incluye_contratistas:     bool
    incluye_api_sso:          bool
    descripcion_corta:        str           # 1 línea para el bot
    razon_eleccion:           str           # frase exacta que usa el bot al recomendarlo

    @property
    def precio_dia_cop(self) -> Optional[int]:
        """Precio diario aproximado (precio_mensual / 30), redondeado al entero más cercano."""
        if self.precio_mensual_cop is None:
            return None
        return round(self.precio_mensual_cop / 30)

    @property
    def max_trabajadores_totales(self) -> Optional[int]:
        """Trabajadores totales = sin acceso + con acceso. None si ilimitado."""
        if self.max_empleados_sin_acceso is None:
            return None
        return self.max_empleados_sin_acceso + self.max_cuentas


@dataclass(frozen=True)
class PlanVera:
    codigo:              str   # "VERA_LITE" | "VERA_PRO" | "VERA_PLUS"
    nombre:              str
    precio_mensual_cop:  int
    tokens_mensuales:    int
    modelo_claude:       str  # "Haiku", "Sonnet", "Opus"
    descripcion_corta:   str


# ---------------------------------------------------------------------------
# Catálogo de planes SST — en orden ascendente de precio (IMPORTANTE para
# recomendar_plan_base, que devuelve el primer plan que satisface todos los límites)
# ---------------------------------------------------------------------------

PLANES_BASE: list[PlanBase] = [
    PlanBase(
        codigo="BASIC",
        nombre="Basic",
        precio_mensual_cop=39_000,
        max_empleados_sin_acceso=3,
        max_sedes=1,
        max_cuentas=1,
        almacenamiento_gb=0.25,
        incluye_ipevr=False,
        incluye_contratistas=False,
        incluye_api_sso=False,
        descripcion_corta="micro empresa (hasta 4 trabajadores)",
        razon_eleccion=(
            "te alcanza el Basic — hasta 4 trabajadores en total "
            "(3 sin login + 1 con login), formularios e inspecciones de campo"
        ),
    ),
    PlanBase(
        codigo="STARTER",
        nombre="Starter",
        precio_mensual_cop=220_000,
        max_empleados_sin_acceso=7,
        max_sedes=1,
        max_cuentas=3,
        almacenamiento_gb=3,
        incluye_ipevr=True,
        incluye_contratistas=False,
        incluye_api_sso=False,
        descripcion_corta="pequeña empresa iniciando SG-SST (hasta 10 trabajadores)",
        razon_eleccion=(
            "el Starter te queda perfecto — hasta 10 trabajadores en total "
            "(7 sin login + 3 con login), incluye matriz IPEVR GTC-45, "
            "capacitaciones, accidentes y programas SST"
        ),
    ),
    PlanBase(
        codigo="PRO",
        nombre="Pro",
        precio_mensual_cop=600_000,
        max_empleados_sin_acceso=30,
        max_sedes=1,
        max_cuentas=20,
        almacenamiento_gb=15,
        incluye_ipevr=True,
        incluye_contratistas=False,
        incluye_api_sso=False,
        descripcion_corta="mediana empresa con SG-SST formal (hasta 50 trabajadores)",
        razon_eleccion=(
            "el Pro es el que te sirve — hasta 50 trabajadores en total "
            "(30 sin login + 20 con login), salud ocupacional, "
            "objetivos e indicadores SST y reportes ejecutivos para gerencia"
        ),
    ),
    PlanBase(
        codigo="PLUS",
        nombre="Plus",
        precio_mensual_cop=1_220_000,
        max_empleados_sin_acceso=80,
        max_sedes=10,
        max_cuentas=50,
        almacenamiento_gb=50,
        incluye_ipevr=True,
        incluye_contratistas=True,
        incluye_api_sso=False,
        descripcion_corta="multi-sede con contratistas (hasta 130 trabajadores)",
        razon_eleccion=(
            "el Plus es el adecuado — hasta 130 trabajadores en total "
            "(80 sin login + 50 con login), multi-sede, contratistas, "
            "auditorías ISO 45001 y requisitos legales"
        ),
    ),
    PlanBase(
        codigo="CORPORATIVO",
        nombre="Corporativo",
        precio_mensual_cop=None,
        max_empleados_sin_acceso=None,
        max_sedes=999,
        max_cuentas=999,
        almacenamiento_gb=999,
        incluye_ipevr=True,
        incluye_contratistas=True,
        incluye_api_sso=True,
        descripcion_corta="solución a la medida (trabajadores ilimitados)",
        razon_eleccion=(
            "esto se va a Corporativo — trabajadores ilimitados, API y SSO, "
            "lo cotizamos a la medida con el equipo"
        ),
    ),
]


PLANES_VERA: list[PlanVera] = [
    PlanVera(
        codigo="VERA_LITE",
        nombre="Vera Lite",
        precio_mensual_cop=59_000,
        tokens_mensuales=100_000,
        modelo_claude="Haiku",
        descripcion_corta="Consultas SST + navegación asistida (solo lectura)",
    ),
    PlanVera(
        codigo="VERA_PRO",
        nombre="Vera Pro",
        precio_mensual_cop=199_000,
        tokens_mensuales=500_000,
        modelo_claude="Sonnet",
        descripcion_corta="Gestiona programas, accidentes y planes de acción",
    ),
    PlanVera(
        codigo="VERA_PLUS",
        nombre="Vera Plus",
        precio_mensual_cop=650_000,
        tokens_mensuales=2_000_000,
        modelo_claude="Opus",
        descripcion_corta="Análisis cruzado IPEVR + diagnóstico integral",
    ),
]

DESCUENTO_ANUAL = 0.10  # 10% según sst.verifty.com/planes

_PLANES_BASE_IDX: dict[str, PlanBase] = {p.codigo.upper(): p for p in PLANES_BASE}
_PLANES_VERA_IDX: dict[str, PlanVera] = {p.codigo.upper(): p for p in PLANES_VERA}


# ---------------------------------------------------------------------------
# Helpers públicos
# ---------------------------------------------------------------------------

def get_plan_base(codigo: str) -> Optional[PlanBase]:
    """Lookup case-insensitive por código. Retorna None si no existe."""
    return _PLANES_BASE_IDX.get(codigo.upper())


def get_plan_vera(codigo: str) -> Optional[PlanVera]:
    """Lookup case-insensitive por código. Retorna None si no existe."""
    return _PLANES_VERA_IDX.get(codigo.upper())


def precio_con_ciclo(precio_mensual_cop: int, ciclo: Ciclo) -> int:
    """Precio total según ciclo de facturación.

    Mensual: devuelve el precio mensual sin cambios.
    Anual:   precio_mensual * 12 * (1 - DESCUENTO_ANUAL), redondeado al entero.
    """
    if ciclo == Ciclo.MENSUAL:
        return precio_mensual_cop
    return round(precio_mensual_cop * 12 * (1 - DESCUENTO_ANUAL))


def formato_cop(monto: int) -> str:
    """Formatea un entero como precio COP con puntos de miles, sin dependencias de locale.

    Ejemplo: 600_000 → "$ 600.000"
             1_220_000 → "$ 1.220.000"
    """
    return "$ " + f"{monto:,}".replace(",", ".")


def recomendar_plan_base(
    num_empleados: int,
    num_sedes: int = 1,
    tiene_contratistas: bool = False,
    necesita_api_sso: bool = False,
) -> PlanBase:
    """Devuelve el plan de menor precio que satisface todos los límites dados.

    num_empleados se interpreta como TRABAJADORES TOTALES (sin acceso + con acceso).

    Evalúa PLANES_BASE en orden ascendente; retorna el primero que cumple:
    - max_trabajadores_totales es None (ilimitado) o num_empleados <= max_trabajadores_totales
    - max_sedes >= num_sedes
    - si tiene_contratistas, el plan debe incluir_contratistas
    - si necesita_api_sso, el plan debe incluir_api_sso

    Nunca retorna None — CORPORATIVO es el catch-all final.
    """
    for plan in PLANES_BASE:
        totales = plan.max_trabajadores_totales
        emp_ok   = totales is None or num_empleados <= totales
        sedes_ok = plan.max_sedes >= num_sedes
        cont_ok  = not tiene_contratistas or plan.incluye_contratistas
        sso_ok   = not necesita_api_sso or plan.incluye_api_sso
        if emp_ok and sedes_ok and cont_ok and sso_ok:
            return plan
    return PLANES_BASE[-1]  # CORPORATIVO — nunca debería llegar aquí


def debe_agendar_demo(plan: PlanBase) -> bool:
    """True solo para CORPORATIVO. El resto se cierra vía deep link de compra self-serve."""
    return plan.codigo == "CORPORATIVO"


def deep_link_compra(
    plan: PlanBase,
    ciclo: Ciclo = Ciclo.MENSUAL,
    lead_id: Optional[str] = None,
    nueva_empresa: bool = True,
) -> str:
    """Construye la URL de cierre de venta para un plan SST.

    Para CORPORATIVO devuelve mailto (no hay self-serve).
    Para el resto: https://sst.verifty.com/agregar-vera con query params:
      plan, ciclo, nueva (1/0), lead_id (solo si se pasa).
    """
    if plan.codigo == "CORPORATIVO":
        return "mailto:hola@sst.verifty.com"

    params: list[tuple[str, str]] = [
        ("plan",   plan.codigo),
        ("ciclo",  ciclo.value),
        ("nueva",  "1" if nueva_empresa else "0"),
    ]
    if lead_id:
        params.append(("lead_id", lead_id))

    qs = "&".join(f"{k}={v}" for k, v in params)
    return f"https://sst.verifty.com/agregar-vera?{qs}"


def prompt_inyectable() -> str:
    """Renderiza el catálogo completo como texto listo para inyectar en un system prompt.

    Muestra TRABAJADORES TOTALES como dato principal, con desglose técnico.
    No incluye lógica de segmentación — esa vive en las REGLAS del system prompt.
    """
    lines: list[str] = [
        "═══════════════════════════════════════════════════════════",
        "CATÁLOGO VERIFTY SST — FUENTE ÚNICA DE PRECIOS Y PLANES",
        "═══════════════════════════════════════════════════════════",
        "",
        "PLANES BASE (compra directa en sst.verifty.com/agregar-vera)",
        "─────────────────────────────────────────────────────────────",
    ]

    for p in PLANES_BASE:
        if p.precio_mensual_cop is not None:
            dia_str   = f"($ {p.precio_dia_cop:,.0f}/día)".replace(",", ".")
            precio_str = f"{formato_cop(p.precio_mensual_cop)}/mes {dia_str}"
            anual_str  = (
                f"  |  {formato_cop(precio_con_ciclo(p.precio_mensual_cop, Ciclo.ANUAL))}"
                f"/año (10% dto)"
            )
        else:
            precio_str = "A la medida"
            anual_str  = ""

        if p.max_trabajadores_totales is not None:
            sin_acc = p.max_empleados_sin_acceso
            con_acc = p.max_cuentas
            tot_str = (
                f"Hasta {p.max_trabajadores_totales} trabajadores "
                f"({sin_acc} sin login + {con_acc} con login)"
            )
        else:
            tot_str = "Trabajadores ilimitados"

        sedes_str = "ilimitadas" if p.max_sedes >= 999 else (
            f"{p.max_sedes} sede" + ("s" if p.max_sedes != 1 else "")
        )
        ipevr_str = " | IPEVR (GTC-45)" if p.incluye_ipevr else ""
        cont_str  = " | con contratistas" if p.incluye_contratistas else ""
        sso_str   = " | API + SSO" if p.incluye_api_sso else ""

        lines.append(f"  {p.codigo} — {precio_str}{anual_str}")
        lines.append(f"    {tot_str}")
        lines.append(
            f"    {sedes_str} · {p.almacenamiento_gb} GB"
            f"{ipevr_str}{cont_str}{sso_str}"
        )
        lines.append(f"    {p.descripcion_corta}")
        lines.append(f"    Cuándo: {p.razon_eleccion}")
        lines.append("")

    lines += [
        "PLANES VERA (add-on IA — opcional, se suma al plan base)",
        "─────────────────────────────────────────────────────────────",
    ]
    for v in PLANES_VERA:
        tok_str = (
            f"{v.tokens_mensuales // 1_000}k" if v.tokens_mensuales < 1_000_000
            else f"{v.tokens_mensuales // 1_000_000}M"
        )
        lines.append(
            f"  {v.codigo:<12} | {formato_cop(v.precio_mensual_cop)}/mes"
            f" | {tok_str} tokens/mes | Claude {v.modelo_claude}"
        )
        lines.append(f"               | {v.descripcion_corta}")
        lines.append("")

    lines += [
        "═══════════════════════════════════════════════════════════",
        "INSTRUCCIONES DE USO (para el bot):",
        "- SOLO puedes cotizar los planes listados arriba con los precios listados.",
        "  NO inventes planes ni precios.",
        "- Para CORPORATIVO: no hay self-serve. Usa escalar_a_humano o escalar_a_demo.",
        "- Descuento anual: 10% sobre el total del año (pago anticipado 12 meses).",
        "- Este catálogo es exclusivo de Verifty SST. No menciones planes del",
        "  producto Verifty Flow en conversaciones SST.",
        "═══════════════════════════════════════════════════════════",
        "",
        "─── ACLARACIÓN PARA EL CLIENTE ─────────────────────────────",
        "Si te preguntan 'cómo cuenta los trabajadores':",
        "Cada plan permite un total de trabajadores con SG-SST gestionado,",
        "distribuidos en dos tipos:",
        "  - SIN acceso a la app: trabajadores cuya info SST está en el sistema",
        "    (capacitaciones, exámenes, accidentes) pero no tienen login.",
        "  - CON acceso a la app: trabajadores con cuenta para entrar a la",
        "    plataforma (responsable SST, supervisor, gerente). Su info SST",
        "    también queda en el sistema.",
        "El TOTAL es lo que importa para escoger plan.",
        "Ejemplo: empresa de 8 trabajadores → STARTER te alcanza porque",
        "el techo son 10.",
        "─────────────────────────────────────────────────────────────",
    ]

    return "\n".join(lines)
