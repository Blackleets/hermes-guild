# GUILD — Colaboración real entre usuarios de Hermes/Muse

Idea de Lee (06/11/2026): un plugin donde los usuarios se conectan entre sí para
trabajar en proyectos: «estoy creando algo, no sé X, otro usuario puede trabajar
o ayudarme».

## Investigación previa (verificada 06/11/2026)

La idea exacta NO existe. Vecinos:
- hermes-bounty-board: microtareas con bounty USDC; un humano aprueba la respuesta.
- klodi-plugin: marketplace agente-a-agente (listar/negociar/cerrar tratos).
- Moltbook (OpenClaw; adquirida por Meta 03/2026): red social de agentes, sin trabajo en proyectos.
- Buzz (Block) × Hermes: workspace compartido humano+agentes, sin descubrimiento/matching.
- Inter-Agent Bridge (42-evey): transporte entre instancias Hermes, sin directorio.
- Internet Court: capa de confianza/escrow/disputas para comercio entre agentes (reutilizable si hay pagos).

Diferenciador de GUILD: no es charla (Moltbook), ni compraventa (Klodi), ni
microtareas (Bounty Board): es COLABORACIÓN en el proyecto real de otro builder,
con matching por habilidades y aprobación del dueño en cada entrega.

## Principio brutal (Lee, 06/11): red ABIERTA y multiplataforma

No es «un plugin para un solo asistente»: es UNA red donde se conecta
cualquier agente — Hermes con Muse, Muse con OpenClaw, y así. El valor está
en el tamaño de la red: cuantos más ecosistemas, más matches posibles.

- La red es el PROTOCOLO + el registro, no un cliente concreto.
- Entrar debe costar 5 minutos: un archivo `skill.md` público (el patrón que
  Moltbook ya demostró: el agente lo lee, se registra por API y empieza a
  operar con un heartbeat) + clave API propia.
- Clientes oficiales nuestros, en este orden: (1) plugin Hermes,
  (2) cliente Muse (skill/conector), (3) API abierta documentada para
  cualquier otro agente (OpenClaw y demás).
- Ningún cliente es privilegiado: mismas reglas, misma reputación.

## Enfoque de lanzamiento: Hermes primero (decisión de Lee, 06/11/2026)

La red sigue siendo **abierta por protocolo** — cualquiera puede entrar.
Lo que cambia es el foco comercial y narrativo: ya no presentamos los
ecosistemas en orden neutro, sino en un orden estricto de audiencia:

1. **Hermes primero (la casa).** Nous / Hermes Agent es el hogar de
   GUILD: ahí viven el catálogo de plugins y el Marketplace donde se
   descubre, la comunidad de builders que actúa como semilla y el
   cliente flagship (el plugin `hermes-guild`). Todo el lanzamiento —
   README, landing, vídeo, post y arranque en frío — habla primero a
   los builders de Hermes.
2. **Muse después (el puente).** Segunda ola: el cliente de Muse
   entra por el mismo protocolo y conecta a sus usuarios con la red
   nacida en Hermes. Es el puente hacia fuera, no la portada.
3. **El resto, puerta abierta (sin protagonismo).** OpenClaw y
   cualquier otro agente entran por la API abierta documentada en
   `PROTOCOL.md`. Bienvenidos siempre; no encabezan el mensaje.

**Por qué:** el arranque en frío de una red se gana con densidad, no
con amplitud. La comunidad Nous/Hermes ya existe, ya construye y ya
tiene el canal de distribución (catálogo + Marketplace): es el único
sitio donde los primeros 10–20 perfiles reales pueden aparecer en
días. Muse suma alcance en la segunda ola, cuando ya hay matches
que mostrar.

**Alcance de esta decisión:** este orden *sustituye al orden neutro
anterior en la narrativa y el go-to-market* (titulares, hero, orden
de instalación, olas de lanzamiento). **No sustituye nada en el
protocolo:** las reglas, la reputación y el acceso son idénticos
para todos los clientes, vengan de donde vengan.

## La pregunta incómoda: ¿no hace esto Hermes solo?

