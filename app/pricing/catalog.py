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
        codigo="EMPRENDE_IA",
        nombre="Emprende IA",
        precio_mensual_cop=250_000,
        max_empleados_sin_acceso=25,
        max_sedes=3,
        max_cuentas=2,
        almacenamiento_gb=5,
        incluye_ipevr=True,
        incluye_contratistas=False,
        incluye_api_sso=False,
        descripcion_corta="micro/pequeña con IA (hasta 27 trabajadores)",
        razon_eleccion=(
            "el Emprende IA te queda perfecto — hasta 27 trabajadores "
            "(25 gestionados + 2 con acceso), y viene con VERA (la IA) que te "
            "arma y mantiene todo el SG-SST, más todos los módulos SST y el plan "
            "de emergencias. Puedes probarlo gratis 3 días"
        ),
    ),
    PlanBase(
        codigo="CRECE_IA",
        nombre="Crece IA",
        precio_mensual_cop=360_000,
        max_empleados_sin_acceso=75,
        max_sedes=5,
        max_cuentas=4,
        almacenamiento_gb=20,
        incluye_ipevr=True,
        incluye_contratistas=False,
        incluye_api_sso=False,
        descripcion_corta="pequeña/mediana con IA (hasta 79 trabajadores)",
        razon_eleccion=(
            "el Crece IA es el que te sirve — hasta 79 trabajadores "
            "(75 gestionados + 4 con acceso), con VERA incluida y más cupo de IA "
            "para tu operación, 20 GB y 5 áreas. Puedes probarlo gratis 3 días"
        ),
    ),
    PlanBase(
        codigo="CONSOLIDA_IA",
        nombre="Consolida IA",
        precio_mensual_cop=880_000,
        max_empleados_sin_acceso=200,
        max_sedes=8,
        max_cuentas=15,
        almacenamiento_gb=50,
        incluye_ipevr=True,
        incluye_contratistas=False,
        incluye_api_sso=False,
        descripcion_corta="mediana con IA (hasta 215 trabajadores)",
        razon_eleccion=(
            "el Consolida IA es el adecuado — hasta 215 trabajadores "
            "(200 gestionados + 15 con acceso), VERA con el cupo máximo de IA, "
            "50 GB y 8 áreas. Puedes probarlo gratis 3 días"
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

DESCUENTO_ANUAL = 0.05  # 5% anual (política actual)

# ---------------------------------------------------------------------------
# Módulos por plan — Modelo Híbrido C (M4)
# ---------------------------------------------------------------------------
# `incluye`: módulos que ESTE plan agrega sobre el anterior.
# `no_incluye`: módulos de planes superiores que este plan NO tiene.
# Usado para: (a) inyectar en el system prompt y (b) encontrar el plan mínimo
# que tiene un módulo dado cuando el lead lo menciona explícitamente.
# ---------------------------------------------------------------------------

MODULOS_POR_PLAN: dict[str, dict[str, list[str]]] = {
    # Los 3 planes IA incluyen TODOS los módulos SST — se diferencian por
    # capacidad (trabajadores, cupo de IA, almacenamiento, áreas), no por módulos.
    "EMPRENDE_IA": {
        "incluye": [
            "Formularios y firmas digitales",
            "Planes de acción PHVA",
            "Inspecciones de campo con fotos",
            "Reportes de actos y condiciones inseguras",
            "Caminatas de seguridad",
            "Gestor documental",
            "Cronograma SST",
            "EPP e inventario",
            "Accidentes e incidentes (Res. 1401/2007)",
            "Ausentismo e incapacidades (CIE-10)",
            "Capacitaciones y plan anual",
            "Matriz IPEVR GTC-45",
            "Salud ocupacional y exámenes médicos",
            "Objetivos e indicadores SST (Res. 0312/2019)",
            "Programas SST (vigilancia epidemiológica)",
            "Auditorías internas ISO 45001",
            "Matriz de requisitos legales",
            "Perfil sociodemográfico de la plantilla",
            "Plan de emergencias",
            "Autoevaluación 0312",
            "Reportes ejecutivos y dashboard avanzado",
            "VERA (IA) que arma y mantiene todo el SG-SST — INCLUIDA",
        ],
        "no_incluye": [
            "Gestión de contratistas / control de acceso (eso es Verifty Flow — se ve en demo)",
            "API para integraciones y SSO empresarial (Camino B / enterprise)",
        ],
    },
    "CRECE_IA": {
        "incluye": [
            "Formularios y firmas digitales",
            "Planes de acción PHVA",
            "Inspecciones de campo con fotos",
            "Reportes de actos y condiciones inseguras",
            "Caminatas de seguridad",
            "Gestor documental",
            "Cronograma SST",
            "EPP e inventario",
            "Accidentes e incidentes (Res. 1401/2007)",
            "Ausentismo e incapacidades (CIE-10)",
            "Capacitaciones y plan anual",
            "Matriz IPEVR GTC-45",
            "Salud ocupacional y exámenes médicos",
            "Objetivos e indicadores SST (Res. 0312/2019)",
            "Programas SST (vigilancia epidemiológica)",
            "Auditorías internas ISO 45001",
            "Matriz de requisitos legales",
            "Perfil sociodemográfico de la plantilla",
            "Plan de emergencias",
            "Autoevaluación 0312",
            "Reportes ejecutivos y dashboard avanzado",
            "VERA (IA) que arma y mantiene todo el SG-SST — INCLUIDA",
        ],
        "no_incluye": [
            "Gestión de contratistas / control de acceso (eso es Verifty Flow — se ve en demo)",
            "API para integraciones y SSO empresarial (Camino B / enterprise)",
        ],
    },
    "CONSOLIDA_IA": {
        "incluye": [
            "Formularios y firmas digitales",
            "Planes de acción PHVA",
            "Inspecciones de campo con fotos",
            "Reportes de actos y condiciones inseguras",
            "Caminatas de seguridad",
            "Gestor documental",
            "Cronograma SST",
            "EPP e inventario",
            "Accidentes e incidentes (Res. 1401/2007)",
            "Ausentismo e incapacidades (CIE-10)",
            "Capacitaciones y plan anual",
            "Matriz IPEVR GTC-45",
            "Salud ocupacional y exámenes médicos",
            "Objetivos e indicadores SST (Res. 0312/2019)",
            "Programas SST (vigilancia epidemiológica)",
            "Auditorías internas ISO 45001",
            "Matriz de requisitos legales",
            "Perfil sociodemográfico de la plantilla",
            "Plan de emergencias",
            "Autoevaluación 0312",
            "Reportes ejecutivos y dashboard avanzado",
            "VERA (IA) que arma y mantiene todo el SG-SST — INCLUIDA",
        ],
        "no_incluye": [
            "Gestión de contratistas / control de acceso (eso es Verifty Flow — se ve en demo)",
            "API para integraciones y SSO empresarial (Camino B / enterprise)",
        ],
    },
}

_PLANES_BASE_IDX: dict[str, PlanBase] = {p.codigo.upper(): p for p in PLANES_BASE}
_PLANES_VERA_IDX: dict[str, PlanVera] = {p.codigo.upper(): p for p in PLANES_VERA}


# ---------------------------------------------------------------------------
# Helpers públicos
# ---------------------------------------------------------------------------

def get_plan_base(codigo: str) -> Optional[PlanBase]:
    """Lookup case-insensitive por código. Retorna None si no existe."""
    return _PLANES_BASE_IDX.get(codigo.upper())


def get_modulos_plan(codigo: str) -> dict[str, list[str]]:
    """Retorna {incluye: [...], no_incluye: [...]} para el plan dado."""
    return MODULOS_POR_PLAN.get(codigo.upper(), {"incluye": [], "no_incluye": []})


def encontrar_plan_minimo_con_modulo(nombre_modulo: str) -> Optional[PlanBase]:
    """Encuentra el plan más barato que incluye el módulo dado (búsqueda por substring).

    Recorre PLANES_BASE de menor a mayor precio. Retorna el primero cuya lista
    `incluye` en MODULOS_POR_PLAN contiene `nombre_modulo` (case-insensitive).
    Retorna None si ningún plan lo incluye.

    Usado en el Modelo Híbrido C: cuando el lead menciona explícitamente un módulo,
    se puede encontrar el plan mínimo que lo cubre y compararlo con el recomendado.
    """
    keyword = nombre_modulo.lower()
    for plan in PLANES_BASE:
        modulos = MODULOS_POR_PLAN.get(plan.codigo, {}).get("incluye", [])
        if any(keyword in m.lower() for m in modulos):
            return plan
    return None


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
    """Los 3 planes IA se cierran self-serve. La demo (Camino B) es para >215
    trabajadores o contratistas/Flow — eso se maneja en agent.py, no acá."""
    return False


def deep_link_compra(
    plan: PlanBase,
    ciclo: Ciclo = Ciclo.MENSUAL,
    lead_id: Optional[str] = None,
    nueva_empresa: bool = True,
) -> str:
    """Construye la URL de cierre de venta para un plan SST con IA.

    Va DIRECTO a /pagar (no a /agregar-vera): los planes IA ya traen VERA
    incluida, y /pagar muestra el botón de PRUEBA GRATIS de 3 días.
    Query params: plan, ciclo (mensual/anual), nueva (1/0), lead_id (opcional).
    """
    params: list[tuple[str, str]] = [
        ("plan",   plan.codigo),
        ("ciclo",  ciclo.value),
        ("nueva",  "1" if nueva_empresa else "0"),
    ]
    if lead_id:
        params.append(("lead_id", lead_id))

    qs = "&".join(f"{k}={v}" for k, v in params)
    return f"https://sst.verifty.com/pagar?{qs}"


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
        "PLANES BASE (compra directa en sst.verifty.com/pagar — con prueba gratis 3 días)",
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
        mods = MODULOS_POR_PLAN.get(p.codigo, {})
        if mods.get("incluye"):
            lines.append(f"    Incluye: {' · '.join(mods['incluye'])}")
        if mods.get("no_incluye"):
            lines.append(
                f"    NO incluye (plan superior): {' · '.join(mods['no_incluye'])}"
            )
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
