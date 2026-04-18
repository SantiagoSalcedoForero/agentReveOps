# Módulos de Verifty

Verifty es un **sistema operativo industrial** con 8 módulos + un workflow engine que los conecta. La filosofía: *"el software se adapta al ADN de tu empresa, no al revés"*.

## Los 8 módulos

### 1. Capacitaciones (LMS SST)
- Cursos virtuales, presenciales, híbridos
- Evaluaciones digitales con calificación automática
- Asistencia por Face ID biométrico, QR, firma o confirmación del instructor
- **Seguimiento de brechas:** notifica automáticamente a quien no asistió hasta cerrar la brecha
- Dolor que resuelve: *"¿cómo sabes que tu gente SÍ asistió y no firmó por el compañero?"*

### 2. Formatos Digitales (Formularios)
- Creador tipo Google Forms pero con superpoderes: secciones anidadas, secciones repetibles, referenciar trabajador (precarga cédula, cargo, certificados)
- Campos: texto, fecha, foto, video, geolocalización, firma garabato, lectura de trabajador
- Plantillas incluidas: ATS, permisos, inspecciones, checklists
- **Autodiligenciamiento (preforma):** el 90% del formato pre-llenado; usuario solo llena lo que cambia
- Versionado completo de formatos

### 3. Inventario EPP y Equipos
- Hoja de vida digital por elemento (EPPs, vehículos, escaleras, arnés, extintores)
- Inspecciones periódicas ligadas al elemento (se guardan en su historial)
- Alertas 30 días antes de vencimiento
- Bloqueo automático de entrega sin inspección vigente
- Transferencias entre bodegas y personas con trazabilidad

### 4. Cronogramas / Calendario SST
- Cada trabajador ve en su celular qué debe hacer hoy
- Integra capacitaciones, inspecciones, entregas EPP, planes de acción
- Alertas automáticas de incumplimiento por WhatsApp / correo / in-app
- Integrable con Google Workspace / Microsoft

### 5. Permisos de Trabajo (Alto Riesgo)
- Alturas, espacios confinados, caliente, eléctrico, excavaciones
- Flujos multifase: inicio → revisiones intermedias programadas → cierre
- Firmas digitales con timestamp y hash inmutable
- Suspender/cancelar permiso por lluvia o desvío (queda registrado con foto + geolocalización)
- Check intermedio: contratista sube foto → responsable aprueba/rechaza remotamente

### 6. Control de Ingresos (Gatekeeper con IA)
- OCR + IA valida documentos de contratistas en segundos (planillas SS, ARL, cédulas, SOAT, tecnomecánica, pólizas RC)
- Face ID y QR para control de acceso
- **Bloqueo automático** si documentos vencidos (ARL, EPS, certificaciones)
- **Scrapers disponibles hoy:** ARL (Sura, Positiva, Colmena, Bolívar), Policía Nacional (RMC + antecedentes judiciales), Ministerio de Trabajo (certificado alturas), SISCOM (sustancias peligrosas)
- **En desarrollo:** Policía completa (descarga doble), RUNT (~25 días), espacios confinados
- Integrable con hardware existente (High Vision, huella, torniquetes)

### 7. Control de Contratistas
- Jerarquía: Empresa → Sedes → Contratistas → Equipos → Trabajadores
- Contratistas tienen cuenta propia para subir sus documentos (quita carga al cliente)
- Permisos granulares por rol
- Conexión con planillas vía API a través de socio de enlace operativo (75% cobertura del mercado colombiano)

### 8. Gestor Documental (Document Compliance Engine / DCE)
- No es un drive: son **políticas** sobre documentos
- Por cada documento define: periodicidad (única / diaria / semanal / mensual / anual / 2 años), días de alerta previa, días de gracia, entidad destino (empresa, persona, vehículo)
- OCR valida que el documento cumpla criterios (fechas, NIT, cédulas matching)
- Si ARL, se puede validar vía scraping directo sin pedir PDF

## Workflow Engine (lo que conecta todo)

Canvas visual con nodos arrastrables. Bot debe mencionar esto como el **diferenciador clave**:

### Disparadores
- Manual (botón)
- Automático: nueva empresa, nuevo trabajador, vencimiento de documento

### Nodos disponibles
- **Formularios** (llamar formatos del módulo Formatos Digitales)
- **Control de documentos** (pedir docs con política)
- **Face ID** (validar identidad)
- **OCR** (leer y validar documento)
- **Scraping** (consultar fuente externa)
- **WhatsApp / Email / In-app** (notificar)
- **Condicional** (if/else según respuestas previas)
- **Espera** (pausar N horas entre pasos)
- **Aprobación humana** (bloqueante hasta que alguien apruebe)
- **Subflujos** (anidar workflows completos dentro de otros)
- **Crear/llamar entidad** (empresa, persona, vehículo)
- **Cambio de estado** (activar/desactivar por equipo/sede)
- **Registro hora entrada/salida**
- **Analítica** (enviar data a dashboard)

### Ejemplo típico: ingreso contratista
1. Disparador: manual o automático
2. Formato solicitud (unidad, sede, fecha, actividad, tipo vinculación)
3. Condicional por tipo vinculación → persona natural o jurídica
4. Crear/llamar empresa + invitar operador por correo
5. Operador sube planilla → OCR valida + scraping ARL
6. Condicional trabajo alturas → certificado Mintrab (scraping)
7. Aprobación interventor
8. Aprobación gestión humana (subflujo)
9. Face ID en portería
10. Registro hora entrada → tabla de acceso

## Diferenciadores vs competencia

- **Vs Excel:** customizable pero también automatizado, verificado biométricamente, legal
- **Vs ERPs rígidos (SAP, ISODOC, SIADC):** se adapta en días, no en meses
- **Vs otros SaaS SST:** workflow engine permite construir flujos que NINGÚN otro ofrece
- **Vs Zoho / bots genéricos:** somos especialistas verticales en seguridad industrial

## Integraciones

- API bidireccional con SAP Business One, ERPs, HRIS
- Active Directory / Google Workspace / Microsoft (SSO)
- Hardware de acceso (High Vision, huellas, torniquetes)
- Google Calendar / Workspace
- WhatsApp Business API (Meta Cloud)

## Infraestructura

- Dos nubes: Oracle (principal) + AWS (secundaria)
- SLA estándar 95%, upgrade a 98-99% con replicación (costo extra)
- Backups: 1 incluido, más = addon
- Todos los archivos del cliente son accesibles por el cliente
