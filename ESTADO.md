# GUILD — Estado (06/11/2026, v0.6.1)

## Qué es esta versión

El paquete «Fricciones»: cerrar las **cinco fricciones de diseño**
que dejó el enjambre de prueba de v0.6.0 (`docs/swarm-test.md`) —
ningún bug de protocolo, cinco bordes ásperos con evidencia.
Protocolo **v1.6**. **Nada publicado** — sigue la regla: repo, PR
y posts solo con el OK final de Lee, paso a paso. Timing ya
decidido: lanzamiento tranquilo tras el 11/11 (plan en
`launch/PLAN_LANZAMIENTO.md`), Hermes primero → Muse → API
abierta. El paquete anterior (v0.6.0, «Blindaje», protocolo v1.5)
cerró las dos superficies que quedaban en confianza ciega: el
**contenido** de las entregas viaja **cifrado extremo a extremo**
(el registro guarda ciphertext que no puede leer), la **clave con
la que el registro firma** la reputación **ya no vive dentro de su
base**, y **`/guild deliver` firma de verdad** con la clave local
del usuario.

## Implementado y probado ✅ (v0.6.1, protocolo v1.6)

Todo lo de v0.6.0 (entregas cifradas E2E GUILD-E2E-1, clave del
registro fuera de la base, firma desde comandos, prueba en Hermes
real y en release oficial, eventos SSE en vivo, perfil público
web, inbox, presencia, contratos con `on_time`, transporte
relay/peer, tipos de necesidad, reputación portable, matching v2,
anti-spam, dashboard) sigue dentro y en verde. Lo nuevo — las
cinco fricciones del enjambre, cerradas una a una:

- **F1 · Habilidades verificadas precisas**: la entrega declara
  `skills_covered` (subconjunto validado de las habilidades del
  post; sin post asociado no hay declaración posible) y al
  aceptarse se verifica SOLO lo declarado; la declaración entra
  en la forma canónica firmada cuando existe (sin declaración, la
  forma es byte a byte la de v1.5). Sin declaración, la
  derivación acredita únicamente requerido ∩ ofrecido del autor:
  jamás una habilidad que ni ofrece. Defensa del defecto: la
  intersección no castiga a los clientes anteriores al campo (su
  silencio no puede leerse como «no cubrí nada» sin romper
  integraciones honestas) y ya elimina exactamente la
  sobre-atribución cazada — nadie verifica lo que no ofrece ni
  entregó. La declaración es el instrumento preciso; el defecto,
  el suelo conservador.
- **F2 · Cierre de posts por API**: `POST /v1/posts/:id/close`
  (+ `GuildClient.close_post`, `/guild close`) — solo el autor
  (403 a terceros), idempotente, `{"resolved": true}` para cerrar
  como resuelta. Aceptar una entrega RESUELVE automáticamente el
  post de su conexión. Cerrados/resueltos: fuera del tablón y
  fuera del cupo anti-spam de abiertas.
- **F3 · Motivo en el rechazo de conexión**: `reason` opcional
  (≤280) guardado como `rejection_reason`, legible por el
  solicitante en la conexión y en su evento `connection_decided`
  (y en `/guild watch`); `/guild reject <id> motivo…` lo acepta.
  Sin motivo, comportamiento idéntico a v0.6.0.
- **F4 · Aceptar exige sobre íntegro**: al aceptar una entrega
  cifrada, el servidor compara el sha256 del ciphertext
  almacenado con el `payload_ref` firmado; si no coincide → 409
  y NO se acepta (firmada o no). `verify_delivery` distingue
  `valid` de `envelope_ok`. El cliente del dueño descifra en
  local antes de aceptar cuando tiene la clave (defensa en
  profundidad; la exigencia ya no depende de ello).
- **F5 · Reloj de presencia inyectable (SOLO dev/pruebas)**: el
  registro acepta el desplazamiento `GUILD_DEV_TIME_OFFSET_S`
  en su reloj interno, leído en cada uso. Infraestructura de
  test — el enjambre corre en segundos con el mismo resultado
  que los 305 s reales — documentada como prohibida en
  producción (desplaza todas las marcas). Umbrales y pesos
  intactos.

Lo de v0.6.0, en detalle:

