"""Catálogo único de planes y precios de Verifty SST.

Fuente de verdad para WhatsApp bot, webchat VERA y cotizaciones email.
Inmutable en runtime — frozen dataclasses, sin acceso a DB ni .env.
Verifty Flow queda fuera de este módulo (opera con handoff a demo).
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
    codigo:               str            # "BASIC" | "STARTER" | "PRO" | "PLUS" | "CORPORATIVO"
    nombre:               str            # "Basic", "Starter", ...
    precio_mensual_cop:   Optional[int]  # None para Corporativo
    max_empleados:        Optional[int]  # None = ilimitado
    max_sedes:            int
    max_cuentas:          int
    almacenamiento_gb:    float
    incluye_ipevr:        bool           # Matriz IPEVR GTC-45 disponible desde STARTER
    incluye_contratistas: bool
    incluye_api_sso:      bool
    descripcion_corta:    str            # 1 línea para el bot
    razon_eleccion:       str            # frase exacta que usa el bot al recomendarlo

    @property
    def precio_dia_cop(self) -> Optional[int]:
        """Precio diario aproximado (precio_mensual / 30), redondeado al entero más cercano."""
        if self.precio_mensual_cop is None:
            return None
        return round(self.precio_mensual_cop / 30)


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
        max_empleados=3,
        max_sedes=1,
        max_cuentas=1,
        almacenamiento_gb=0.25,
        incluye_ipevr=False,
        incluye_contratistas=False,
        incluye_api_sso=False,
        descripcion_corta="Plan básico para empresas micro (hasta 3 empleados)",
        razon_eleccion=(
            "te alcanza el Basic — manejas hasta 3 empleados, "
            "formularios e inspecciones de campo"
        ),
    ),
    PlanBase(
        codigo="STARTER",
        nombre="Starter",
        precio_mensual_cop=220_000,
        max_empleados=7,
        max_sedes=1,
        max_cuentas=3,
        almacenamiento_gb=3,
        incluye_ipevr=True,
        incluye_contratistas=False,
        incluye_api_sso=False,
        descripcion_corta="Empresas pequeñas iniciando SG-SST (hasta 7 empleados)",
        razon_eleccion=(
            "el Starter te queda perfecto — hasta 7 empleados, "
            "capacitaciones, accidentes, programas SST e incluye matriz IPEVR (GTC-45)"
        ),
    ),
    PlanBase(
        codigo="PRO",
        nombre="Pro",
        precio_mensual_cop=600_000,
        max_empleados=30,
        max_sedes=1,
        max_cuentas=20,
        almacenamiento_gb=15,
        incluye_ipevr=True,
        incluye_contratistas=False,
        incluye_api_sso=False,
        descripcion_corta="Empresas medianas con SG-SST formal (hasta 30 empleados)",
        razon_eleccion=(
            "el Pro es el que te sirve — hasta 30 empleados, "
            "salud ocupacional, objetivos e indicadores SST y reportes ejecutivos para gerencia"
        ),
    ),
    PlanBase(
        codigo="PLUS",
        nombre="Plus",
        precio_mensual_cop=1_220_000,
        max_empleados=80,
        max_sedes=10,
        max_cuentas=50,
        almacenamiento_gb=50,
        incluye_ipevr=True,
        incluye_contratistas=True,
        incluye_api_sso=False,
        descripcion_corta="Empresas con múltiples sedes y contratistas (hasta 80 empleados)",
        razon_eleccion=(
            "el Plus es el adecuado — multi-sede, contratistas, "
            "auditorías ISO 45001 y requisitos legales"
        ),
    ),
    PlanBase(
        codigo="CORPORATIVO",
        nombre="Corporativo",
        precio_mensual_cop=None,
        max_empleados=None,
        max_sedes=999,
        max_cuentas=999,
        almacenamiento_gb=999,
        incluye_ipevr=True,
        incluye_contratistas=True,
        incluye_api_sso=True,
        descripcion_corta="Solución a la medida (empleados ilimitados, API, SSO)",
        razon_eleccion=(
            "esto se va a Corporativo — empleados ilimitados, API y SSO, "
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

    Evalúa PLANES_BASE en orden ascendente; retorna el primero que cumple:
    - max_empleados es None (ilimitado) o num_empleados <= max_empleados
    - max_sedes >= num_sedes
    - si tiene_contratistas, el plan debe incluir_contratistas
    - si necesita_api_sso, el plan debe incluir_api_sso

    Nunca retorna None — CORPORATIVO es el catch-all final.
    """
    for plan in PLANES_BASE:
        emp_ok   = plan.max_empleados is None or num_empleados <= plan.max_empleados
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

    Formato compacto y parseable visualmente. No incluye lógica de segmentación —
    esa vive en las REGLAS del system prompt del agente. Solo datos.
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
            precio_str = f"{formato_cop(p.precio_mensual_cop)}/mes"
            anual_str  = f"  |  {formato_cop(precio_con_ciclo(p.precio_mensual_cop, Ciclo.ANUAL))}/año (10% dto)"
        else:
            precio_str = "A la medida"
            anual_str  = ""

        emp_str   = f"hasta {p.max_empleados} emp" if p.max_empleados else "ilimitados"
        sedes_str = "ilimitadas" if p.max_sedes >= 999 else (f"{p.max_sedes} sede" + ("s" if p.max_sedes != 1 else ""))
        ipevr_str = " | IPEVR (GTC-45)" if p.incluye_ipevr else ""
        cont_str  = " | con contratistas" if p.incluye_contratistas else ""
        sso_str   = " | API + SSO" if p.incluye_api_sso else ""

        lines.append(
            f"  {p.codigo:<12} | {emp_str:<16} | {precio_str}{anual_str}"
        )
        lines.append(
            f"               | {sedes_str:<10} | {p.descripcion_corta}{ipevr_str}{cont_str}{sso_str}"
        )
        lines.append(f"               | Cuándo usarlo: {p.razon_eleccion}")
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
        "- Para CORPORATIVO: no hay self-serve. Escala a hola@sst.verifty.com",
        "  o emite [HANDOFF_NEEDED].",
        "- Descuento anual: 10% sobre el total del año (pago anticipado 12 meses).",
        "- Este catálogo es exclusivo de Verifty SST. No menciones planes del",
        "  producto Verifty Flow en conversaciones SST.",
        "═══════════════════════════════════════════════════════════",
    ]

    return "\n".join(lines)
