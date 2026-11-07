# NOMBRES — Lista corta comprobada para la red hoy llamada GUILD

**Fecha de las comprobaciones: 2026-11-06.** Documento de decisión para
Lee (Fase 0): lista corta con disponibilidad **comprobada**, no una
decisión. GUILD sigue siendo el nombre vigente; nada se ha renombrado.

> **Nota de corrección (06/11/2026, mismo día):** la primera pasada de
> dominios se hizo a través del intermediario rdap.org y produjo
> lecturas inconsistentes (en particular, 404 genéricos para todo
> `.io` y varias fechas erróneas). La versión vigente de este
> documento usa **solo los servidores RDAP autoritativos de cada
> registro** (abajo) y marca `.io` como **no comprobado**. Si leíste
> una versión anterior: `guildhall.*` NO está libre, `commons.network`
> NO está libre y ningún dato de `.io` de la primera pasada era
> válido.

## Método (y sus límites, sin maquillar)

| Comprobación | Herramienta usada | Qué significa el resultado |
|---|---|---|
| Repo en la cuenta del fundador | `curl https://api.github.com/repos/Blackleets/<slug>` | **404 = indicio de libre**, no garantía (un repo privado también puede dar 404 sin autenticación; se asume que la cuenta no oculta repos con estos nombres). 200 = ocupado. |
| Dominio `.dev` | **RDAP autoritativo de Google Registry**: `https://pubapi.registry.google/rdap/domain/<dominio>` | 200 = registrado (con fechas); 404 = sin registro = **indicio fuerte de libre**. No garantiza precio normal: un dominio libre puede ser *premium* o estar reservado; eso solo se confirma en el carrito de un registrador. |
| Dominio `.network` | **RDAP autoritativo de Identity Digital**: `https://rdap.identitydigital.services/rdap/domain/<dominio>` | Igual que `.dev`. |
| Dominio `.io` | **NO COMPROBADO** | `.io` **no tiene servicio RDAP** en el bootstrap oficial de IANA (comprobado en `data.iana.org/rdap/dns.json`: hay entrada para `dev` y `network`, no para `io`). El whois por puerto 43 está denegado por los permisos de red de esta máquina (`other_tcp: Deny`) y el whois web consultado está bloqueado por política. Todo `.io` queda **sin verificar** en esta pieza; el intermediario rdap.org devuelve un 404 propio para `.io` que NO es dato del registro y no debe usarse. |
| Colisiones en el ecosistema | `browser.search` con «<nombre> AI agents» / «<nombre> agent network» y variantes | Búsqueda web breve, no exhaustiva: detecta proyectos conocidos, no hace búsqueda de marcas registradas (EUIPO/USPTO fuera de esta pieza). |

**Por qué no se usó DNS:** el resolver del sandbox devuelve una IP de
la red 198.18.0.0/15 para *cualquier* nombre (comprobado con un dominio
inventado, `zzzqqx-nonexistent-987123.dev`, que también «resolvía»), y
los resolvers públicos (8.8.8.8, 1.1.1.1) devuelven REFUSED. RDAP
quedó validado con controles: el dominio inventado devuelve 404 en el
RDAP de Google, y `forgekin.dev` devuelve su registro completo.

**Hallazgo general antes de la lista:** de los 16 dominios `.dev` /
`.network` comprobados (8 candidatos × 2 TLD), **solo uno está sin
registrar: `forgekin.network`**. Todas las palabras de diccionario
están ocupadas en ambos TLD verificados, y además colisionan con
proyectos reales de agentes. El espacio de nombres del sector está
saturado en 2026.

---

## Candidato 0 — GUILD (quedarse con el nombre actual)

**Evocación y encaje.** El gremio medieval de artesanos: maestros de
oficios distintos que se ayudan, se avalan y guardan estándares
comunes. Es, literalmente, el concepto del producto (builders de
distintos dueños, reputación ganada, aprobación mutua), y el
posicionamiento ya está construido sobre él: «Hermes multiplica a TU
agente. GUILD conecta tu Hermes con los builders de otros Hermes».
Pronunciación: /ɡɪld/, en español «guil» — asumible.

- **Repo:** `Blackleets/guild` → **404 (indicio de libre)**. Extra:
  `Blackleets/hermes-guild` —el nombre que el README ya anuncia como
  repo público— también **404 (indicio de libre)**.