- **Entregas cifradas extremo a extremo** (`guild/e2e.py` +
  X25519 en `guild/identity.py`): cada perfil genera un par
  X25519 de cifrado al unirse (pública en el perfil como
  `enc_public_key`; la privada viaja una sola vez al cliente y
  nunca sale de él). `GuildClient.deliver(..., payload=…)` cifra
  en el cliente del autor con la construcción **GUILD-E2E-1**:
  par efímero por entrega, secreto X25519 con la pública del
  dueño, **HKDF-SHA256** (salt = nonce, info `guild-e2e-1`) →
  clave de flujo + clave de MAC, **HMAC-CTR** (bloque *i* =
  `HMAC-SHA256(clave, nonce ‖ i)`) y **Encrypt-then-MAC** sobre
  dominio ‖ efímera ‖ nonce ‖ contexto (conexión+autor) ‖
  ciphertext, verificado antes de descifrar. El registro guarda
  solo `enc_ciphertext`, `enc_nonce`, `enc_eph_public_key`,
  `enc_mac`; el `payload_ref` firmado pasa a ser
  `e2e:<sha256 del ciphertext>`, así que la firma Ed25519 cubre
  el sobre exacto. **Título y resumen siguen en claro por
  decisión declarada** (son los metadatos que el dueño lee para
  decidir). Nueva ruta `GET /v1/deliveries/:id` (solo las dos
  partes de la conexión) y `GuildClient.decrypt_delivery()` para
  abrir el sobre en local antes de decidir. Un perfil sin
  `enc_public_key` (anterior a v1.5) no puede recibir contenido
  cifrado: error claro, nunca degradación silenciosa a claro.
  Sin payload, la entrega es la de siempre (solo metadatos).
- **La clave del registro, fuera de la base**
  (`Registry.registry_keypair` / `rotate_registry_key`): orden
  de resolución — `GUILD_REGISTRY_PRIVATE_KEY` (entorno, no se
  persiste) → fichero (`GUILD_REGISTRY_KEY_FILE` o
  `<db>.registry-key`) creado con **0600 desde el primer byte**
  y con permisos verificados al cargar (un fichero explícito
  más abierto se rechaza con error claro) → si una base antigua
  la guarda en `registry_meta`, **migración automática**: se
  extrae tal cual al fichero, se borra de la base y queda el
  evento `registry_key_migrated` (la clave no cambia: los
  exports viejos siguen verificando). **Rotación** explícita
  (`rotate_registry_key()` o `python3 -m guild.server --rotate-key`):
  par nuevo al fichero, la pública nueva se sirve en
  `/v1/stats`, evento `registry_key_rotated`, y declarado en
  PROTOCOL que los exports antiguos solo verifican contra la
  clave antigua. El espejo Supabase ya no contempla tabla para
  esa clave (vive en el fichero del operador).
- **Firmar desde `/guild deliver`** (`commands.py` +
  `guild/paths.keys_path()`): al unirse, el plugin guarda las
  claves privadas del usuario en **`keys.json`, solo en su
  máquina, creado con 0600 desde el primer byte** (`os.open`
  con modo y verificación posterior; si los permisos no se
  pueden asegurar, no se guarda y el join lo avisa). Con ella,
  `deliver` calcula hash de contenido + firma Ed25519 igual que
  la vía API y el registro la verifica. **Sin clave local,
  entrega igual pero con aviso explícito «SIN firmar»** — nunca
  en silencio. Nuevos `/guild keys` (estado + huella de la
  pública) y `/guild keys forget` (borra la clave local). El
  inbox marca las entregas con contenido cifrado con 🔐.
  `state.json` sigue sin guardar secretos: las claves viven en
  su propio fichero, separadas a propósito.
- **Docs y superficies en 0.6.0**: PROTOCOL v1.5 (principio 8,
  secciones «Contenido cifrado extremo a extremo» y «La clave
  de firma del registro», firma desde comandos en «Entregas
  firmadas»), CHANGELOG, READMEs (EN/ES), landings (pie
  v0.6.0), plugin.yaml (descripción con E2E y clave fuera de
  la base) y dashboard en 0.6.0. Espejo Supabase: columnas
  `enc_*` y `enc_public_key` añadidas; sigue sin desplegar.

## Verificación real (ejecutada, no simulada)

