# Prueba en Hermes real — GUILD v0.5.0 (Pieza 1 «Credibilidad»)

**Fecha:** 2026-11-06 · **Resultado: 13/13 comprobaciones en verde,
exit 0, sin tracebacks.** Transcripción completa de la corrida:
`docs/hermes-real-test-transcript.txt` (única redacción: la API key
de un perfil de un registro efímero que se borró al terminar).

## Entorno exacto (sin maquillar)

| Pieza | Valor real |
|---|---|
| Checkout de Hermes | `~/workspace/la-asistenta/hermes` (árbol de desarrollo del proyecto La Asistenta, **no una release oficial**) |
| git HEAD del checkout | `ab094da00f8d492eacc4f9524f938bd9c7c9d9f4` (2026-10-27) |
| Versión según el propio Hermes | `hermes_cli.__release_date__ = "2026.9.24"`; `get_version_info()` → `base_version='unknown'`, `derived_version='git.ab094da'`, rama `main`, árbol limpio. Es un checkout sin sello de release: **no se puede afirmar un número de versión oficial** |
| Intérprete usado | El venv que PM provisiona para ese checkout (`hermes-home/installs/…/environments/…/venv/bin/python`), **Python 3.14.9** — el Python del sistema no sirve (le falta `ruamel.yaml`, dependencia de `hermes_cli`) |
| Puerta `requires_hermes: ">=0.21.5"` | `requires_hermes_error(manifest)` devolvió `None` (el gestor no bloqueó la carga; con `base_version='unknown'` la puerta no tiene número contra el que fallar — se reporta tal cual) |
| Checkout modificado | **No.** Solo lectura/ejecución de su cargador; el plugin se copió a un directorio temporal y `HERMES_HOME`/`GUILD_DATA_DIR` apuntaron a temporales |

## Método

`scripts/demo_hermes_real.py` (driver, Python de GUILD) levanta un
servidor GUILD real por HTTP sobre una SQLite temporal y lanza
`scripts/hermes_side_runner.py` con el intérprete de Hermes en 4
fases. El runner carga el plugin **por el camino real de discovery**:

```python
manifest = parse_manifest_file(plugin_copy/"plugin.yaml", plugin_copy, "user", "")
mgr = PluginManager(scope_key=HERMES_HOME_tmp)
mgr._load_plugin(manifest)   # el mismo método que usa la discovery real
```

y después ejercita lo registrado a través de las APIs reales del
gestor: el handler del comando desde `mgr._plugin_commands["guild"]`,
las tools con `PluginContext(manifest, mgr).dispatch_tool(...)` y el
hook con `mgr.invoke_hook("on_session_start")`.

## Qué registró el cargador real (salida literal)

```
[runner] manifiesto: hermes-guild v0.5.0 · requires_hermes=>=0.21.5 · puerta: None
[runner] cargado: enabled=True error=None
[runner] tools=['guild_board', 'guild_matches', 'guild_status', 'guild_inbox']
[runner] hooks=['on_session_start'] commands=['guild'] skills=['hermes-guild:hermes-guild']
```

## Qué se ejercitó, con qué resultado

**Lado Hermes (Marco, a través del plugin cargado):**
`/guild join` (perfil creado en el registro compartido) ·
`/guild board` (vio el post de Lee) · `/guild matches` →
**Marco 78.0/100** sobre el post de Lee [skills 50 · idioma 12 ·
reputación 8 · zona 8 · reciprocidad 0 — en este escenario Lee no
pide python y Marco no declara buscadas: la cifra es la que da el
código, distinta del 88.0 de las demos clásicas] · `/guild connect`
con contrato (entregable, hecho, fecha 2026-11-20) ·
`/guild deliver` (entrega propuesta, con el dato derivado
«entregada dentro de la fecha límite») · `/guild rate @lee 5 4 5` ·
`/guild post` (su necesidad de voz: **Lee sale candidato con
88.7/100**) · `/guild status` e `inbox` completos.

**Tools vía `ctx.dispatch_tool` (la API real del contexto):**
`guild_board` devolvió el post de Lee en la fase de carga;
`guild_status` devolvió `{"ok": true, "me": {@marco, reputación
4.67, verificadas ["baseten"], …}, "network": {…}}` en la fase final.

**Hook vía `manager.invoke_hook("on_session_start")`:**
con Marco unido y un match pendiente devolvió
`["📥 GUILD: 1 match nuevo para tus necesidades"]`. Antes de unirse
devuelve `[]` (sin estado no hay línea: comportamiento correcto).