- **Dominios (RDAP autoritativo):** `guild.dev` **registrado**
  (2019-02-27 → 2027-02-27); `guild.network` **registrado**
  (2020-07-21 → 2027-07-21); `guild.io` **no comprobado** (ver
  método). Los dos TLD verificados, ocupados.
- **Colisiones: REALES Y GRAVES, es el peor expediente de la lista.**
  - **Guild.ai** — «the control plane for AI agents»: plataforma
    comercial de gobierno de agentes, con Agent Hub y SDK.
  - **NanoCorp «Guild»** (guild.nanocorp.app) — «Professional network
    and registry for AI agents»: perfiles, reputación, discovery y
    colaboración entre agentes. Es casi el mismo posicionamiento.
  - **Agent Guild** (MCP, AgentTanuki) — red de reputación portable
    entre agentes con credenciales firmadas: solapa con el foso de
    reputación portable del producto.
  - Continental Guild y otros menores.
- **Veredicto:** el mejor nombre-concepto y el peor vecindario.
  Quedarse es defendible (coste de renombre: cero, ver abajo), pero
  exige disciplina permanente de apellido —«GUILD for Hermes»,
  repo `hermes-guild`— y aceptar que un buscador siempre devolverá
  antes a Guild.ai y a NanoCorp.

## Candidato 1 — FORGEKIN

**Evocación y encaje.** *Forge* (la fragua, forjar) + *kin*
(parentela, los tuyos): «la parentela de los que forjan». Conecta
además con una palabra de identidad del fundador: «forjando» es
central en Efesto/Internet Brain OS. Nombre inventado, registrable
como marca con más facilidad que una palabra de diccionario.
Pronunciación: FORCH-kin; un hispanohablante lo dice sin problema
tras oírlo una vez.

- **Repo:** `Blackleets/forgekin` → **404 (indicio de libre)**.
- **Dominios (RDAP autoritativo):** `forgekin.dev` **REGISTRADO**
  (2026-06-22 → 2027-06-22, Amazon Registrar, con DNS de AWS; titular
  no visible — no es nuestro y no consta qué proyecto es);
  `forgekin.network` **404 = sin registro (indicio de libre)** — el
  único dominio libre de los 16 comprobados en esta pieza;
  `forgekin.io` **no comprobado** (ver método).
- **Colisiones:** ninguna directa en agentes/IA con el nombre exacto.
  La búsqueda devuelve palabras distintas (ForgeKernel, AgentForge) y
  un uso menor sin relación: «forgekin» como taxonomía de autómatas
  en Final Fantasy XIV. Colisión menor, fuera del sector.
- **Veredicto:** el expediente más limpio de la lista y el único
  candidato con un dominio verificado libre (`forgekin.network`,
  que además cuenta el producto: una red). Sus costes son otros:
  nombre inventado (hay que construirle el significado en el
  lanzamiento) y el `.dev` ya está en manos de un tercero desde
  junio de 2026.

## Candidato 2 — GUILDHALL

**Evocación y encaje.** La sala del gremio: el lugar físico donde los
artesanos se encuentran, muestran el trabajo y se contratan. Conserva
el 80 % del capital semántico de GUILD y añade «lugar de encuentro»,
que es lo que el registro es. Pronunciación: GUIL-jol, asumible.

- **Repo:** `Blackleets/guildhall` → **404 (indicio de libre)**.
- **Dominios (RDAP autoritativo):** `guildhall.dev` **registrado**
  (2025-11-18 → 2027-11-18, Squarespace); `guildhall.network`
  **registrado** (2026-02-10 → 2027-02-10); `guildhall.io` **no
  comprobado**. Registro reciente en ambos TLD: coherente con
  tocayos recientes (abajo).
- **Colisiones: DESCALIFICANTES.**
  - **GuildHallAI/GuildHall** (GitHub, creado 2026-10-13): «the work
    and reputation network for AI agents and human contributors» —
    marketplace de trabajo y reputación para agentes, **con token
    $GUILD en Solana**. Mismo concepto y olor a cripto: exactamente
    lo que el nombre debía evitar.
  - guildhall.cc — harness de agentes para trabajo de software.
  - RodCor/guildhall — protocolo de colaboración entre agentes con
    reputación verificable (hackathon).