- **Tests: 118 passed (v0.6.1)** — `.venv/bin/python -m pytest
  tests/ -q`. Los 97 anteriores siguen verdes con UNA aserción
  actualizada y declarada (el dict exacto de `verify_delivery`
  en `test_signed_delivery_verifies_and_tamper_fails` crece con
  el campo `envelope_ok` de F4; ninguna aserción de F1/F2 hacía
  falta tocar: el defecto de intersección conserva el caso
  legítimo histórico). Los 21 nuevos
  (`tests/test_v061_fricciones.py`) cubren, por fricción: la
  forma exacta del enjambre en F1 (dos colaboradores, un post,
  cada uno verificado solo con lo suyo), la declaración fuera
  del post (422/error), sin post, y DENTRO de la firma
  (ampliarla en la base invalida la verificación); en F2, cupo
  liberado, tercero bloqueado (403 también por HTTP), cierre
  idempotente, resolución automática al aceptar y el comando
  `/guild close`; en F3, el motivo llegando al solicitante por
  la conexión, por su evento y por HTTP, el límite de 280 y el
  rechazo sin motivo intacto; en F4, la aceptación bloqueada
  del sobre manipulado en local, por el cliente (MAC) y por el
  servidor HTTP con 409 aislado del cliente, más el control
  íntegro que acepta; en F5, el experimento de gemelos con el
  reloj desplazado en milisegundos (mismo orden, misma
  puntuación) y el reloj real intacto sin la variable.
- **Enjambre re-corrido en modo rápido (v0.6.1): exit 0, 0
  fallos de invariante, 0 observaciones** —
  `.venv/bin/python scripts/swarm_test.py --presence-offset 305`.
  Tops de matching S1 IDÉNTICOS a la corrida oficial de v0.6.0
  (83.0 · 73.3 · 82.7 · 84.0 · 53.0 · 77.3, con los mismos
  desgloses), gemelos S2 con el mismo orden que los 305 s
  reales ([santi, bruno], 25.3 = 25.3) y S3 igual (34.7 por
  reputación). Las fricciones, ejercitadas en la corrida: F1 →
  14 habilidades verificadas (las 16 de v0.6.0 menos las 2
  sobre-atribuidas); F2 → `posts_open=5` al cierre (antes 11),
  cierre por API con 403 a terceros e idempotencia, y cupo
  liberado en directo; F3 → el motivo del rechazo leído por el
  propio solicitante vía API; F4 → el intento de aceptar el
  sobre manipulado muere en el servidor con el 409 exacto
  («la huella del sobre cifrado no coincide…») y la entrega
  sigue `proposed`; F5 → todo ello sin esperar 305 s. Escaneo
  de secretos: 0 fugas, como en la corrida oficial. Addendum
  completo en `docs/swarm-test.md`.
- **Plugin re-ejercitado en la release oficial v0.23.0
  (v0.6.1): 13/13, exit 0** — los comandos cambiaron
  (reject/close/deliver), así que `scripts/demo_hermes_real.py`
  se re-corrió entero contra `~/workspace/hermes-release-check`
  (sin modificarlo): el cargador real cargó el plugin ya en
  **0.6.1**, Marco se unió, entregó y su `baseten` quedó
  verificada (con la regla F1: el post la pedía y Marco la
  ofrece), reputación 4.67/5 y las cifras de la demo intactas.
  Demos local y de red también en verde (exit 0); en la de red
  el post aceptado ya se resuelve solo (`posts_open: 0`).
- **Tests en v0.6.0: 97 passed** — los 80 anteriores seguían
  verdes sin tocar sus aserciones; los 17 de v0.6.0
  (`tests/test_v06_blindaje.py`) son **tests de ataque**, no de
  trámite:
  - *Primitivas*: X25519 contra el **vector de Alice de RFC
    7748 §6.1** byte a byte; simetría DH con claves generadas
    (un tercero deriva otro secreto); HKDF por propiedades
    (determinismo, longitud, sensibilidad a salt/info/IKM);
    el AAD liga el sobre a su contexto.
  - *E2E (a–e)*: roundtrip local y **roundtrip HTTP completo**
    autor→dueño; el texto en claro **no aparece en los bytes
    de la SQLite ni en ninguna respuesta del servidor**
    (escaneo literal); **un byte tocado** del ciphertext o del
    MAC en la propia base → descifrado rechazado por MAC; un
    **tercero** (y el propio autor) no descifran; un tercero ni
    siquiera puede leer la entrega por la API (403); dueño sin
    clave publicada → error claro; y las entregas de **solo
    metadatos** (flujo v0.5) siguen funcionando y aceptándose.
  - *Clave del registro*: la privada **no está en la base**
    tras operar (ni en los bytes ni en `registry_meta`), el
    fichero nace 0600, la **migración** desde una base heredada
    conserva la clave (el export verifica fuerte tras migrar)
    y deja evento, un fichero explícito con 0644 se **rechaza**
    y la **rotación** separa pasado y futuro (export viejo
    verifica contra la antigua y no contra la nueva).
  - *Comandos*: el join crea `keys.json` en **0600** con ambas
    claves; la entrega de `/guild deliver` queda **firmada y
    verificable** por el registro; tras `/guild keys forget`,
    el comando entrega con el aviso **«SIN firmar»** y la
    entrega queda sin firma en el registro.
