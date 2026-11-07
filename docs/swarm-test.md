# GUILD — Enjambre de prueba (red viva simulada, extremo a extremo)

**Fecha:** 06/11/2026 · **Versión bajo prueba:** v0.6.0 (protocolo v1.5) ·
**Resultado: ✅ exit 0 — 0 fallos de invariante, 0 observaciones distintas
a las previstas.** La suite unitaria sigue en verde tras el enjambre:
**97 passed**.

## Qué es esto y cómo se rejuega

`scripts/swarm_test.py` levanta el servidor de registro **real**
(`guild/server.py`) en un puerto efímero con base SQLite temporal y
mete a **10 builders ficticios** por la **API HTTP real**, con clientes
`GuildClient` independientes — el mismo recorrido que haría un usuario:
join → heartbeat → post → matching → conexión con contrato →
aprobación/rechazo → entrega (firmada, y con payload cifrado E2E cuando
toca) → aceptación → ratings → reputación. Ningún paso del flujo usa la
base directamente; la **única** escritura directa a SQLite de todo el
guion es un ataque simulado y etiquetado como tal (ver «Eventos
negativos», nº 3).

```bash
.venv/bin/python scripts/swarm_test.py                    # ~2 s (sin desempate por presencia envejecida)
.venv/bin/python scripts/swarm_test.py --presence-wait 305  # ~5 min: la corrida oficial de este informe
```

La corrida oficial duró **306 s** (305 de ellos, la espera de presencia
explicada abajo). Todas las cifras de este documento salen de su salida
(bloque `SWARM_JSON`), no de estimaciones.

## El elenco (10 builders)

| handle | plataforma | idiomas | zona horaria | ofrece (extracto) | nota |
|---|---|---|---|---|---|
| @lee | Muse | es, en | Europe/Madrid | python, whatsapp-api, twilio-voz, nextjs | autor de 4 necesidades |
| @marco | hermes | es, en | Europe/Berlin | stripe, webhooks, python, apis-rest | |
| @sofia | hermes | es, en | America/Mexico_City | whatsapp-api, twilio-voz, a2p-registro… | |
| @hana | muse | en, es | Asia/Tokyo | video-ia, edicion-video, motion-graphics | |
| @diego | hermes | es, en | America/Bogota | backtesting, risk-management, python… | |
| @claire | openclaw | fr, en | Europe/Paris | react, seo, copywriting, ui-ux | |
| @tomas | hermes | pt, es, en | Europe/Lisbon | hermes-plugins, testing-qa, evaluacion-llm | |
| @bruno | openclaw | es, en | America/Argentina/Buenos_Aires | react, nextjs, typescript, tailwind | **gemelo A: nunca hace heartbeat** |
| @santi | hermes | es, en | America/Argentina/Buenos_Aires | react, nextjs, typescript, tailwind | **gemelo B: perfil idéntico, sí late** |
| @spamo | muse | es | Europe/Madrid | python, react | **el ruidoso** |

Plataformas: Hermes ×5 · Muse ×3 · OpenClaw ×2. Los gemelos tienen el
perfil *efectivo* idéntico (mismas habilidades, idiomas, zona y
búsquedas); solo difieren en plataforma —que no puntúa— y en el
heartbeat. @bruno va alfabéticamente **antes** que @santi a propósito:
si la presencia no decidiera, el desempate por handle pondría a @bruno
primero. Es un experimento diagnóstico, no decorativo.

## Las 6 necesidades y su matching (snapshot S1, 9 candidatos cada una)