- **Veredicto:** **descartado** por partida doble: la colisión es la
  peor de la lista tras GUILD y los dominios verificados están
  ocupados.

## Candidato 3 — COMMONS

**Evocación y encaje.** El procomún: el espacio compartido que una
comunidad cuida y del que todos se benefician. Encaja con «red
abierta» y con reputación como bien común. Pronunciación: CÓ-mons,
fácil. Debilidad de nacimiento: es genérico — difícil de defender
como marca y de encontrar en un buscador.

- **Repo:** `Blackleets/commons` → **404 (indicio de libre)**.
- **Dominios (RDAP autoritativo):** `commons.dev` **registrado**
  (2025-12-21 → 2026-12-21); `commons.network` **registrado**
  (2016-11-23 → **2026-11-23**: expira este mes, pero una expiración
  cercana NO es disponibilidad — su titular puede renovarlo hasta el
  último día y durante el periodo de gracia posterior);
  `commons.io` **no comprobado**.
- **Colisiones: reales en el concepto.** **Operator Commons**
  (operatorcommons.ai): red de confianza donde los agentes de
  operadores aprobados aprenden unos de otros — vecino conceptual muy
  próximo. **Hive Commons** (proyecto Sandbox de la CNCF): familia
  OSS para trabajar con agentes de código. **The Agent Commons**:
  comunidad de agentes con publicación y voto.
- **Veredicto:** **descartado** en esta ronda: sin ningún TLD
  verificado libre y con un vecino que ya ocupa el concepto. Solo
  resucitaría si `commons.network` caducara de verdad sin renovación
  (vigilable a partir del 2026-11-23, sin contar con ello).

## Candidato 4 — FORGE

**Evocación y encaje.** La fragua: donde la materia prima se
convierte en herramienta. Potente y muy «builder»; como verbo ya vive
en el copy del ecosistema del fundador. Pronunciación perfecta en
español («forch»).

- **Repo:** `Blackleets/forge` → **404 (indicio de libre)**.
- **Dominios (RDAP autoritativo):** `forge.dev` **registrado**
  (2025-05-07 → 2027-05-07); `forge.network` **registrado**
  (2022-01-20 → 2028-01-20); `forge.io` **no comprobado**.
- **Colisiones: saturación total.** CoreWeave Forge (plataforma
  enterprise de agentes, lanzada 2026-09-30), Agent Forge de AITECH
  (no-code de agentes, migrado a Ethereum — adyacencia cripto),
  Asymbl Forge (gestión de proyectos para equipos humano+agentes),
  useforge.ai (runtime del estándar Agent Skills), y la familia
  Forgejo/Codeberg en dev-tools.
- **Veredicto:** **descartado** como nombre propio. Puede seguir
  usándose como descriptor («where builders forge together»), nunca
  como la marca.

## Candidato 5 — ATELIER

**Evocación y encaje.** El taller del artesano: pequeño, cuidado,
premium; un atelier es colaboración entre especialistas bajo un mismo
techo. El más elegante de la lista. Contra: su pronunciación inglesa
(/əˈtɛljeɪ/) es la peor para un hispanohablante, que lo leerá
«a-te-li-é».

- **Repo:** `Blackleets/atelier` → **404 (indicio de libre)**.
- **Dominios (RDAP autoritativo):** `atelier.dev` **registrado**
  (2020-01-26 → 2028-01-26); `atelier.network` **registrado**
  (2025-04-08 → 2027-04-08); `atelier.io` **no comprobado**.
- **Colisiones: reales y en el mismo sector.** **Atelier**
  (remp0x/atelier): marketplace donde agentes autónomos se contratan
  y cobran en USDC sobre Solana/Base — mismo sector y adyacencia
  cripto directa. Además: Atelier, chat-first agentic coding
  (studioatelier.ca); el workspace Atelier de Arabic.AI; varios
  frameworks «Atelier» para agentes.
- **Veredicto:** **descartado.** Elegante, ocupado y con un tocayo
  marketplace-de-agentes con pagos on-chain.

## Candidato 6 — LOOM

**Evocación y encaje.** El telar: hilos distintos (builders,
ecosistemas) tejidos en una sola tela. Metáfora bonita para una red
que entrelaza. Pronunciación: «lum», perfecta.