- **Demo en Hermes real re-ejecutada: 13/13, exit 0**
  (`scripts/demo_hermes_real.py`). Los comandos cambiaron en
  esta versión, así que no valía fiarse de la corrida de v0.5:
  el cargador real del checkout de La Asistenta cargó el plugin
  ya en **0.6.0** sin errores, ejercitó `/guild` de punta a
  punta (join, matches, contrato, entrega, valoraciones, inbox,
  hook) y los perfiles ya exponen `enc_public_key`. Informe de
  la prueba original en `docs/hermes-real-test.md`; el checkout
  **no se modificó**.
- **Prueba en RELEASE OFICIAL de Hermes: 13/13, exit 0
  (06/11/2026)** (`scripts/demo_hermes_real.py` con
  `GUILD_HERMES_CHECKOUT` apuntando a un clon nuevo; sin
  copiar ni parchear el script): el cargador real de la
  release **v0.23.0** de `NousResearch/hermes-agent`
  (publicada el 05/11/2026, commit
  `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`; clon en
  `~/workspace/hermes-release-check`, árbol limpio antes y
  después) cargó el plugin ya en **0.6.0** sin errores y lo
  ejercitó de punta a punta con las cifras de siempre —
  Marco **78.0/100** sobre el post de Lee, Lee candidato con
  **88.7/100**, reputación de Marco **4.67/5**, skill
  `baseten` verificada y entrega firmada Ed25519 desde
  `/guild deliver`. Esta vez la puerta `requires_hermes
  >=0.21.5` se evaluó contra una versión **real**: la release
  reporta `base_version='0.23.0'` (el checkout de desarrollo
  reportaba `'unknown'`). `hermes_cli/plugins.py` es byte a
  byte idéntico entre el checkout dev y la release;
  `plugins_manifest.py` solo añade el campo opcional
  `config_keys` (aditivo, sin adaptación necesaria). **Sin
  tocar código del plugin**; suite de control re-corrida:
  **97/97**. El checkout de La Asistenta no se modificó.
  Informe completo en `docs/hermes-release-test.md`. **El
  límite «sin probar en una release oficial v0.21+» queda
  CERRADO.**
- **Demo E2E local: completa** (exit 0) y **demo de red:
  completa** (exit 0), sin tocar el escenario: mismas cifras
  salidas del código — Marco nº1 con **88.0/100** [skills 50 ·
  idioma 12 · reputación 8 · zona 8 · reciprocidad 10], Ana
  27.3, reputación de Marco **4.67/5** (útil 5 · claro 5 ·
  a tiempo 4). Las stats ya muestran `registry_public_key`
  servida desde el fichero de clave, no desde la base.

## Límites que quedan (honestos, sin maquillar)

- **GUILD-E2E-1 no tiene auditoría externa**: es una
  construcción con primitivas estándar (X25519 y HKDF son RFC;
  HMAC es FIPS 198) implementada en Python puro con stdlib
  para no añadir dependencias. No es ChaCha20-Poly1305 ni AES
  de una librería auditada como libsodium, y no se presenta
  como tal: se presenta con su nombre, su construcción
  documentada y sus tests de ataque.
- **Validación de vectores, con matiz declarado**: X25519 se
  validó byte a byte contra el vector de clave de Alice de RFC
  7748 §6.1. El secreto compartido de ese mismo ejemplo y el
  vector oficial de HKDF (RFC 5869) **no se reprodujeron con
  certeza** al implementar (las constantes recordadas no
  casaron), así que **no** se fingen como vectores: la simetría
  DH y HKDF se validan por roundtrip y propiedades. Es un
  límite de validación conocido, no oculto.
- **Sin secreto perfecto hacia adelante frente al receptor**:
  la privada de cifrado del dueño es de larga duración; si se
  filtra algún día, los sobres históricos guardados en el
  registro serían descifrables con ella. El par efímero del
  autor da claves distintas por entrega, no inmunidad ante ese
  compromiso. Rotar la clave de cifrado de un perfil exigiría
  republicar el perfil (no hay rotación de claves de perfil en
  el protocolo todavía).
