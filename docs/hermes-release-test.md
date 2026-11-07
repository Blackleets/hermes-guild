# Prueba en RELEASE OFICIAL de Hermes — GUILD v0.6.0 (cierre del límite «sin probar en release oficial»)

**Fecha:** 2026-11-06 · **Resultado: 13/13 comprobaciones en verde,
exit 0, sin tracebacks, a la primera corrida.** Transcripción
completa: `docs/hermes-release-test-transcript.txt` (única
redacción: la API key de un perfil de un registro efímero que se
borró al terminar — 2 apariciones, mismo criterio que en la prueba
de v0.5).

**Veredicto: el límite «Hermes real ≠ release oficial» de ESTADO.md
queda CERRADO.** hermes-guild 0.6.0 carga y funciona de punta a
punta con el cargador real de plugins de la release oficial
**v0.23.0** de Hermes Agent, sin tocar una línea del plugin ni de
ningún checkout.

## Cuál es la última release oficial (con evidencia)

Dos fuentes, el mismo resultado:

- **API de GitHub** — `GET /repos/NousResearch/hermes-agent/releases/latest`
  devolvió el 2026-11-06:
  - `tag_name: "v0.23.0"`
  - `name: "Hermes Agent v0.23.0 — The Hearth Release"`
  - `published_at: "2026-11-05T21:32:33Z"`, `draft: false`,
    `prerelease: false`, `immutable: true`
  - `target_commitish: "2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19"`
  - `html_url: https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.0`
- **`git ls-remote --tags`** confirma el tag y su commit pelado:
  `df1774294af26285ae758c6114f3f2f60e2a602d  refs/tags/v0.23.0` /
  `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19  refs/tags/v0.23.0^{}`.

Ambigüedades del repo, declaradas y resueltas:

- Conviven **dos esquemas de tags**: CalVer `v2026.*` (hasta
  `v2026.9.24` = Hermes v0.21.5) y semver `v0.21.6` → `v0.23.0`.
  La lista ordenada de *releases* (no solo tags) pone v0.23.0 la
  primera (2026-11-05), seguida de v0.22.7 (2026-11-03): no hay
  ninguna release `v2026.*` posterior a v0.21.5.
- Existen tags **canary** posteriores
  (`v0.23.0+canary.20261106T064428Z`), pero **no son releases**:
  no tienen objeto Release en GitHub ni son `releases/latest`.
  Se descartan por definición de «release oficial publicada».
- Conclusión: la última release oficial es **v0.23.0** (≥ la
  puerta `requires_hermes: ">=0.21.5"` del manifiesto y ≥ el
  «v0.21+» que pedía el límite).

## Entorno exacto (sin maquillar)

| Pieza | Valor real |
|---|---|
| Release probada | Tag **`v0.23.0`** de `NousResearch/hermes-agent` |
| Clon | `~/workspace/hermes-release-check/` — `git clone --branch v0.23.0 --depth 1 https://github.com/NousResearch/hermes-agent.git` (directorio NUEVO, fuera del árbol de GUILD; el checkout de La Asistenta no se usó como código, solo su venv de intérprete) |
| HEAD del clon | `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` — idéntico al `target_commitish` de la release; `git describe --tags --exact-match` → `v0.23.0`; árbol limpio antes y después |
| Versión según el propio Hermes (release) | `get_version_info()` → `VersionInfo(base_version='0.23.0', derived_version='0.23.0', distance=0, commit='2bd378ed…', source='git', dirty=False)`; `running_hermes_version()` → `'0.23.0'`; `hermes_cli.__release_date__ = "2026.9.24"` |
| Versión según el propio Hermes (dev, contraste) | El checkout de La Asistenta da `base_version='unknown'`, `derived_version='git.ab094da'` — la diferencia que importaba: en la release la puerta de versión se evalúa contra un número REAL |
| Puerta `requires_hermes: ">=0.21.5"` | `requires_hermes_error(manifest)` devolvió `None` en las 4 fases — esta vez contra `0.23.0` de verdad (0.23.0 ≥ 0.21.5), no en modo permisivo por versión desconocida |
| Intérprete usado | El mismo venv que PM provisiona para el checkout de La Asistenta (`hermes-home/installs/…/venv/bin/python`), **Python 3.14.9**, fijado con `GUILD_HERMES_PYTHON`. Es un venv de dependencias, no código del checkout dev: el código de Hermes que se ejecutó fue el del clon v0.23.0 (`sys.path.insert(0, checkout)` en el runner, verificado antes con `import hermes_cli.plugins` contra la ruta nueva) |
| Checkouts modificados | **Ninguno.** `git status --porcelain` vacío en `la-asistenta/hermes` (HEAD sigue en `ab094da00f8d492eacc4f9524f938bd9c7c9d9f4`) y en `hermes-release-check` tras la corrida; el plugin se copió a un directorio temporal y `HERMES_HOME`/`GUILD_DATA_DIR` apuntaron a temporales borrados al terminar |
| Código del plugin tocado | **Ninguno.** Ni el plugin, ni `scripts/demo_hermes_real.py`, ni el runner necesitaron cambios: el driver ya aceptaba la ruta por `GUILD_HERMES_CHECKOUT` |