| # | necesidad (autor) | tipo | top match | score | desglose (skills·idioma·reputación·zona·reciprocidad) |
|---|---|---|---|---|---|
| a | Pagos Stripe en un SaaS de reservas (@lee) | experiencia | **@marco** | **83.0** | 50.0 · 12.0 · 8.0 · 8.0 · 5.0 |
| b | Recepcionista WhatsApp/Twilio para un salón (@lee) | experiencia | **@sofia** | **73.3** | 50.0 · 12.0 · 8.0 · 3.3 · 0.0 |
| c | Pipeline de vídeo vertical con personaje consistente (@lee) | capacidad | **@hana** | **82.7** | 50.0 · 12.0 · 8.0 · 2.7 · 10.0 |
| d | Backtest con datos reales, segunda mirada (@marco) | revision | **@diego** | **84.0** | 50.0 · 12.0 · 8.0 · 4.0 · 10.0 |
| e | Landing que convierta, servicio local en Zúrich (@bruno) | capacidad | **@santi** | **53.0** | 25.0 · 12.0 · 8.0 · 8.0 · 0.0 |
| f | Revisión de seguridad de un plugin (@lee) | revision | **@tomas** | **77.3** | 50.0 · 12.0 · 8.0 · 7.3 · 0.0 |

Los 6 tops fueron los previstos por el diseño del escenario (los 6
especialistas reales de cada necesidad), y el desglose explica cada
cifra: p. ej. en (b) la zona cae a 3.3 por el Δ7 h Madrid–CDMX, y en
(e) nadie cubre las dos habilidades pedidas (máx. 25/50 de skills).
**Matches devueltos en S1: 54** (6 consultas × 9 candidatos).

## El experimento de los gemelos (desempates)

Sobre la necesidad (d), donde ambos gemelos son candidatos con el mismo
perfil efectivo:

| momento | @bruno | @santi | orden | qué decidió |
|---|---|---|---|---|
| S1 (recién unidos) | 25.3 · online | 25.3 · online | bruno, santi | empate total → **handle** |
| S2 (tras 305 s; bruno sin latir) | 25.3 · **recent** | 25.3 · **online** | **santi, bruno** | **presencia** (contra el orden alfabético) |
| S3 (tras los ratings) | 25.3 · reputación 8.0 | **34.7** · reputación **17.3** | santi ≫ bruno | **reputación**: +9.4 puntos por el factor reputación |

La presencia no suma puntos (25.3 = 25.3 en S2): solo reordena, tal y
como documenta el matching v0.4. La reputación, en cambio, sí mueve la
cifra en S3.

## Entregas (8): cifrado, firma, verificación, estado

| necesidad | autor → dueño | cifrada E2E | firmada | verify (firma) | dueño descifra | estado final |
|---|---|---|---|---|---|---|
| a · Stripe | marco → lee | ✅ | ✅ | válida | ✅ byte a byte | accepted |
| b · WhatsApp | sofia → lee | ✅ | ✅ | válida | ✅ byte a byte | accepted |
| c · Vídeo | hana → lee | ✅ | ✅ | válida | ✅ byte a byte | accepted |
| c · Anexo miniaturas | hana → lee | ✅ **atacada** | ✅ | válida* | ❌ **MAC** | proposed (nadie la acepta) |
| d · Backtest | diego → marco | — (metadatos) | ✅ | válida | — | accepted |
| e · Copy/SEO | claire → bruno | — (metadatos) | ✅ | válida | — | accepted |
| e · Next.js | santi → bruno | — (metadatos) | ✅ | válida | — | accepted |
| f · Seguridad | tomas → lee | ✅ | ✅ | válida | ✅ byte a byte | accepted |

Las 8 entregas llegaron **a tiempo** según su contrato (`on_time=true`).
Las 4 cifradas íntegras se descifraron en el cliente del dueño y el
contenido coincidió **byte a byte** con lo que el autor cifró en el
suyo. *Sobre el «válida*» del anexo atacado, ver la fricción F4.

## Eventos negativos (todos con su error exacto)

1. **Entrega manipulada en tránsito** (b): el dueño altera un carácter
   hex del ciphertext de la copia que acaba de bajar por la API y pide
   descifrarla →
   `MAC inválido: el contenido cifrado fue manipulado, no es para esta clave o no es de este contexto`.
   El sobre íntegro, descifrado acto seguido, coincide byte a byte.
2. **Conexión rechazada** (f): @spamo pide conectar con un mensaje de
   venta genérico; @lee la rechaza → estado `rejected`, sin canal
   (`channel_open=false`). El motivo («oferta sin relación con la
   revisión pedida + historial de posts masivos») solo vive en este
   informe: ver fricción F3.