- **Los metadatos se ven**: título, resumen, quién entrega a
  quién, cuándo y si la entrega va cifrada son visibles para
  el registro por diseño (son el suelo operativo: decidir,
  matching, anti-spam). El cifrado protege el contenido, no la
  existencia de la colaboración.
- **`/guild deliver` no cifra contenido**: desde los comandos
  se entrega y se firma (metadatos), igual que en v0.5 pero
  firmado; el payload cifrado E2E va por la vía del cliente
  (`GuildClient.deliver(..., payload=…)`). Añadir payload a
  los comandos exige decidir cómo teclea un humano contenido
  largo en un comando: decisión de UX pendiente, no un olvido.
- **La clave local vive en claro en la máquina del usuario**:
  `keys.json` se protege con permisos 0600, no con cifrado
  con frase de paso. Quien tenga acceso a la sesión del
  usuario en su máquina tiene su clave — es el mismo modelo
  de amenaza que una clave SSH sin passphrase, y está
  declarado para que el usuario decida (`/guild keys forget`
  la borra).
- **Release oficial: CERRADO el 06/11/2026** — probado y en
  verde (13/13) contra la release oficial **v0.23.0** de
  Hermes Agent (ver «Verificación real» y
  `docs/hermes-release-test.md`). Lo que sigue pendiente ya
  no es la release: el hook dentro de una sesión viva con
  humano, el dashboard en un host con UI real y una
  instalación limpia desde cero de la release con su propio
  instalador.
- **Transporte peer probado solo con doble simulado**: no hay
  un segundo Hermes con Bot Mode en este sandbox. Pendiente
  de prueba con un Hermes v0.21+ real de otro dueño.
- **Registro no desplegado públicamente, pero con kit de
  despliegue listo y validado en local (06/11/2026, Pieza
  B):** `deploy/` contiene Dockerfile (recomendado: python
  slim, usuario sin privilegios, volumen para DB + fichero
  de clave, HEALTHCHECK contra `/v1/stats` — no existe
  `/health`), docker-compose, alternativa systemd, Caddyfile
  (Caddy = TLS elegido por su ACME automático), `backup.sh`
  (DB + clave fechados, 0600, con el aviso de que el backup
  de la clave es un secreto) y `RUNBOOK.md` del Día L (VPS →
  DNS → TLS → despliegue → humo → backup → rollback).
  Validado en local SIN docker (no existe en el sandbox; el
  `docker build` queda pendiente del Día L): servidor real
  arrancado con las variables del kit, `/v1/stats` 200,
  clave creada en 0600, `smoke_test.py` (join ×2 + entrega
  cifrada E2E descifrada por el dueño + firma válida) en
  verde con exit 0, y backup + restauración probados (la
  restauración reproduce la misma `registry_public_key` y
  los perfiles). Hallazgo de la validación: la resolución de
  la clave es perezosa — un fichero laxo no impide arrancar;
  el rechazo salta en el primer uso (`/v1/stats` 400), y el
  RUNBOOK lo declara. El servidor existe y está probado en
  local; desplegarlo sigue siendo el paso del Día L, no está
  hecho. El esquema Supabase sigue siendo una vía alternativa
  escrita, tampoco desplegada.
- **Tiempo real de una sola dirección y sin WebSocket**: el
  stream cubre registro → agente; un canal bidireccional en
  vivo (WebSocket / Inter-Agent Bridge) queda como futuro
  documentado en PROTOCOL.
- **Concurrencia del servidor**: las peticiones comparten una
  conexión SQLite (escrituras serializadas; el stream usa
  conexión propia por escucha). Suficiente para una comunidad,
  no es un servidor de alto tráfico.
- **La heurística anti-ruido es simple a propósito**: puede
  avisar de más. Por eso es aviso y nunca bloqueo; afinarla
  exige uso real, no imaginación.
- **Vídeo de lanzamiento**: NO necesita re-render tras v0.6 —
  el 88/100 que muestra la v3 sigue saliendo idéntico del
  código en las demos clásicas. Si un cambio futuro moviese
  el 88, habría que re-renderizar antes de publicar.
- **Si Nous extiende Bot Mode/`peer` entre dueños** con
  directorio y reputación, parte de GUILD quedaría absorbida:
  el riesgo está analizado en CONCEPTO.md con los fosos que
  sobrevivirían.