## Método

El **mismo ejercicio** de v0.5/v0.6, parametrizado solo por
entorno (sin copiar ni parchear el script):

```bash
cd ~/workspace/guild-plugin
GUILD_HERMES_CHECKOUT=/home/hatch/workspace/hermes-release-check \
GUILD_HERMES_PYTHON=<venv PM de Hermes, Python 3.14.9> \
.venv/bin/python scripts/demo_hermes_real.py
```

El driver levanta un servidor GUILD real por HTTP sobre SQLite
temporal y lanza `scripts/hermes_side_runner.py` con el intérprete
de Hermes en 4 fases (`load`, `act1`, `act2`, `act3`). El runner
carga el plugin **por el camino real de discovery** de la release:
`parse_manifest_file(...)` + `PluginManager._load_plugin(manifest)`,
y ejercita lo registrado por las APIs reales del gestor: handler
del comando desde `mgr._plugin_commands["guild"]`, tools con
`PluginContext(manifest, mgr).dispatch_tool(...)` y hook con
`mgr.invoke_hook("on_session_start")`.

## Diferencias de API entre el checkout dev (ab094da) y v0.23.0

Medidas con `diff`, no supuestas:

- **`hermes_cli/plugins.py`: byte a byte idéntico** entre el
  checkout de desarrollo y la release v0.23.0 (2163 líneas,
  `diff` sin salida). Todas las piezas que usa el runner —
  `PluginManager`, `PluginContext.dispatch_tool`,
  `_load_plugin`, `_plugin_commands`, `_plugin_skills`,
  `invoke_hook` — están en el mismo sitio con la misma firma.
- **`hermes_cli/plugins_manifest.py`: difiere solo de forma
  aditiva** (568 → 586 líneas): añade el campo opcional
  `config_keys` a los manifiestos (helper `_config_key_path`,
  campo `config_keys` en `PluginManifest` y su paso en
  `portable_plugin_manifest`). `parse_manifest_file(...)` y
  `requires_hermes_error(...)` conservan nombre, firma y
  semántica; un manifiesto sin `config_keys` (el de GUILD) se
  parsea igual. **No hace falta ninguna adaptación.**

## Qué registró el cargador real de la release (salida literal, ×4 fases)

```
[runner] manifiesto: hermes-guild v0.6.0 · requires_hermes=>=0.21.5 · puerta: None
[runner] cargado: enabled=True error=None
[runner] tools=['guild_board', 'guild_matches', 'guild_status', 'guild_inbox']
[runner] hooks=['on_session_start'] commands=['guild'] skills=['hermes-guild:hermes-guild']
```

## Resultado, check a check (13/13)

Las 13 comprobaciones del driver, todas en verde (transcripción
completa en el fichero hermano):