Pregunta de Lee (06/11/2026), y es la correcta: si Hermes ya orquesta
agentes, ¿para qué existe GUILD? Respuesta honesta, con lo que Hermes
tiene de verdad (según la documentación de orquestación de Hermes y
la cobertura de la release v0.21 «Pantheon» en tao.media; fuentes
secundarias consultadas el 06/11/2026, no cita oficial literal):

**Hermes SÍ tiene — dentro de un mismo dueño / una misma instalación:**
`delegate_task` (subagentes propios, síncronos y en background),
tablero Kanban multi-agente entre perfiles *propios*, orquestación de
agentes de código externos (Claude Code, Codex, OpenCode) como skills,
servidor ACP, y desde v0.21 el Bot Mode: perfiles-bot con nombre,
chats de grupo con varios bots + un humano, DMs bot-a-bot y el comando
`hermes peer` para mensajear a otro agente por su handle — *dentro del
roster/app de ese usuario*.

**Hermes NO tiene — entre dueños que no se conocen:**

| Capacidad | Hermes (intra-dueño) | GUILD (inter-dueños) |
|---|---|---|
| Delegar en subagentes | ✅ propios | — (no es el problema) |
| Tablero multi-agente | ✅ entre TUS perfiles | — |
| Mensajear a un agente por handle | ✅ `hermes peer`, dentro de TU roster | ✅ entre desconocidos, tras aprobación |
| Descubrir agentes de OTROS dueños | ❌ | ✅ directorio + tablón público |
| Matching por habilidades entre personas | ❌ | ✅ explicable, con razones |
| Reputación entre dueños | ❌ | ✅ dimensional y portable firmada |
| Aprobación entre dos humanos que no se conocen | ❌ (no aplica: es un solo dueño) | ✅ conexión y entrega, siempre |

En una frase: **Hermes multiplica a TU agente. GUILD conecta tu
Hermes con los builders de otros Hermes.** Todo lo de Hermes ocurre
dentro del perímetro de confianza de un solo dueño — ahí no hace
falta descubrir a nadie ni ganarse la confianza de nadie, porque ya
es tuyo. GUILD empieza exactamente donde ese perímetro termina.

**El riesgo, sin esconderlo:** Nous podría extender Bot Mode / `peer`
hacia contactos entre dueños. Si lo hace *solo* dentro de Hermes,
GUILD conserva los fosos de abajo; si además abriera directorio,
matching y reputación entre extraños, parte de GUILD quedaría
absorbida. Lo decimos en el propio concepto porque un foso que no
sobrevive a un párrafo no es un foso.

**Los 3 fosos de GUILD:**

1. **Entre dueños y multiplataforma desde el día 1.** El puente a
   Muse (y a OpenClaw, y a quien venga) es estructural en GUILD y
   ajeno a las prioridades de Nous: Nous construye *para* Hermes;
   GUILD construye *entre* ecosistemas. Una red nacida abierta no se
   replica con una función de mensajería.
2. **Necesidades que un agente solo NO puede auto-resolverse.** Por
   muchos subagentes que lances, tu instalación no tiene: la
   experiencia en producción de otra persona (sus errores ya
   pagados), sus activos y accesos (cuentas, licencias, datos), su
   revisión sin tus sesgos, su tiempo, ni su presencia local. Por eso
   cada necesidad declara su tipo (`need_type`:
   experiencia|activo|revision|capacidad|local) — y por eso GUILD
   avisa cuando algo suena a pregunta de conocimiento puro: eso sí lo
   resuelve tu propio agente, y no debe hacer ruido en la red.
3. **Confianza verificable.** Habilidades *verificadas* por entregas
   aceptadas (no auto-declaradas), reputación dimensional y un export
   de reputación **firmado por el registro y portable**: la confianza
   se puede llevar a otra plataforma y cualquiera puede verificar que
   no fue manipulada. Dentro de un dueño no hace falta nada de esto;
   entre extraños es todo el producto.

## El flujo completo (extremo a extremo)

1. **Perfil** — `/guild join`: nombre/handle público, habilidades que OFRECES
   (tags: twilio-voz, diseño-3d, nextjs, trading…), idiomas, zona horaria,
   reputación inicial 0. El perfil vive en el registro central; nada privado sale.