- **Repo:** `Blackleets/loom` → **404 (indicio de libre)**.
- **Dominios (RDAP autoritativo):** `loom.dev` **registrado**
  (2019-02-28 → 2027-02-28); `loom.network` **registrado**
  (2017-08-07 → 2027-08-07); `loom.io` **no comprobado** en esta
  pieza (la colisión de abajo no depende de este TLD).
- **Colisiones: insalvables.** Loom, el vídeo asíncrono de Atlassian
  (25 M de usuarios, 400 000 empresas), es dueño absoluto de la
  palabra en software. Y dentro de agentes: **AWS Loom** (plataforma
  open source de AWS Labs para gobernar agentes, 2026) y
  `loom-agents` (orquestación multi-agente en PyPI).
- **Veredicto:** **descartado.** Ni regalado: cualquier búsqueda
  será de Atlassian.

## Candidato 7 — KINDRED

**Evocación y encaje.** *Kindred spirits*: almas afines. Evoca la
afinidad entre builders que no se conocen pero comparten oficio —
el «clic» del matching. Pronunciación: KIN-dred, asumible en español.

- **Repo:** `Blackleets/kindred` → **404 (indicio de libre)**.
- **Dominios (RDAP autoritativo):** `kindred.dev` **registrado**
  (2019-03-04 → 2027-03-04); `kindred.network` **registrado**
  (2019-03-22 → 2027-03-22); `kindred.io` **no comprobado**.
- **Colisiones: reales, con tinte cripto.** **Kindred AI**: companions
  agénticos con token **$KIN** en Sei/BNB Chain — el apellido ya
  huele a token. Kindred Voice (agentes de voz en producción),
  Kindred Personal Assistant (asistente IA en beta privada), más
  proyectos menores con el mismo nombre.
- **Veredicto:** **descartado.** La evocación es buena; el vecindario
  (token $KIN) contradice la regla de no sonar a cripto.

---

## Recomendación ordenada

1. **FORGEKIN** — El único candidato que pasa las comprobaciones:
   repo libre (indicio), `forgekin.network` sin registrar (indicio
   RDAP autoritativo — el único dominio libre de los 16 comprobados),
   cero tocayos en agentes. Suma identidad propia del fundador
   («forjando») y es el más defendible como marca. Precio a pagar:
   es un nombre inventado — el lanzamiento tiene que enseñar qué
   significa — y el `.dev` pertenece a un tercero desde 2026-06-22.
2. **GUILD (quedarse)** — Si Lee prioriza el concepto y la velocidad:
   el posicionamiento, los materiales y el vídeo ya existen, y el
   coste de renombre es cero. El precio es permanente pero conocido:
   diferenciarse siempre de Guild.ai y del «Guild» de NanoCorp con el
   apellido «for Hermes» y el repo `hermes-guild` (libre, indicio).
3. **Vacante — ningún otro candidato pasa el corte.** COMMONS era el
   tercero hasta la reverificación: `commons.network` está registrado
   desde 2016. En vez de rellenar el podio con un descartado, la
   tercera recomendación es de método: **ronda 2 de compuestos
   inventados** (el patrón de FORGEKIN: raíz artesana + sufijo de
   comunidad o lugar), pasados por esta misma batería —repo, RDAP
   autoritativo .dev/.network, colisiones— antes de enamorarse de
   ninguno. La evidencia de esta pieza es que insistir en palabras de
   diccionario es perder: las 7 están registradas en ambos TLD
   verificados y/o colisionadas.

---

## Coste de cambiar de nombre (si Lee renombra)

**Método declarado:** `grep -ril "guild"` (insensible a mayúsculas)
sobre `~/workspace/guild-plugin/`, excluyendo `.venv`, `__pycache__`
y `.git`. Resultado el 2026-11-06:

- **59 archivos** contienen «guild»: **57 de fuente** + 2 generados
  (`.pytest_cache/v/cache/nodeids` y el bundle compilado
  `dashboard/dist/index.js`, que se regeneran solos).
- **≈925 líneas** con al menos una mención.
- **Nombres con «guild» en la ruta:** el paquete Python `guild/`
  (13 archivos dentro), `skills/hermes-guild/`,
  `deploy/guild-registry.service` y `tests/test_guild.py`.

**El coste depende de qué renombre se haga:**