- **Nombre: GUILD, DEFINITIVO** — decidido por Lee el
  06/11/2026 («Quedarse con GUILD») con la lista corta
  comprobada sobre la mesa (`launch/NOMBRES.md`: 8
  candidatos, dominios vía RDAP autoritativo, colisiones
  vía búsqueda web). Lee eligió GUILD conociendo sus
  colisiones (Guild.ai y el «Guild» de NanoCorp, red de
  agentes casi idéntica) y que el único dominio libre de
  los 16 comprobados era forgekin.network. La
  diferenciación se apoya en el posicionamiento y en el
  handle del ecosistema (`hermes-guild`), no en el nombre
  desnudo. No hay renombre pendiente.

## Decisión de timing (Lee, 06/11/2026 ~15:04)

- **Lanzamiento tranquilo tras el 11/11**: GUILD NO es tercera
  entrada del hackathon de Nous. Plan fechado en
  `launch/PLAN_LANZAMIENTO.md` (Fase 0 silenciosa 12–15/11, Día L
  en la semana del 17/11 a elegir por Lee, olas Hermes → Muse →
  API abierta).
- Kit de despliegue del registro preparado el 06/11/2026
  (`deploy/`, Pieza B): el Día L es ejecutar el RUNBOOK, no
  diseñarlo.
- Registro día 1: **LOCAL-FIRST, central en v1.1** —
  decidido por Lee el 07/11/2026. Consecuencia: el copy
  de lanzamiento (post de X, README, landing) debe ser
  coherente con ello y no prometer red central; pasada
  de coherencia asignada a la Fase 0.
- **Pasada de coherencia local-first: HECHA el
  07/11/2026.** Ningún texto público promete ya un
  registro central alojado existente; el mensaje es
  «corre tu propio nodo (un comando, SQLite), conéctate
  al registro de otro builder o a uno compartido, el
  alojado oficial llega en v1.1, tu reputación es un
  export firmado que te llevas». Ficheros tocados:
  `launch/post_x.md`, `launch/cold_start.md`,
  `launch/video_script.md`, `README.md`, `README.es.md`,
  `landing/index.html`, `landing/index.es.html`,
  `skill.md`, `skill.es.md` y `clients/muse/SKILL.md`.
  El vídeo v4 (`guild-video/script_v4_en.md`) se verificó
  sin tocar: su copy ya era neutro, no promete servidor
  central.
- **DÍA L FIJADO: miércoles 18/11/2026, ~16:30 Madrid**
  (decidido por Lee el 07/11/2026). Pendiente de Lee:
  solo los OK finales paso a paso el propio Día L.
  (Nombre, registro y día, decididos el 06–07/11/2026.)

## LANZAMIENTO ADELANTADO — ejecución del 07/11/2026

**Lee ordenó el 07/11/2026 «Lanzamiento completo de GUILD ahora»** — la
orden sustituye al Día L del 18/11. Ejecución del mismo día, estado exacto
paso a paso (verdad operacional: HECHO solo lo que tiene URL verificada):

1. **Pre-vuelo: HECHO.** Copy desfasado corregido (`launch/post_x.md`:
   cifras v0.1.0/16 tests → v0.6.1, protocolo v1.6, 118 tests, swarm y
   release oficial v0.23.0; `landing/index.es.html`: pesos antiguos
   ~60/15/25 → canónicos 50/12/20/8/10). Escaneo de secretos sobre el
   árbol completo: limpio (2 únicos hits, ambos fixtures públicos de
   test: el vector oficial RFC 8032 y un placeholder `<redacted>`).
   Árbol de publicación: 67 ficheros, 717 KB, todo UTF-8, sin bases de
   datos, sin `keys.json`, sin checkouts anidados, sin la carpeta del
   vídeo. Suite completa: **118 passed** (puerta del lanzamiento).
2. **Repo público `Blackleets/hermes-guild`: HECHO y VERIFICADO.**
   Lee creó el repo vacío y público y lo añadió a la instalación de la
   App «Meta Muse AI» («Selected 5 repositories»). Push ejecutado el
   07/11/2026 por snapshot (manifiesto de 67 ficheros, 723.510 bytes,
   todo UTF-8) a la rama `main`: commit de la release
   **`bb5e3fd0bb6328b3652d648ba7162500255218fb`** (sobre el commit
   inicial de inicialización del proveedor, `fd93ca8c…`). Verificado:
   https://github.com/Blackleets/hermes-guild carga público, rama por
   defecto `main`, README renderizado, raíz con los 67 ficheros.
   **Release `v0.6.1` y topics: PENDIENTES de web** — el conector no
   expone herramientas de releases ni de topics (solo lectura de
   releases); quedan como clicks en la web del repo (release con notas
   del CHANGELOG; al crearla, el pin del catálogo sigue siendo el
   commit `bb5e3fd0…`).
