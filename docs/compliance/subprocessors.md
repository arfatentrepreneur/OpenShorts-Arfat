# Subencargados de tratamiento — OpenShorts Cloud

**Responsable:** TONVI TECH SL · NIF B-19780394 · Calle Puerta del Mar 18, 5º,
29005 Málaga (España) · info@openshorts.app · info@openshorts.app
**Versión:** 4 de septiembre de 2026 · **Anterior:** — (primera versión)

Lista nominal de todos los terceros que tratan datos personales por cuenta de
TONVI TECH SL al prestar OpenShorts Cloud, con qué recibe cada uno, dónde está
y qué garantiza la transferencia cuando sale del EEE (arts. 28 y 44-49 RGPD).
Es la versión de referencia del apartado 4 de la
[política de privacidad](https://www.openshorts.app/privacidad).

Los cambios se anotan al final. Un cliente B2B que quiera aviso previo de altas
puede pedirlo en info@openshorts.app.

---

## 1. Procesado de vídeo e IA

| Proveedor | Entidad y país | Qué recibe | Garantía de transferencia | DPA |
|---|---|---|---|---|
| **Google (Gemini API)** | Google LLC / Google Ireland Ltd. — EE. UU. | Transcripción, fotogramas muestreados (pueden incluir caras), foto de referencia del presentador para miniaturas, y el **archivo de vídeo completo** solo en la comprobación de encuadre "screencast" (se borra del File API en cuanto responde) | EU-US Data Privacy Framework (Google LLC certificado) + CCT | Google Cloud / AI Studio paid data terms — **verificar que la clave gestionada pertenece a un proyecto de pago**: los términos gratuitos permiten entrenamiento |
| **ElevenLabs** | ElevenLabs Inc. — EE. UU. | Audio del clip para doblaje (voz de personas reales), texto para TTS | DPF (certificado) + CCT | Pendiente de firma/archivo |
| **fal.ai** | Features & Labels, Inc. — EE. UU. | Foto del actor (puede ser de una persona real), audio a sincronizar, vídeo generado. Modelos: Flux 2 Pro, Kling AI-Avatar, Hailuo | **Sin certificación DPF conocida → CCT obligatorias** | Pendiente de firma/archivo |

## 2. Infraestructura y almacenamiento

| Proveedor | Entidad y país | Qué recibe | Garantía | DPA |
|---|---|---|---|---|
| **Hetzner Online GmbH** | Alemania | Servidores de la API y base de datos | Dentro del EEE | DPA estándar de Hetzner |
| **Contabo GmbH** | Alemania | Servidores | Dentro del EEE | DPA estándar de Contabo |
| **Cloudflare R2** | Cloudflare, Inc. — EE. UU. / región UE del bucket | Clips, metadatos de proyecto (incluida la transcripción), copias de seguridad | DPF + CCT (Cloudflare Customer DPA) | Automático con la cuenta — **verificar que el bucket está en jurisdicción UE** |
| **Cloudflare (DNS + CDN)** | Cloudflare, Inc. — EE. UU. / global | IP y metadatos de petición de cada visitante del sitio | DPF + CCT | Cloudflare Customer DPA |
| **Amazon Web Services (S3)** | AWS EMEA SARL — región `eu-west-3` (París) | Galería pública UGC e imágenes de actor, solo si el usuario opta por publicar | Dentro del EEE (región UE) | AWS Service Terms / DPA |

## 3. Pagos, facturación y correo

| Proveedor | Entidad y país | Qué recibe | Garantía | DPA |
|---|---|---|---|---|
| **Stripe** | Stripe Payments Europe Ltd. (Irlanda) / Stripe, Inc. (EE. UU.) | Email, nombre y dirección fiscal, datos de tarjeta (nunca pasan por nuestros servidores), historial de pagos | DPF + CCT | Incluido en el Stripe Services Agreement |
| **Aikount** (sistema propio de facturación) | TONVI TECH SL — servidores en Alemania | `stripe_customer_id`, nombre fiscal, email y dirección importados de Stripe para emitir la factura legal española | Dentro del EEE; **mismo responsable**, no es un tercero | Sistema interno |
| **Namecheap Private Email** | Namecheap, Inc. — EE. UU. | Dirección de email y contenido de los mensajes de servicio | **Sin certificación DPF conocida → CCT obligatorias** | Pendiente de firma/archivo |

## 4. Distribución y analítica

| Proveedor | Entidad y país | Qué recibe | Garantía | DPA |
|---|---|---|---|---|
| **Upload-Post** | TONVI TECH SL | Publicación en las redes que el usuario conecta; **custodia los tokens OAuth** de TikTok/YouTube/Instagram (OpenShorts no almacena ninguno, solo el nombre de perfil) | Mismo responsable | Sistema interno — su política debe cubrir esta custodia |
| **OpenPanel** (instancia propia) | TONVI TECH SL — servidores en Alemania | Eventos de uso con el uuid de la cuenta como `profileId`. **Nunca el email** (retirado del `identify` del navegador el 4-sep-2026). Solo tras consentimiento | Dentro del EEE; script servido desde el propio dominio | Sistema interno |
| **Google (iniciar sesión con Google)** | Google Ireland Ltd. / Google LLC | Solo el ámbito `openid email profile`: dirección e identificador de cuenta | DPF + CCT | Google Terms |

## 5. Descarga de vídeo (proxies)

| Proveedor | País | Qué recibe | Garantía |
|---|---|---|---|
| **DataImpulse** (proxy residencial por GB) | ❓ **verificar sede y términos** | La URL del vídeo y sus bytes. Ningún dato de cuenta | CCT si está fuera del EEE |
| **Proxies ISP estáticos** (proveedor por confirmar) | ❓ **verificar** | Igual | CCT si está fuera del EEE |

## 6. Terceros que YA NO reciben datos

| Proveedor | Qué recibía | Retirado |
|---|---|---|
| **Google Fonts** (`fonts.googleapis.com`, `fonts.gstatic.com`) | La IP de cada visitante, en cada carga de página, sin consentimiento y sin base jurídica | 4-sep-2026 — las tipografías se sirven desde el propio dominio (`dashboard/public/fonts.css`) |
| **openpanel.dev** (script de terceros) | La IP de cada visitante antes de cualquier consentimiento | 4-sep-2026 — `op1.js` se sirve desde el propio dominio y solo tras aceptar |
| **Telegram Bot API** (Telegram FZ-LLC, Dubái, EAU) | **Direcciones de email de clientes** y títulos de vídeos, en las alertas operativas | 4-sep-2026 — las alertas identifican al usuario por los 8 primeros caracteres de su uuid y ya no citan títulos, de modo que Telegram deja de recibir datos personales. El canal sigue existiendo para alertas técnicas |

## 7. Pendiente de verificación o firma

Nada de esto se puede hacer desde el repositorio; queda para el responsable:

1. **Confirmar que la `MANAGED_GEMINI_API_KEY` pertenece a un proyecto de
   pago.** Los términos gratuitos de AI Studio permiten usar los datos para
   mejorar los modelos, lo que haría falsa la frase "no se entrena con tu
   contenido".
2. **Firmar y archivar** los DPA de ElevenLabs, fal.ai (+ CCT) y Namecheap
   (+ CCT). Guardar los PDF con fecha.
3. **Verificar la jurisdicción del bucket R2** (debe ser UE) y la región de S3.
4. **Identificar al proveedor de proxies estáticos** y el país de DataImpulse,
   y firmar CCT si están fuera del EEE.
5. **Confirmar dónde están físicamente los dos servidores de producción.** La política dice
   "Hetzner y Contabo, Alemania"; si alguno es hardware propio fuera de un CPD,
   hay que decirlo y aplicar cifrado de disco.
6. **Comprobar que la política de Upload-Post** describe la custodia de tokens
   de redes sociales en nombre de usuarios de OpenShorts.

## Historial de cambios

| Fecha | Cambio |
|---|---|
| 2026-09-04 | Primera versión publicada. Altas documentadas (ya en uso, no listadas antes): fal.ai, Cloudflare CDN/DNS, Aikount, OpenPanel, proxies de descarga, Google OAuth. Bajas: Google Fonts, script de openpanel.dev y datos personales hacia Telegram. |
