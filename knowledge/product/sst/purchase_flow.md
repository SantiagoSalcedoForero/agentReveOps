> ⚠️ PLANES OBSOLETOS EN ESTE DOC: Verifty SST hoy solo tiene Emprende IA / Crece IA / Consolida IA (VERA incluida + prueba gratis 3 días). Ignora cualquier mención de Basic/Starter/Pro/Plus/Corporativo o VERA como add-on. Fuente de verdad: product/icp.md.

# Flujo de compra — Verifty SST

## Pasarela de pago

**Única pasarela: Mercado Pago.** No hay PSE directo, Stripe ni otra opción.

Flujo técnico:
1. Usuario hace clic en "Pagar" en sst.verifty.com/planes
2. Backend crea una preferencia en MP → MP devuelve una URL de pago
3. Usuario es redirigido al checkout de MP (página externa, no modal)
4. Paga en MP → MP lo devuelve a Verifty en /resultado
5. **La confirmación real viene del webhook de MP** (no del redirect). MP notifica a Verifty cuando autoriza la suscripción y cuando procesa el primer cobro. Verifty activa el plan al recibir el webhook (segundos a pocos minutos).

Si hay algún problema técnico con MP: el sistema muestra un fallback con el email **hola@sst.verifty.com** para pago manual.

## Plan gratuito permanente (FREE)

Existe un plan FREE real, sin costo y sin vencimiento:
- Hasta 5 empleados
- 1 usuario con acceso
- Módulos básicos limitados
- 300 MB de almacenamiento

**No es un trial** — la empresa puede quedarse en FREE indefinidamente. Sirve para empresas muy pequeñas que arrancan, pero rápidamente quedan limitadas al crecer.

Cuando presentar el FREE: si el lead tiene 1-4 empleados y quiere "probar antes de pagar". Aclarar que a partir del 5° empleado necesita el plan Basic.

## Descuentos

- **Descuento anual: 10%** — se paga el año completo por adelantado (precio_mensual × 12 × 0.90). Automático en el checkout al seleccionar facturación anual.
- **Cupones**: existen códigos de descuento del 5% al 100%. Aplican durante los primeros 12 meses en planes mensuales, sin límite en anuales. Pedir al equipo comercial si el lead pide descuento.

## Post-compra — ¿qué pasa después de pagar?

### Para empresa nueva (primer registro):
1. Paga en MP → llega a /resultado
2. Hace clic en "Crear mi empresa"
3. Llena formulario: razón social, NIT, sector, ciudad, logo
4. El sistema crea todo de una vez (empresa + usuario owner + primer empleado + suscripción activa)
5. Entra al dashboard

**El acceso NO es inmediato para empresa nueva** — requiere completar el formulario de creación. Avisar al usuario que tiene ese paso antes de entrar.

### Para empresa ya existente (upgrade):
- Acceso inmediato una vez llega el webhook de MP (segundos a pocos minutos)
- La página de /resultado muestra spinner por 4 segundos y luego habilita "Ir al panel"

### ¿Hay onboarding guiado?
No existe actualmente. El usuario entra directo al dashboard estándar. Si la empresa está vacía los KPIs muestran ceros. **El primer módulo recomendado para arrancar es "Empleados" — cargar la nómina es el punto de entrada a todo lo demás.**

### ¿Hay emails automáticos de confirmación?
Actualmente no. No se envía correo de confirmación de compra, activación ni renovación. Si el usuario pregunta "¿me llega un correo?", la respuesta honesta es que debe guardar su acceso desde la página de resultado.

## Facturación y renovación

- **Renovación automática** vía Mercado Pago (suscripción recurrente). MP cobra mensual o anual según lo que eligió el usuario y Verifty actualiza la fecha de vencimiento automáticamente.
- **Vencimiento**: un proceso diario revisa suscripciones vencidas y las marca. Si VERA IA también venció, se desactiva por separado.
- **Cancelación**: requiere contactar a Verifty o ir directamente a Mercado Pago para cancelar la suscripción recurrente. No hay botón de cancelación en la interfaz del usuario actualmente.

## Plan Corporativo

**No tiene flujo diferenciado.** No hay formulario de cotización ni página de contacto enterprise.

Para leads Corporativo (más de 130 empleados, precio a la medida):
- Redirigir a WhatsApp con el equipo comercial (usar [FLOW_LEAD] o [HANDOFF_NEEDED])
- O dar el email directo: **hola@sst.verifty.com**
- El precio es negociable según número real de empleados, módulos requeridos y multi-sede

## Argumentos para objeciones de compra

**"¿Puedo probar antes de pagar?"**
→ Sí: el plan FREE es gratuito y permanente. Tienen acceso real a la plataforma con hasta 5 empleados. Si tienen más, arrancamos con Basic que son $39.000/mes — menos que un almuerzo para dos personas.

**"¿Es seguro pagar por Mercado Pago?"**
→ Mercado Pago es la pasarela más usada en Colombia y Latinoamérica. Acepta tarjetas débito/crédito de todos los bancos, PSE vía MP, y tiene protección al comprador. Verifty nunca ve ni guarda datos de tarjeta — todo va directo a MP.

**"¿Puedo cancelar cuando quiera?"**
→ Sí. La suscripción es mensual (o anual si eligieron ese descuento). No hay penalidad por cancelar.

**"¿Qué pasa si pago y no funciona?"**
→ El acceso se activa en minutos. Si hay algún problema, escriben a hola@sst.verifty.com y el equipo lo resuelve manualmente.

**"¿Me facturan?"**
→ Mercado Pago genera el comprobante de pago. Para factura electrónica formal, solicitarla a hola@sst.verifty.com con el NIT de la empresa.
