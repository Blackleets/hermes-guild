# GUILD — RUNBOOK de despliegue del registro (Día L)

> Estado: kit preparado y validado en local el 06/11/2026. **Nada de esto
> está desplegado.** Ejecutar solo el Día L, con el OK del fundador, paso a
> paso. Servidor: `guild/server.py` (Python, **solo stdlib**), v0.6.1 /
> protocolo v1.6.

## Decisiones del kit (y por qué)

| Pieza | Elección | Por qué, en una línea |
|---|---|---|
| Artefacto | **Docker** (`deploy/Dockerfile` + `deploy/docker-compose.yml`) — **recomendado** | Un VPS pequeño queda reproducible y desechable: misma imagen en local y en producción, sin tocar el Python del sistema; rollback = volver a la imagen anterior. |
| Alternativa | systemd (`deploy/guild-registry.service`) | Viable porque el servidor es stdlib pura (basta `python3` del sistema); se deja lista por si el VPS no lleva Docker, pero exige cuidar a mano usuario, permisos y actualizaciones de Python. |
| TLS | **Caddy** (`deploy/Caddyfile.example`) | TLS automático de verdad (ACME/Let's Encrypt sin certbot, sin cron de renovación, sin fechas que vigilar): para un registro operado por una persona, un fallo menos posible que nginx+certbot. |
| Healthcheck | `GET /v1/stats` | **No existe endpoint `/health`** en `guild/server.py`. `/v1/stats` es público, devuelve 200 y de paso expone `registry_public_key` (la clave pública con la que se verifica fuerte la reputación portable). |

## Hechos del código que manda sobre este runbook (verificados en `guild/server.py` y `guild/registry.py`)

- CLI: `python3 -m guild.server --db <db> --host <host> --port <puerto>`;
  equivalentes por entorno: `GUILD_DB`, `GUILD_HOST`, `GUILD_PORT`.
  Defectos del código: db `guild-registry.db`, host `127.0.0.1`, puerto `8787`.
- Clave privada del registro, orden de resolución: `GUILD_REGISTRY_PRIVATE_KEY`
  (entorno, no se persiste) → fichero `GUILD_REGISTRY_KEY_FILE` o, por defecto,
  `<db>.registry-key` junto a la base.
- El fichero de clave debe ser **0600**: el servidor lo crea con 0600 desde el
  primer byte, y **rechaza con error claro un `GUILD_REGISTRY_KEY_FILE`
  explícito con permisos más abiertos**. Ojo, verificado en local el
  06/11/2026: la resolución de la clave es **perezosa** — el proceso arranca
  aunque el fichero esté laxo, y el rechazo salta en el **primer uso** de la
  clave (`GET /v1/stats` devuelve error 400 con el mensaje de chmod). Por eso
  el paso 5 (stats + `stat` del fichero) es obligatorio y no opcional: un
  contenedor «arrancado» con la clave laxa está roto aunque el proceso viva,
  y el HEALTHCHECK contra `/v1/stats` lo marcará `unhealthy`. Rotación:
  `python3 -m guild.server --db <db> --rotate-key` (los exports viejos solo
  verifican contra la pública antigua: guárdala antes de rotar).
- Concurrencia: una conexión SQLite compartida, escrituras serializadas
  (suficiente para una comunidad; no es un servidor de alto tráfico).
- El stream SSE `GET /v1/events` va delimitado por cierre de conexión:
  el proxy no debe amortiguarlo ni cerrarlo antes de tiempo (Caddy no
  bufferiza `reverse_proxy` por defecto).

## Cómo se garantiza el 0600 del fichero de clave

1. El servidor lo crea con `os.open(..., 0o600)` — nace 0600, no se aprieta después.
2. En Docker, el entrypoint del `Dockerfile` hace `chmod 600` sobre
   `GUILD_REGISTRY_KEY_FILE` **antes** de arrancar, por si el volumen traía
   un fichero montado con permisos laxos (si no, el servidor rechazaría la
   clave en su primer uso y `/v1/stats` fallaría: ver la nota de resolución
   perezosa más arriba).
3. En systemd, `UMask=0077` + `StateDirectoryMode=0700`.
4. Verificación obligatoria tras el arranque (paso 5): `stat` debe decir `600`
   y el propietario debe ser el usuario del servicio (`guild`).

---

## Paso 0 — Antes de tocar nada

- [ ] OK explícito del fundador para el Día L y dominio elegido
      (este runbook usa `registry.example.com` como marcador: sustituir).
- [ ] Primer backup imposible (no hay datos todavía): el primer backup se
      hace en el paso 6, nada más pasar el humo.

## Paso 1 — Provisionar el VPS

VPS pequeño basta (1 vCPU / 1 GB RAM / 10 GB disco): el servidor es stdlib
pura sobre SQLite. Sistema: Debian/Ubuntu LTS.

```bash
# En el VPS, como root:
apt-get update && apt-get install -y docker.io docker-compose-v2 caddy ufw git
systemctl enable --now docker caddy
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
# El puerto 8787 NO se abre al exterior: solo loopback, detrás de Caddy.
```

## Paso 2 — Apuntar el DNS

En el proveedor DNS del dominio elegido:

```
registry.example.com.   A   <IP-del-VPS>
```

Esperar a que resuelva desde fuera antes de seguir (Caddy necesita el
puerto 80 libre y el nombre resolviendo a este VPS para emitir el certificado):

```bash
dig +short registry.example.com   # debe devolver la IP del VPS
```

## Paso 3 — TLS con Caddy

```bash
cp deploy/Caddyfile.example /etc/caddy/Caddyfile   # editar: dominio real
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Caddy emitirá el certificado al primer acceso HTTPS. No hay paso manual
de renovación: Caddy renueva solo antes de caducar.

## Paso 4 — Desplegar el registro (Docker, recomendado)

```bash
# En el VPS:
git clone <repo-de-guild> guild && cd guild   # o copiar el repo por scp
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps        # debe salir healthy
docker compose -f deploy/docker-compose.yml logs --tail=20
# Debe leerse: «Registro GUILD escuchando en http://0.0.0.0:8787»
```

Datos: volumen Docker `guild-data` montado en `/data` con
`registry.db` + `registry.db.registry-key`. El contenedor corre como
usuario sin privilegios `guild`, con `read_only`, sin capabilities y el
puerto publicado **solo en `127.0.0.1:8787`** (el exterior entra por Caddy).

### Alternativa systemd (solo si no hay Docker)

```bash
sudo useradd --system --home-dir /opt/guild guild
sudo cp -r guild /opt/guild/
sudo mkdir -p /var/lib/guild && sudo chown guild:guild /var/lib/guild
sudo cp deploy/guild-registry.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now guild-registry
sudo systemctl status guild-registry
```

## Paso 5 — Verificación inmediata (antes del humo)

```bash
curl -s http://127.0.0.1:8787/v1/stats | python3 -m json.tool   # en el VPS
curl -s https://registry.example.com/v1/stats | python3 -m json.tool
# Permisos de la clave (Docker):
ls -l /var/lib/docker/volumes/guild-data/_data/
# registry.db.registry-key debe ser: -rw------- (600), dueño guild/root del volumen
sudo stat -c '%a %U %n' /var/lib/docker/volumes/guild-data/_data/registry.db.registry-key
# systemd: stat -c '%a %U %n' /var/lib/guild/registry.db.registry-key  -> 600 guild
```

Anotar la `registry_public_key` que devuelve `/v1/stats`: es la clave
pública oficial del registro; se publica para la verificación fuerte de
exports (PROTOCOL, «Reputación portable firmada»).

## Paso 6 — PRUEBA DE HUMO contra el registro público

Ejercita join + entrega cifrada E2E de extremo a extremo con el cliente
real de GUILD (`deploy/smoke_test.py`):

```bash
# Desde cualquier máquina con el repo (o en el propio VPS):
GUILD_REGISTRY_URL=https://registry.example.com python3 deploy/smoke_test.py
```

Debe imprimir, en orden: `/v1/stats` 200 con `registry_public_key` ·
join ×2 con `enc_public_key` · necesidad + conexión aprobada por el dueño ·
**entrega cifrada E2E descifrada por el dueño con el texto idéntico** ·
firma verificada · `🎉 HUMO COMPLETO`, exit 0.

Si falla: **no se anuncia nada** y se va directo a ROLLBACK (abajo).
Nota: el humo deja dos perfiles `smoke-<timestamp>-a/b` en el registro;
si el registro debe nacer limpio para el anuncio, repetir los pasos 4–6
con un volumen nuevo tras un humo previo satisfactorio, o aceptar los
perfiles de humo como primeros habitantes declarados.

## Paso 7 — Primer backup (obligatorio tras el humo)

```bash
GUILD_DATA_DIR=/var/lib/docker/volumes/guild-data/_data \
GUILD_BACKUP_DIR=/root/guild-backups \
  sh deploy/backup.sh
```

⚠️ **El backup incluye la clave privada del registro: es un SECRETO.**
Guárdalo cifrado y fuera de cualquier repo (ver cabecera de `backup.sh`).
Copia ese directorio a un segundo destino cifrado fuera del VPS el mismo día.

## Paso 8 — Anuncio

Solo con pasos 5–7 en verde: publicar la URL y la `registry_public_key`.
A partir de aquí, backups periódicos (cron del operador, p. ej. diario)
con la misma orden del paso 7.

---

## Restaurar un backup

```bash
# 1. Parar el registro
docker compose -f deploy/docker-compose.yml stop     # o: systemctl stop guild-registry
# 2. Mover (no borrar) los datos actuales por si hay que volver
mv /var/lib/docker/volumes/guild-data/_data/registry.db{,.roto-$(date +%F)}
mv /var/lib/docker/volumes/guild-data/_data/registry.db.registry-key{,.roto-$(date +%F)}
# 3. Copiar el backup elegido y fijar permisos
cp /root/guild-backups/<STAMP>/registry.db /var/lib/docker/volumes/guild-data/_data/
cp /root/guild-backups/<STAMP>/registry.db.registry-key /var/lib/docker/volumes/guild-data/_data/
chmod 600 /var/lib/docker/volumes/guild-data/_data/registry.db.registry-key
( cd /root/guild-backups/<STAMP> && sha256sum -c SHA256SUMS )   # verificar huellas
# 4. Arrancar y repetir verificación + humo (pasos 5 y 6)
docker compose -f deploy/docker-compose.yml start
```

En systemd, mismo procedimiento con rutas `/var/lib/guild/`.

## ROLLBACK (si el humo o la verificación fallan)

El registro del Día L nace vacío: **no hay datos de usuarios que proteger
todavía**, así que el rollback es apagar y empezar de cero sin anunciar nada.

```bash
# 1. Apagar la cara pública primero: nadie debe entrar a un registro roto
systemctl stop caddy                                  # o quitar el bloque del Caddyfile y recargar
# 2. Apagar el registro
docker compose -f deploy/docker-compose.yml down      # conserva el volumen
# 3a. Si el fallo es de código/configuración: corregir, reconstruir y repetir desde el paso 4
docker compose -f deploy/docker-compose.yml up -d --build
# 3b. Si el fallo es de datos (volumen corrupto o clave dudosa): nacer de cero
docker compose -f deploy/docker-compose.yml down -v   # borra el volumen: DB y clave
docker compose -f deploy/docker-compose.yml up -d --build
#    (una clave nueva implica una registry_public_key nueva: la del paso 5
#     queda inválida y hay que republicarla; los exports firmados con la
#     antigua — aún ninguno el Día L — no verificarían contra la nueva)
# 4. Repetir pasos 5 y 6 completos antes de volver a encender Caddy
systemctl start caddy
```

Si el rollback ocurre **después** del anuncio (ya hay perfiles reales):
no usar `down -v` jamás; restaurar el último backup bueno (sección
anterior) y repetir el humo antes de reabrir Caddy.

## Operación mínima posterior

- **Logs:** `docker compose -f deploy/docker-compose.yml logs -f` (el
  servidor es silencioso por diseño: `log_message` está desactivado en
  `server.py`; los errores operativos se ven en el arranque y en systemd/
  Docker, no por petición).
- **Salud:** `curl -s https://registry.example.com/v1/stats` (no hay `/health`).
- **Rotación de clave:** solo si hay motivo; antes, guardar la pública
  antigua y el backup. Comando y consecuencias: PROTOCOL, «La clave de
  firma del registro».
- **Actualización:** `git pull` + repetir pasos 4–6 (el volumen persiste;
  la clave no se regenera porque ya existe el fichero 0600).