1. ✓ plugin cargado sin error por PluginManager — `error=None`
2. ✓ registra 4 tools — guild_board, guild_matches, guild_status, guild_inbox
3. ✓ registra hook on_session_start
4. ✓ registra comando /guild
5. ✓ registra la skill del plugin — hermes-guild:hermes-guild
6. ✓ tool guild_board (vía ctx.dispatch_tool) ve el post de Lee
7. ✓ Marco se unió desde el comando /guild del plugin cargado
8. ✓ conexión creada desde el plugin (pendiente de Lee)
9. ✓ Lee recibió connection_requested EN VIVO por SSE (sin sondear el inbox)
10. ✓ la entrega de Marco llegó al inbox de Lee
11. ✓ reputación de Marco tras la valoración de Lee (5,5,4) — 4.67/5
12. ✓ skill baseten de Marco quedó VERIFICADA por la entrega aceptada
13. ✓ hook on_session_start invocado vía manager con Marco unido

Cifras reales de la corrida (idénticas a las de la prueba en dev,
como debe ser: es el mismo escenario y el mismo código):

- Match de Marco sobre el post de Lee: **78.0/100** [skills 50 ·
  idioma 12 · reputación 8 · zona 8 · reciprocidad 0]
- Marco valora y publica su necesidad de voz → Lee candidato con
  **88.7/100**
- Entrega de Marco desde `/guild deliver`: **firmada Ed25519 con
  su clave local y verificada por el registro** (comportamiento
  v0.6), dentro de la fecha del contrato (2026-11-20)
- Reputación final: Marco **4.67/5**, Lee **4.67/5**; perfiles con
  `enc_public_key` expuesta (v1.5)
- Stats finales de la red: 2 perfiles · 2 necesidades abiertas ·
  1 conexión aprobada · 1 entrega aceptada · 2 valoraciones ·
  13 eventos

## Control adicional

Sin haber tocado código, la suite de GUILD se re-corrió como
control tras la prueba: **97 passed** —
`.venv/bin/python -m pytest tests/ -q` → `97 passed in 10.43s`.

## Qué sigue SIN probar (para no sobredimensionar el cierre)

Cerrar este límite no convierte la prueba en más de lo que es:

- **El arranque de una sesión viva de Hermes con humano**
  (gateway/CLI reales): el hook se invocó vía
  `PluginManager.invoke_hook`, la misma API que usa el runtime,
  pero no dentro de una sesión interactiva.
- **El dashboard** del plugin en un host Hermes v0.23.0 con UI.
- **El transporte `hermes peer`** entre dos instalaciones reales
  de dueños distintos (sigue probado solo con doble simulado).
- **Un intérprete provisionado por la propia release**: se usó el
  venv PM existente (Python 3.14.9, dentro del rango
  `>=3.11,<3.15` que declara la release) apuntando al código
  v0.23.0; no se hizo una instalación limpia desde cero de la
  release con su instalador.

## Reproducir

```bash
git clone --branch v0.23.0 --depth 1 \
  https://github.com/NousResearch/hermes-agent.git ~/workspace/hermes-release-check
cd ~/workspace/guild-plugin
GUILD_HERMES_CHECKOUT=~/workspace/hermes-release-check \
GUILD_HERMES_PYTHON=<python del entorno Hermes> \
.venv/bin/python scripts/demo_hermes_real.py   # esperado: 13/13, exit 0
```

## Addendum v0.6.1 (06/11/2026)

Los comandos del plugin cambiaron en v0.6.1 (`/guild reject` con
motivo, `/guild close`, `/guild deliver` con `skills=`), así que la
prueba se re-ejecutó ENTERA contra esta misma release v0.23.0, con
el plugin ya en **0.6.1** (el manifiesto cargado reporta
`"version": "0.6.1"`): **13/13 en verde, exit 0**, sin tocar el
checkout. Las cifras de la demo no se movieron (Marco 78.0 sobre el
post de Lee, Lee candidato 88.7, reputación de Marco 4.67/5) y la
skill `baseten` de Marco quedó verificada bajo la regla precisa de
F1 (el post la pedía y Marco la ofrece en su perfil: la acredita la
intersección, sin declaración expresa en el comando).