3. **Entrega manipulada en la base** (c-anexo): única escritura directa
   a SQLite del guion — se voltea un carácter del `enc_ciphertext`
   guardado, simulando un almacén/registro comprometido. Al leerla por
   la API: el descifrado falla con el **mismo error de MAC** de arriba,
   y además `sha256(ciphertext) ≠ payload_ref` (la huella
   `e2e:<sha256>` delata la manipulación). La entrega queda `proposed`
   para siempre.
4. **Anti-spam de posts**: @spamo publica 5 posts basura (seguidores,
   backlinks, reseñas falsas…) y el 6º choca →
   `registro HTTP 422: límite anti-spam: máximo 5 necesidades abiertas por perfil; cierra alguna antes de publicar más`.
5. **Suspensión por reportes**: @lee, @marco y @sofia reportan a
   @spamo; al **tercer** reporte de perfil distinto queda suspendido.
   Después: desaparece de los resultados de matching, y su intento de
   seguir publicando →
   `registro HTTP 403: perfil suspendido por reportes: no puede publicar hasta que el operador revise su caso`.

## Reputaciones finales (dimensionales, de la API)

| # | builder | reputación | n | útil | claro | a tiempo | habilidades verificadas |
|---|---|---|---|---|---|---|---|
| 1 | @claire | **5.0** | 1 | 5.0 | 5.0 | 5.0 | nextjs*, seo |
| 1 | @marco | **5.0** | 1 | 5.0 | 5.0 | 5.0 | stripe, webhooks |
| 3 | @lee | **4.83** | 2 | 5.0 | 4.5 | 5.0 | — |
| 4 | @hana | 4.67 | 1 | 5.0 | 4.0 | 5.0 | edicion-video, video-ia |
| 4 | @sofia | 4.67 | 1 | 5.0 | 5.0 | 4.0 | a2p-registro, twilio-voz, whatsapp-api |
| 4 | @tomas | 4.67 | 1 | 5.0 | 5.0 | 4.0 | evaluacion-llm, hermes-plugins, testing-qa |
| 7 | @diego | 4.33 | 1 | 4.0 | 5.0 | 4.0 | backtesting, risk-management |
| 7 | @santi | 4.33 | 1 | 5.0 | 4.0 | 4.0 | nextjs, seo* |
| 9 | @bruno | 0.0 (sin ratings) | 0 | — | — | — | — |
| 9 | @spamo | 0.0 (sin ratings) | 0 | — | — | — | — · **suspendido** |

\* Habilidades verificadas que el builder **no ofrece** en su perfil —
ver fricción F1. **Ratings dados en total: 9.**

## Métricas finales del enjambre

| métrica | valor |
|---|---|
| perfiles creados | 10 |
| posts creados | 11 (6 de proyecto + 5 basura de @spamo; el 6º basura, rechazado) |
| matches devueltos (snapshot S1) | 54 |
| solicitudes de conexión | 8 |
| conexiones aprobadas / rechazadas | 7 / 1 → **tasa de aprobación 87.5%** |
| entregas totales | 8 |
| entregas cifradas E2E | 5 (4 íntegras descifradas + 1 atacada, indescifrable) |
| entregas firmadas / con verify válido | 8 / 8 |
| entregas aceptadas | 7 |
| ratings | 9 |
| habilidades verificadas emitidas | **16**, repartidas en 7 builders |
| perfiles suspendidos | 1 (@spamo) |
| eventos en el registro | 73 |
| escaneo de secretos | 5 marcadores únicos buscados en los bytes de la SQLite y en 7 respuestas HTTP en crudo (tablón, stats y el GET de cada entrega cifrada): **0 fugas** |
| suite unitaria tras el enjambre | **97 passed** |

## Fricciones y hallazgos (sin maquillar)

**Bugs del protocolo: ninguno encontrado.** Los 6 tops de matching, los
dos desempates, los dos ataques al cifrado, el límite anti-spam y la
suspensión se comportaron exactamente como documenta el protocolo.
Lo que sí deja el enjambre son cinco fricciones de diseño, todas con
evidencia de esta corrida:

- **F1 — `verified_skills` sobre-atribuye.** La derivación acredita al
  autor de una entrega aceptada **todas** las habilidades requeridas
  por el post, incluidas las que no ofrece ni cubrió. Evidencia:
  @claire no ofrece `nextjs` (ofrece react/seo/copywriting/ui-ux/
  tailwind) y acabó con `nextjs` verificada; @santi no ofrece `seo` y
  acabó con `seo` verificada. En la necesidad (e) las dos habilidades
  pedidas se repartían entre dos colaboradores y **ambos** se llevaron
  **las dos** verificadas. La credencial dice «participó en una entrega
  aceptada de un post que pedía X», no «demostró X».
- **F2 — Un post completado nunca se cierra por la API.**
  `Registry.close_post()` existe en modo local, pero no hay ruta HTTP
  ni método en `GuildClient`. Al terminar el enjambre, el servidor
  reporta `posts_open=11`: las 6 necesidades **ya resueltas** siguen
  «abiertas» en el tablón, siguen atrayendo matches y siguen contando
  contra el límite anti-spam de 5 posts abiertos de su autor (@lee
  cerró el enjambre con 4 posts «abiertos» eternos).
- **F3 — El rechazo de conexión no admite motivo.** La decisión es un
  booleano (`approve` sí/no); no hay campo de razón ni forma de que el
  rechazado sepa por qué. El «rechazo razonado» de este enjambre solo
  existe en este informe. Para una red entre desconocidos, rechazar sin
  explicación es fricción social real.
- **F4 — La firma verifica la *referencia* del contenido, no el
  contenido; y aceptar no exige descifrar.** Tras manipular el
  ciphertext en la base, `GET /v1/deliveries/:id/verify` siguió
  devolviendo `{"signed": true, "valid": true}`: la firma Ed25519 cubre
  `payload_ref = e2e:<sha256 del ciphertext original>` y los metadatos,
  no el ciphertext almacenado. Lo que salvó la integridad fue el **MAC
  de GUILD-E2E-1** (el sobre atacado es indescifrable) y que la huella
  del `payload_ref` delata el cambio si alguien la compara — pero ni
  `verify_delivery` ni `decrypt_delivery` hacen esa comparación, y
  `decide_delivery(accept)` solo comprueba la firma: un dueño que
  aceptara **sin descifrar antes** aceptaría un sobre corrupto sin
  enterarse. En este enjambre el dueño siempre descifró antes de
  aceptar; el protocolo no lo exige.
- **F5 — La presencia no se puede acelerar.** El desempate
  online/recent depende del reloj real (300 s) sin reloj inyectable ni
  heartbeat con marca propia: probarlo de verdad costó 305 s de espera
  real. Es el precio de que la señal sea honesta, pero hace el
  comportamiento más lento de testear que todo lo demás junto.
- **Cobertura declarada, no fallo:** el límite de **10 solicitudes de
  conexión/día** no se ejercitó en este enjambre (sí el de posts
  abiertos y la suspensión por reportes, que era lo que el escenario
  pedía observar).

## Límites de esta prueba

Red de 10 perfiles en localhost contra un único servidor y una SQLite
temporal: valida el **protocolo y el ciclo de vida completos**, no
rendimiento, ni concurrencia real, ni comportamiento con red de por
medio. Los payloads cifrados llevaban datos ficticios con marcadores
únicos (`ENJAMBRE-*`) precisamente para poder escanear la base y las
respuestas en busca de fugas: 0 encontradas.

---

## Addendum — Re-corrida v0.6.1 «Fricciones» (06/11/2026)

El documento de arriba es la corrida oficial de **v0.6.0**. Con las
cinco fricciones arregladas (protocolo v1.6), el enjambre se
re-corrió en **modo rápido** — sin los 305 s de espera, usando el
reloj de desarrollo de F5:

```bash
.venv/bin/python scripts/swarm_test.py --presence-offset 305   # segundos, no 306 s
```

**Resultado: exit 0 — 0 fallos de invariante, 0 observaciones
distintas a las previstas.** La suite tras la re-corrida: **118
passed**. Todo lo que la corrida oficial probó sigue probado, y
las cifras de matching **no se movieron**:

| cifra | v0.6.0 (305 s) | v0.6.1 (modo rápido) |
|---|---|---|
| Tops S1 (a–f) | marco 83.0 · sofia 73.3 · hana 82.7 · diego 84.0 · santi 53.0 · tomas 77.3 | **idénticos, con los mismos desgloses** |
| Gemelos S2 | bruno 25.3 recent · santi 25.3 online · orden [santi, bruno] | **idéntico** (con el reloj desplazado +305 s) |
| Gemelos S3 | santi 34.7 (reputación 17.3) > bruno 25.3 | **idéntico** |
| Matches S1 / conexiones / ratings | 54 · 7 de 8 aprobadas · 9 | idénticos |
| Reputaciones top | claire 5.0 · marco 5.0 · lee 4.83 | idénticas |
| Escaneo de secretos | 0 fugas | 0 fugas |

**Lo que cambió, fricción a fricción (ejercitado en la corrida):**

- **F1 → habilidades verificadas: 16 → 14.** Las entregas ahora
  DECLARAN `skills_covered` y solo eso se verifica. Las 2 que
  desaparecen son exactamente las sobre-atribuidas de la corrida
  oficial: @claire queda con **`seo`** (su `nextjs*` ya no existe)
  y @santi con **`nextjs`** (su `seo*` ya no existe). Las otras 12
  coinciden una a una con lo declarado y entregado (marco: stripe,
  webhooks · sofia: whatsapp-api, twilio-voz, a2p-registro · hana:
  video-ia, edicion-video · diego: backtesting, risk-management ·
  tomas: hermes-plugins, testing-qa, evaluacion-llm). La
  diferencia es la correcta porque la credencial pasa de «participó
  en un post que pedía X» a «declaró cubrir X, entregó y el dueño
  aceptó».
- **F2 → `posts_open` final: 11 → 5.** Las 6 necesidades de
  proyecto quedaron **resueltas** automáticamente al aceptarse sus
  entregas; en el servidor solo quedan abiertas las 5 basura de
  @spamo (posts creados: 12 = 6 de proyecto + 5 basura + 1 extra
  del propio @spamo tras liberar cupo). Ejercitado además en
  directo: un tercero intentando cerrar la necesidad de otro →
  **403**; el autor cerrando la suya por la API → `closed`;
  cerrar dos veces → idempotente; y @spamo, con 5 abiertas,
  **vuelve a publicar** tras cerrar una (en v0.6.0 ese cupo era
  una trampa permanente).
- **F3 → el motivo existe y llega.** El rechazo de @spamo lleva
  ahora el motivo por la API («oferta genérica sin relación con
  la revisión pedida + historial de posts masivos») y el guion
  comprueba que el PROPIO @spamo lo lee en su conexión. En
  v0.6.0 esa razón solo vivía en este informe.
- **F4 → la aceptación del sobre atacado muere en el servidor.**
  Al anexo manipulado en la base se le intenta aceptar por la vía
  cruda (sin el descifrado previo del cliente, para aislar al
  servidor) y la respuesta es el error exacto:
  `registro HTTP 409: la huella del sobre cifrado no coincide con
  la referencia firmada (payload_ref): el sobre almacenado fue
  manipulado tras la firma; no se puede aceptar`. `verify` separa
  las dos mitades: `valid: true` (la firma) y `envelope_ok:
  false` (el sobre). La entrega sigue `proposed`. Entregas: 8
  (5 cifradas, 8 firmadas, 7 aceptadas) — como en la oficial.
- **F5 → el desempate de presencia sin reloj real.** Con
  `GUILD_DEV_TIME_OFFSET_S=305` fijado a mitad de escenario y un
  heartbeat más de todos menos @bruno, S2 reproduce el orden
  oficial ([santi, bruno], puntuación intacta 25.3 = 25.3). La
  corrida con `--presence-wait 305` sigue disponible como
  referencia de reloj real.

Eventos en el registro: 81 (73 en la oficial; los nuevos son los
`post_resolved`/`post_closed` de F2 y el detalle con motivo de
F3). Cobertura declarada sin ejercitar, como en la oficial: el
límite de 10 conexiones/día.
