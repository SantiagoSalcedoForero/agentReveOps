# Perfil de Cliente Ideal (ICP)

## REGLA MAESTRA DE SEGMENTACIÓN

Verifty tiene DOS productos. El bot debe identificar cuál necesita el lead ANTES de intentar
agendar demo o enviar link de compra.

| Producto | ICP | Acción del bot |
|----------|-----|----------------|
| **Verifty SST** | Empresa 5-130 empleados buscando cumplir normativa SST, o profesional/especialista SST | Calificar → [SST_READY] → link de compra (https://sst.verifty.com/planes) |
| **Verifty Flow** | Empresa grande (+130 emp.) o con muchos contratistas buscando automatizar procesos | Calificar → [BOOKING_READY] → agendar demo |

## Matriz de calificación por tamaño — VERIFTY FLOW

| Tamaño empresa | Trabajadores | Estrategia bot | Plan sugerido |
|----------------|-------------|----------------|---------------|
| Micro | < 20 | Solo Flow si tiene contratistas masivos, sino → evaluar SST | INDIVIDUAL |
| Pequeña | 20-130 | Verificar si necesitan SST o Flow. Si mencionan contratistas → Flow | EQUIPO / ESSENTIAL |
| Mediana | 130-500 | Calificar + agendar reu Flow (bot puede cotizar Essential/Advanced) | ESSENTIAL / ADVANCED |
| Grande | 500-1500 | **Agendar reu sin precios** | BUSINESS |
| Enterprise | 1500+ | **Agendar reu sin precios** | CORPORATIVO / PLATINUM |

## Sectores prioritarios (alta conversión histórica)

1. **Construcción e infraestructura** — permisos de alturas, contratistas masivos
2. **Energía** (hidroeléctricas, termoeléctricas, petróleo, gas) — ARL 5
3. **Manufactura y farmacéutica** — sistemas integrados, auditorías
4. **Logística y transporte** — contratistas, mercancía peligrosa (SISCOM)
5. **Minería** — alto riesgo, documentación legal obligatoria

## Clientes referencia (usar en el pitch)

- **AES Colombia** (energía)
- **CFC** (construcción)
- **ECAR** (farmacéutica)
- **Diabonos**
- **Magnetron**
- **Colgate-Palmolive** (manufactura)
- **Cajasan** (mutualidad)
- **Perflex** (pegantes)
- **3 Castillos** (manufactura)

## Stakeholders de compra (quién decide)

1. **Gerente HSEQ / SST** → dolor principal: auditorías, multas, accidentes
2. **Gerente Operaciones / Planta** → dolor: parar producción por contratistas sin docs
3. **Gerente TI** → dolor: integrar con SAP, ISODOC, herramientas existentes
4. **Dueño / CEO empresa pequeña-mediana** → decisor directo

Si el lead es **analista o coordinador SST**, tratar con respeto pero detectar rápido si puede elevarlo al decisor. No cerrar con analistas sin decisor presente.

## ICP — Verifty SST (ver también knowledge/product/verifty_sst.md)

### Tipo A: Empresa pequeña (5–130 empleados)
- Busca cumplir Res. 0312/2019, implementar SG-SST, llevar IPEVR, gestionar accidentes
- Actualmente lo hace en Excel, papel o sin sistema
- Tiene vigía SST o responsable SST sin herramienta

### Tipo B: Profesional / Especialista SST
- Consultor, asesor o profesional SST que gestiona sistemas de uno o varios clientes
- Busca software para llevar los SG-SST de sus clientes de forma organizada
- Señales: "soy especialista SST", "asesoro empresas en SST", "llevo el sistema de varios clientes"

### Señales que identifican un lead SST
- Menciona: SG-SST, COPASST, vigía SST, IPEVR, Res. 0312, accidente laboral, ausentismo
- Empresa 5-130 empleados buscando "cumplir con SST" o "implementar el sistema"
- Se presenta como profesional SST, asesor, coordinador o consultor SST

## Segmentos a los que NO aplica ningún producto

- Empresas < 5 empleados sin riesgo (no justifica inversión)
- Empresas 100% administrativas sin operación de campo ni normativa SST relevante
- Empresas con sistemas SST muy maduros que solo quieren integraciones puntuales (enfocarse en API)

## Geografía (mercados atendidos)

- **Colombia** (principal): SG-SST, Decreto 1072/2015, Res 0312/2019, ARL obligatoria
- **Argentina**: Ley 19587, SRT, ART
- **Perú**: Ley 29783, SUNAFIL, SCTR
- **Chile**: Ley 16744, Mutuales
- **México**: NOM-STPS, IMSS
- **España**: Ley 31/1995 (LPRL), Mutuas

Menciona la normativa local específica del país del lead para mostrar conocimiento.

## Dolores ranqueados (frecuencia validada en campo)

1. **ALTO**: Gestión manual de documentación de contratistas, permisos y procesos SST
2. **ALTO**: Riesgo legal por contratistas sin documentos vigentes en planta
3. **MEDIO**: Necesidad de SG-SST integral desde cero
4. **MEDIO**: Digitalización de permisos de trabajo manuales
5. **BAJO**: Falta de funcionalidad offline para operación en campo

## Señales de calificación alta (lead hot)

- Menciona auditoría próxima
- Ya rechazó otras soluciones ("probé X y no funcionó")
- Tiene contratistas con problemas documentales
- Cambio de gerencia reciente (típicamente buscan digitalizar)
- Accidente reciente en planta
- Expansión (nuevas sedes) que exige estandarización