- **Solo marca visible** (textos, landing, launch, skills de
  incorporación): ~20 archivos — `README.md`, `README.es.md`,
  `CONCEPTO.md`, `ESTADO.md`, `CHANGELOG.md`, `PROTOCOL.md`
  (titular), `landing/index.html`, `landing/index.es.html`,
  `skill.md`, `skill.es.md`, `clients/muse/SKILL.md`,
  `skills/hermes-guild/SKILL.md`, `launch/` (4 archivos: plan,
  cold_start, post_x, video_script), `docs/` (2). Trabajo de edición,
  no de ingeniería; los comandos `/guild` y el paquete seguirían
  llamándose guild por dentro (precedente común: la marca y el
  identificador interno no tienen por qué coincidir).
- **Renombre profundo** (marca + comando `/guild` + paquete `guild/`
  + endpoints + esquema): los **57 archivos de fuente**, incluyendo
  `guild/` entero, `commands.py`, `hooks.py`, `tools.py`,
  `schemas.py`, `__init__.py`, `plugin.yaml`, `dashboard/` (3),
  `supabase/schema.sql`, `deploy/` (6), `scripts/` (4) y `tests/`
  (5, que habría que re-verificar enteros tras el cambio). Es el
  renombre que rompe cosas: también tocaría handles ya comunicados,
  el vídeo de lanzamiento y cualquier enlace publicado.

**Lista completa de archivos con mención (57 de fuente):** raíz:
`.gitignore`, `CHANGELOG.md`, `CONCEPTO.md`, `ESTADO.md`,
`PROTOCOL.md`, `README.es.md`, `README.md`, `__init__.py`,
`commands.py`, `config.example.json`, `hooks.py`, `plugin.yaml`,
`schemas.py`, `skill.es.md`, `skill.md`, `tools.py` ·
`clients/muse/SKILL.md` · `dashboard/manifest.json`,
`dashboard/plugin_api.py` (+ `dist/index.js` generado) ·
`deploy/Caddyfile.example`, `deploy/Dockerfile`, `deploy/backup.sh`,
`deploy/docker-compose.yml`, `deploy/guild-registry.service`,
`deploy/smoke_test.py` · `docs/hermes-real-test-transcript.txt`,
`docs/hermes-real-test.md` · `guild/` (13: `__init__`, `client`,
`e2e`, `identity`, `matching`, `needs`, `paths`, `portable`,
`profile_page`, `registry`, `server`, `taxonomy`, `transport`) ·
`landing/index.es.html`, `landing/index.html` ·
`launch/PLAN_LANZAMIENTO.md`, `launch/cold_start.md`,
`launch/post_x.md`, `launch/video_script.md` ·
`scripts/demo_e2e.py`, `scripts/demo_hermes_real.py`,
`scripts/demo_network.py`, `scripts/hermes_side_runner.py` ·
`skills/hermes-guild/SKILL.md` · `supabase/schema.sql` ·
`tests/test_events_realtime.py`, `tests/test_guild.py`,
`tests/test_profile_page.py`, `tests/test_v05_http.py`,
`tests/test_v06_blindaje.py`.

## Comprobaciones no completadas (y por qué)

- **Todos los `.io` (8 dominios): no comprobados.** `.io` no tiene
  servicio RDAP en el bootstrap de IANA; el whois por puerto 43 está
  denegado por los permisos de red de esta máquina y el whois web
  consultado está bloqueado por política. Ningún dato `.io` de esta
  pieza debe darse por verificado; si un finalista depende de su
  `.io`, hay que comprobarlo desde una red con whois/RDAP completo
  (p. ej. el navegador de Lee o un registrador).
- **whois clásico:** binario no instalado; sustituido por RDAP
  autoritativo, que es su sucesor oficial y fuente registral directa.
- **Resolución DNS:** invalidada por el resolver del sandbox
  (wildcard sintético 198.18.x para todo nombre) y REFUSED en
  resolvers públicos; no se presenta ningún resultado DNS como
  evidencia.
- **Precio/disponibilidad en registrador y marcas registradas:** no
  comprobados; un RDAP 404 no descarta dominio premium ni conflicto
  de marca. Si un candidato pasa a finalista, la Fase 0 debería
  añadir: carrito en el registrador elegido + búsqueda EUIPO/USPTO +
  handles en X/GitHub org antes de anunciarlo.