3. **PR al catálogo: RAMA LISTA, apertura BLOQUEADA vía conector.**
   Paquete completado con el SHA real (`bb5e3fd0…` sustituye al
   marcador `PENDING_V061_RELEASE_COMMIT_SHA` en `hermes-guild.yaml`).
   Rama creada en el fork `Blackleets/hermes-agent-upstream`:
   `add-hermes-guild-plugin` (head
   `aecda1e962582dd05ce8a7492e22d29741ec8df4`), con diff verificado de
   exactamente 1 fichero: `plugin-catalog/hermes-guild.yaml`. Pero
   `create_pull_request` contra `NousResearch/hermes-agent` devolvió
   `403 Resource not accessible by integration`: el token de la App no
   puede abrir PRs en el repo upstream (la App no está instalada allí);
   Gazette/SpendGuard se abrieron por otra vía. **Paso restante (web,
   1 click):** abrir el PR desde la URL de compare
   https://github.com/NousResearch/hermes-agent/compare/main...Blackleets:hermes-agent-upstream:add-hermes-guild-plugin?expand=1
   con el título y el cuerpo de
   `~/workspace/guild-plugin-catalog-pr/PR_DESCRIPTION.md`.
4. **Post de X: FINAL, sin publicar** (lo publica Lee en persona).
   `launch/post_x.md` con cifras de hoy, modelo local-first y el enlace
   `https://github.com/Blackleets/hermes-guild` + comando de instalación.
   Su precondición ya se cumple: la URL del repo carga verificada
   (07/11/2026).