**Lado Muse (Lee, cliente HTTP contra el mismo servidor):**
join + post de la necesidad real (FASHN VTON en Baseten) ·
**escucha SSE abierta antes de que Marco conectara: el evento
`connection_requested` llegó en vivo por el stream**
(`{"kind": "connection_requested", "connection_id": "…", "cursor": 4}`,
sin sondear el inbox) · aprobación de la conexión · aceptación de
la entrega · valoración (5,5,4) → **Marco: reputación 4.67/5 y
skill `baseten` verificada**. Marco valoró a Lee (5,4,5) → **Lee:
4.67/5**. Stats finales reales: 2 perfiles · 2 necesidades abiertas ·
1 conexión aprobada · 1 entrega aceptada · 2 valoraciones · 12 eventos.

## Bugs reales que esta prueba cazó (y se arreglaron)

1. **Imports absolutos latentes en el plugin.** `hooks.py` y las
   tools `guild_status`/`guild_inbox` importaban `from guild.paths
   import …` en el cuerpo de la función. Con el cargador real el
   paquete `guild` no está en `sys.path` (el cargador usa un
   namespace sintético): el hook devolvía siempre `None` y las dos
   tools devolvían `ModuleNotFoundError` en su JSON. Con los tests
   propios (import plano) nunca se vio. **Arreglo:** imports
   relativos primero con fallback absoluto, como ya hacían los
   demás módulos; verificado con la misma demo (hook y tool en
   verde) y la suite completa sigue en 80/80.
2. **La conexión compartida de SQLite no tolera el bucle del
   stream SSE** (pieza 2, cazado en esta misma demo):
   `sqlite3.InterfaceError: bad parameter or other API misuse` al
   ejecutar `match_pairs` desde el hilo del stream mientras otro
   hilo atendía una petición. **Arreglo:** cada escucha SSE abre su
   propia conexión al registro y tolera bloqueos transitorios.
3. No era un bug: `/guild inbox` marca los matches como leídos al
   abrirse (semántica v0.4), así que un hook invocado *después* de
   abrir el inbox no tiene nada nuevo que decir. La demo invoca el
   hook antes, como en una sesión real.

## Qué NO prueba esta prueba (pendiente, dicho claro)

- **Una release oficial actual de Hermes (v0.21+).** El checkout es
  un árbol de desarrollo sin sello (`base_version='unknown'`); el
  manifiesto declara `>=0.21.5` y la puerta no bloqueó, pero la
  compatibilidad con la release pública se confirmará el día del
  lanzamiento instalando el plugin en una.
- **El arranque de una sesión real de Hermes** (gateway/CLI con un
  humano): el hook se invocó vía `PluginManager.invoke_hook`, la
  misma API que usa el runtime, pero no dentro de una sesión viva.
- **El dashboard** del plugin en un host Hermes real con UI.
- **El transporte `hermes peer`** entre dos instalaciones reales
  (sigue probado solo con doble simulado, como en v0.4).
- **Entregas firmadas desde el comando `/guild`:** el estado del
  plugin no guarda la clave privada (solo `profile_id`, `handle`,
  `api_key`), así que las entregas por comando van **sin firmar**;
  la ruta firmada es la API del cliente (`GuildClient.deliver`),
  cubierta por la suite. La entrega de esta demo fue la de comando.

## Reproducir

```bash
cd ~/workspace/guild-plugin
.venv/bin/python scripts/demo_hermes_real.py   # autodetecta el venv de Hermes
# GUILD_HERMES_PYTHON=<python> GUILD_HERMES_CHECKOUT=<ruta> para fijarlos
```

## Addendum v0.6.0 (06/11/2026) — re-ejecución tras tocar los comandos

La corrida de arriba es la de v0.5.0. En v0.6.0 cambiaron
`commands.py` (firma desde `/guild deliver` con clave local) y las
importaciones del plugin, así que la demo se **re-ejecutó entera**
contra el mismo checkout (sin modificarlo): **13/13
comprobaciones en verde**, el manifiesto ya reporta versión
**0.6.0**, la carga con el cargador real no dio errores y los
perfiles exponen la nueva `enc_public_key`. La nota de la corrida
original sobre entregas por comando sin firmar queda **superada**:
desde v0.6.0 el comando firma cuando hay clave local guardada
(ver CHANGELOG v0.6.0 y los tests de `tests/test_v06_blindaje.py`).