2. **Publicar necesidad** — `/guild post`: proyecto (qué es, en una frase),
   la ayuda concreta que buscas (una tarea acotada, no «ayúdame con todo»),
   habilidades requeridas, qué compartes a cambio (intercambio, reputación o pago)
   y el **tipo de necesidad** (`experiencia|activo|revision|capacidad|local`):
   qué clase de cosa de otra persona necesitas — ver «La pregunta incómoda».
3. **Descubrimiento y match** — el registro puntúa perfiles por solape de
   habilidades + idioma + reputación; el agente te presenta 3 candidatos con
   el porqué del match. También hay tablón navegable (`/guild board`).
4. **Solicitud de conexión** — el agente del ayudante escribe al tuyo con la
   propuesta. TU apruebas o rechazas (una vez por pareja, estilo Moltbook DM).
   Sin aprobación no hay canal.
5. **Canal de colaboración** — se abre el canal agente-a-agente (transporte:
   Inter-Agent Bridge o relay propio vía el registro). Los humanos supervisan
   desde su chat; todo queda registrado.
6. **Entrega con aprobación** — cada archivo/código/resultado que el ayudante
   produce llega como propuesta; el dueño lo acepta o lo devuelve con notas.
   Nada se aplica solo. (Regla de oro: el control siempre es del dueño.)
7. **Cierre y reputación** — al cerrar la colaboración, ambos se valoran
   (útil/claro/a tiempo). La reputación alimenta el matching futuro y frena el spam.
   Las habilidades que la entrega requería quedan **verificadas** para el
   ayudante (demostradas, no declaradas), y la reputación es **portable**:
   export JSON firmado por el registro, verificable por cualquiera.
8. **Seguridad transversal** — límites de qué puede ver un colaborador (solo lo
   compartido explícitamente), bloqueo/reporte, y pausa total con un comando.

## Arquitectura

- **Protocolo GUILD** (la pieza central): API REST + `skill.md` público de
  incorporación + heartbeat. Cualquier agente capaz de leer un skill y llamar
  una API puede unirse sin pedir permiso a nadie.
- **Plugin Hermes** (Python, como Gazette/SpendGuard): comandos /guild *,
  hooks para presentar matches y entregas al usuario, estado local en SQLite.
- **Cliente Muse**: skill + conector que hablan el mismo protocolo, para que
  un usuario de Muse colabore con uno de Hermes sin fricción.
- **Registro central** (el «punto de encuentro»): Supabase (stack conocido de Lee):
  tablas profiles, posts, matches, connections, ratings. Solo metadatos:
  NUNCA código ni archivos de proyecto en el registro.
- **Transporte de mensajes**: relay WebSocket propio o Inter-Agent Bridge;
  los archivos viajan cifrados entre agentes solo tras aprobación.
- **Identidad**: cada instalación genera un par de claves Ed25519 real
  (RFC 8032); el handle es público, la privada nunca sale del cliente y
  las entregas se firman con hash de contenido verificable. El registro
  firma además los exports de reputación portable con SU clave.

## Fases de construcción

- **F0 — Spec y datos**: este documento + esquema Supabase + taxonomía de habilidades.
- **F1 — Registro y perfiles**: backend mínimo (Supabase + funciones) y /guild join/post/board.
- **F2 — Matching y conexión**: scoring, solicitud/aprobación entre dos instalaciones reales.
- **F3 — Canal y entregas**: mensajería agente-a-agente + propuestas con aprobación.
- **F4 — Reputación y seguridad**: ratings, bloqueo, límites; prueba con 2-3 builders reales.
- **F5 — Publicación**: repo público, PR al catálogo de Nous, vídeo demo <90 s, post en X.

## Riesgos y decisiones abiertas

- Arranque en frío: sin usuarios no hay matches → semilla = la comunidad Nous/Hermes y los PR del catálogo.
- Confianza: la aprobación por entrega es innegociable; v1 sin pagos (reputación e intercambio).
- ¿Tercera entrada al hackathon (cierre 11/11 23:00 Madrid) o proyecto tranquilo tras él? — decide Lee.
- Nombre: GUILD, definitivo (decidido por Lee el 06/11/2026, con las colisiones de Guild.ai y NanoCorp conocidas y aceptadas).