5. **Landing en vivo: PREPARADA vía Actions, pendiente de 2 pasos
   web** (el repo ya existe). Pages desde rama solo ofrece `/` o
   `/docs` y la landing vive en `landing/`, así que se despliega con
   GitHub Actions: workflow `Deploy landing to Pages`
   (`.github/workflows/pages.yml`) creado y verificado EN LOCAL el
   07/11/2026 — push a `main` con `paths: landing/**` + el propio
   workflow, `workflow_dispatch`, permisos `pages: write` +
   `id-token: write` + `contents: read`, job único con
   checkout@v4 → upload-pages-artifact@v3 (`path: landing`) →
   deploy-pages@v4. **El push del workflow por el conector quedó
   BLOQUEADO**: `403 Resource not accessible by integration` al
   crear el árbol — la GitHub App de Muse no tiene el permiso
   «Workflows» que GitHub exige para crear ficheros bajo
   `.github/workflows/` (los pushes anteriores, sin ficheros de
   workflow, sí pasaron). Verificado tras el fallo: `main` sigue en
   el pin `d727689…` y el registro de sync no avanzó. Pasos web
   restantes: (a) subir `.github/workflows/pages.yml` (contenido en
   local, listo para pegar) vía la web del repo o conceder el
   permiso Workflows a la App; (b) Settings → Pages → fuente
   «GitHub Actions», y verificar la URL publicada
   (https://blackleets.github.io/hermes-guild/). El README no
   enlaza aún ninguna URL de Pages (nada de enlazar a un 404).
6. **Vídeo de lanzamiento:** la v5 quedó DESCARTADA por Lee tras verla
   («no me gusta»); se está rehaciendo con Flow. El post no depende de
   ello para existir, pero el Día L público completo sí quiere su vídeo:
   decisión de Lee si el post sale con la v4 (77,5 s, lista y verificada)
   o espera a la nueva de Flow.

**Resumen (actualizado tras el push):** repo público EN VIVO y
verificado con el commit de la release v0.6.1
(`bb5e3fd0bb6328b3652d648ba7162500255218fb`). Lo que queda es solo vía
web, porque el conector no lo expone o no tiene permiso upstream:
(1) abrir el PR al catálogo desde la URL de compare (la rama del fork
ya lleva el fichero exacto con el pin), (2) crear la release `v0.6.1`
y los topics en la web del repo, (3) activar GitHub Pages
(`landing/`). El post de X lo publica Lee cuando quiera: su URL ya
carga.

**Corrección de copy post-publicación (07/11/2026, tarde):** el
README publicado arrastraba tres restos previos al lanzamiento,
corregidos en `README.md` y `README.es.md`: (a) quitado el
comentario «# (once published)» / «# (cuando se publique)» del
`git clone`; (b) la frase de Status «Not yet published: public
repo, catalogue PR and launch…» / «Aún no publicado: el repo
público, el PR al catálogo y el lanzamiento…» reescrita a la
verdad del momento (repo público ya; PR al catálogo en curso hoy;
modelo local-first, sin prometer red central); (c) «Protocol
v1.4» / «Protocolo v1.4» en «What's in the box» → **v1.6**.
Barrido extra sin más hits. Re-push por snapshot (solo los dos
README) → **nueva cabeza de `main`:
`d7276891e514076a6ee68abe352bc7c3027e0fc6`**, verificada contra la
API (README remoto ya sin «Not yet published»). **Re-pin del
catálogo HECHO:** `hermes-guild.yaml` actualizado a ese SHA tanto
en el paquete local (`~/workspace/guild-plugin-catalog-pr/`) como
en la rama `add-hermes-guild-plugin` del fork (commit
`1e8a24f285b20d061a98c3dd2ed594794ef297f0`); la vista compare de
la rama contra `main` sigue mostrando exactamente **1 fichero**
cambiado (3 commits, todos sobre la entrada del catálogo). Nota:
esta anotación de ESTADO.md es local; el ESTADO.md remoto queda
en el commit `d727689…` hasta la próxima sync por snapshot.

**Paquete «REPO ESTRELLA» (07/11/2026, después del lanzamiento):**
el repo queda a nivel escaparate. Subido por snapshot (9 ficheros)
→ **cabeza de `main`: `91549fbfc3f5a53c8ffd2c3381814cdff37ffc80`**
(commit posterior a la release: el tag `v0.6.1` y el pin del
catálogo `d727689…` NO se tocan):

- **Imágenes SVG nativas** en `docs/img/` (el conector solo publica
  texto UTF-8; todo vectorial, identidad de la landing: fondo
  índigo `#07070d`, tarjetas, oro `#e8b34b`, violeta `#7c6cff`):
  `hero.svg` (wordmark + posicionamiento + chips), `how-it-works.svg`
  (5 pasos + banda de reputación), `match-card.svg` (el match REAL
  Lee×Marco **88/100** con sus 5 barras canónicas),
  `security.svg` (flujo E2E + etiqueta honesta «stdlib, not
  externally audited»), `reputation.svg` (Marco **4.67/5**: útil 5 ·
  claro 5 · a tiempo 4, export firmado y portable) y
  `architecture.svg` (clientes / protocolo v1.6 / nodos
  local-first). QA visual hecha renderizándolas a PNG una a una
  (cairosvg): la primera pasada cazó glifos emoji que no
  renderizaban (⚔ ★ 🔒 🔑 ⭐ → sustituidos por iconos vectoriales
  dibujados), una nota cortada en match-card y el título de la
  tarjeta 5 desbordado; todo corregido y re-verificado.
- **README escaparate** (`README.md` + espejo `README.es.md` con
  las mismas imágenes): hero arriba, 6 badges shields.io SOLO con
  hechos verificados (release v0.6.1 · protocol v1.6 · tests 118
  passing · verified on Hermes v0.23.0 · local-first · MIT),
  quick start <1 min (instalar plugin + `python3 -m guild.server`),
  secciones How it works / Architecture / Security / Reputation con
  las imágenes, sección **Evidence** (swarm, release oficial, Hermes
  real, TESTING), mapa de documentación completo, roadmap corto
  (v1.1 hosted registry · ola Muse · ola API abierta) y el estado
  actualizado enlazando la release y el **PR #150708**.
- **`TESTING.md`** nuevo: cómo correr la suite (**118 passed en
  12.80 s**, corrida real del 07/11/2026, Python 3.12), qué cubre
  cada fichero de test (66+17+21+6+4+4) y las demos con sus comandos
  e informes.
- **Verificación del push:** README remoto servido con las imágenes
  (hero.svg y match-card.svg comprobados desde
  raw.githubusercontent) y pase de enlaces internos del README sin
  ningún enlace roto.

**Pendiente SOLO vía web** (el conector no puede: 403 en
`.github/workflows/` y la imagen social es binaria):

- `.github/workflows/ci.yml` — LISTA EN LOCAL (pytest en push/PR,
  Python 3.12, venv como en local: solo pytest, el resto es
  stdlib). Subirla por la web del repo (Add file → Create new file)
  o conceder el permiso «Workflows» a la GitHub App.
  (La de Pages, `pages.yml`, sí entró por web: commit
  `2eccf735…`.)
- **Imagen social**: `~/workspace/guild-video/og-image.png`
  (1280×640, PIL, misma identidad: wordmark + posicionamiento +
  chips) generada y verificada EN LOCAL — subirla en
  Settings → General → Social preview.
