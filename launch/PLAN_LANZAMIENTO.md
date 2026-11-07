# GUILD — Plan de lanzamiento tranquilo (decisión de Lee, 06/11/2026)

**Decisión:** GUILD NO entra al hackathon de plugins de Nous como tercera
entrada. Se lanza tranquilo DESPUÉS del cierre (11/11 23:00 Madrid), como
proyecto propio con su momento — no a la sombra de Gazette y SpendGuard.
Enfoque: Hermes primero → Muse → API abierta.

> **⚠️ SUPERADO el 07/11/2026:** Lee ordenó «Lanzamiento completo de
> GUILD ahora», sustituyendo este calendario. La ejecución y su estado
> exacto están en la sección «Lanzamiento ejecutado» al final de este
> fichero y en `ESTADO.md` («LANZAMIENTO ADELANTADO»).

## Fase 0 — Preparación silenciosa (12–15/11, todo en local)

- [x] Nombre definitivo: **GUILD** — decidido por Lee el 06/11/2026
      («Quedarse con GUILD», con las colisiones conocidas sobre la mesa).
- [x] Revisión final del repo: diffs, secretos, README, landing —
      ejecutada el 07/11/2026 como pre-vuelo del lanzamiento adelantado
      (escaneo de secretos limpio; suite 118 passed).
- [x] Decisión de registro para el día 1: **LOCAL-FIRST** — decidido por
      Lee el 07/11/2026 («Local-first, central en v1.1»). La v1 sale con
      registro local (SQLite) y el registro central entra como v1.1;
      ningún material de lanzamiento puede prometer una red central que
      aún no existe (pasada de coherencia del copy = tarea de Fase 0).
- [x] Release preparada sin publicar — la release pública es la
      **v0.6.1** (el versionado siguió la numeración del plugin, no un
      v0.1.0 nuevo); notas = CHANGELOG.

## Día L — Lanzamiento: MIÉRCOLES 18/11/2026, ~16:30 Madrid

Fijado por Lee el 07/11/2026 («Miércoles 18, ciérralo así»), a propuesta
de Aragan: mitad de semana, 10:30 EST, jueves y viernes para responder a
la comunidad y el fin de semana libre antes de su CCSE del lunes 23/11.
**Sustituido el mismo 07/11 por la orden de lanzamiento inmediato.**

Cada paso externo requiere el OK final de Lee en ese momento:

1. Repo público `Blackleets/hermes-guild` (release v0.6.1).
2. PR al catálogo de plugins de Nous (como plugin normal, fuera del
   hackathon) → camino al Marketplace de Hermes.
3. Post único en X con el vídeo v4 explicativo en inglés (77,5 s) — lo
   publica Lee desde el texto listo en `launch/post_x.md`.
4. Landing en vivo enlazada desde el repo y el post.

## Ola 1 — Semilla Hermes (semana 1 tras el Día L)

- Presentación en la comunidad Nous/Hermes (canales del ecosistema).
- Objetivo honesto: 2–3 builders reales y la PRIMERA colaboración real
  cerrada con reputación — eso es la prueba social del post siguiente.
- Sin spam, sin métricas inventadas: se comunica solo lo que ocurra.

## Ola 2 — Muse (cuando haya matches reales de Hermes que enseñar)

- Cliente Muse (`clients/muse/SKILL.md` + `skill.md` público) anunciado
  como «el puente»: un usuario de Muse colabora con uno de Hermes.

## Ola 3 — API abierta

- Documentación pública del protocolo (`PROTOCOL.md`) para OpenClaw y
  cualquier agente. Puerta abierta, sin protagonismo.

## Reglas que no cambian

- Nada se publica sin el OK final de Lee, paso a paso.
- Verdad operacional: usuarios, matches y colaboraciones solo se
  comunican cuando sean reales.
- El vídeo oficial del lanzamiento es la v4 (77,5 s, explicativo en
  inglés, Hermes primero); la v3 en español queda como teaser.
  (Actualización 07/11: una v5 candidata fue descartada por Lee tras
  verla; hay una nueva versión en producción con Flow — cuál acompaña
  al post es decisión de Lee.)

## Lanzamiento ejecutado — 07/11/2026 (orden directa de Lee)

Lee ordenó «Lanzamiento completo de GUILD ahora»; el Día L del 18/11
queda sustituido. Estado exacto (detalle en `ESTADO.md`):

1. **Pre-vuelo: HECHO** — copy desfasado corregido (post de X con
   cifras v0.6.1/118 tests; pesos de matching canónicos en la landing
   ES), escaneo de secretos limpio, árbol de 67 ficheros / 717 KB todo
   UTF-8, suite **118 passed**.
2. **Repo público: BLOQUEADO** — la GitHub App devolvió
   `403 Resource not accessible by integration` al crear
   `Blackleets/hermes-guild`. Falta el gesto de Lee: crear el repo
   vacío y público y añadirlo a la instalación de la App «Meta Muse
   AI» (en su día pidió su código de seguridad). Tras eso: push por
   snapshot, release **v0.6.1** (sin herramienta de releases en el
   conector: click web) y topics.
3. **PR al catálogo: PAQUETE LISTO** en
   `~/workspace/guild-plugin-catalog-pr/` (YAML con el SHA por rellenar
   tras el push + descripción completa con disclosure). Se abre en
   cuanto exista el commit de la release.
4. **Post de X: FINAL en `launch/post_x.md`**, con enlace al repo y
   comando de instalación; lo publica Lee. No publicar hasta que la
   URL del repo cargue.
5. **Landing (GitHub Pages): PENDIENTE** del repo; activación en
   Settings → Pages con `landing/` como fuente (el conector no expone
   API de Pages).
