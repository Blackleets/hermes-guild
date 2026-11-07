#!/bin/sh
# ============================================================================
# GUILD — Backup del registro: base SQLite + fichero de clave del registro.
#
# ⚠️  EL BACKUP DE LA CLAVE ES UN SECRETO  ⚠️
# El fichero *.registry-key contiene la CLAVE PRIVADA Ed25519 con la que el
# registro firma la reputación portable. Quien lo tenga puede firmar exports
# falsos en nombre del registro. Por tanto:
#   - Guarda los backups SOLO en un destino cifrado y privado (disco cifrado,
#     gestor de secretos, caja fuerte offline). NUNCA en un repo git, NUNCA en
#     un bucket público, NUNCA por email/chat sin cifrar.
#   - Este script crea el directorio de backups con 0700 y cada fichero con
#     0600, y se niega a escribir si el destino ya existe con permisos laxos
#     que no pueda apretar.
#   - Perder la clave = perder la capacidad de que los exports antiguos
#     verifiquen fuerte contra ella. Perder la DB = perder la red. Las dos
#     cosas se respaldan juntas, siempre.
#
# Uso:
#   GUILD_DATA_DIR=/ruta/datos GUILD_BACKUP_DIR=/ruta/backups ./backup.sh
# Valores por defecto: datos = ./data (o /data si existe registry.db ahí),
# backups = ./backups. En el despliegue Docker con volumen con nombre:
#   GUILD_DATA_DIR=/var/lib/docker/volumes/guild-data/_data ./backup.sh
# (con Docker, parar el contenedor 10 s también es una vía válida y simple:
#  docker compose -f deploy/docker-compose.yml stop, copiar, start.)
#
# Restauración: ver RUNBOOK.md, sección «Restaurar un backup».
# ============================================================================
set -eu
umask 077

DATA_DIR="${GUILD_DATA_DIR:-./data}"
DB_FILE="${GUILD_DB_FILE:-$DATA_DIR/registry.db}"
KEY_FILE="${GUILD_REGISTRY_KEY_FILE:-$DB_FILE.registry-key}"
BACKUP_DIR="${GUILD_BACKUP_DIR:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/$STAMP"

if [ ! -f "$DB_FILE" ]; then
  echo "ERROR: no existe la base: $DB_FILE" >&2
  exit 1
fi
if [ ! -f "$KEY_FILE" ]; then
  echo "ERROR: no existe el fichero de clave: $KEY_FILE" >&2
  echo "Sin él el backup no sirve para verificar/firmar: abortado." >&2
  exit 1
fi

# Permisos del fichero de clave en origen: debe ser 0600.
KEY_MODE="$(stat -c '%a' "$KEY_FILE" 2>/dev/null || stat -f '%Lp' "$KEY_FILE")"
if [ "$KEY_MODE" != "600" ]; then
  echo "ERROR: el fichero de clave tiene permisos $KEY_MODE, exige 0600." >&2
  echo "Corrige con: chmod 600 \"$KEY_FILE\"" >&2
  exit 1
fi

mkdir -p "$DEST"
chmod 700 "$BACKUP_DIR" "$DEST"

# Copia consistente de la SQLite incluso con el servidor en marcha:
# se usa la API de backup online de sqlite3 vía python3 (stdlib, como el
# resto de GUILD). Si python3 no estuviera, copia directa (válida solo con
# el servidor parado; se avisa).
if command -v python3 >/dev/null 2>&1; then
  python3 - "$DB_FILE" "$DEST/registry.db" <<'PYEOF'
import sqlite3, sys
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close(); src.close()
PYEOF
else
  echo "AVISO: sin python3; copia directa (válida solo con el servidor parado)." >&2
  cp "$DB_FILE" "$DEST/registry.db"
  [ -f "$DB_FILE-wal" ] && cp "$DB_FILE-wal" "$DEST/registry.db-wal" || true
  [ -f "$DB_FILE-shm" ] && cp "$DB_FILE-shm" "$DEST/registry.db-shm" || true
fi

# La clave: copia byte a byte, 0600 desde el primer momento (umask + chmod).
cp "$KEY_FILE" "$DEST/registry.db.registry-key"
chmod 600 "$DEST/registry.db.registry-key"
chmod 600 "$DEST/registry.db"

# Manifiesto con huellas (útil para verificar sin abrir el secreto).
if command -v sha256sum >/dev/null 2>&1; then
  ( cd "$DEST" && sha256sum registry.db registry.db.registry-key > SHA256SUMS )
  chmod 600 "$DEST/SHA256SUMS"
fi

echo "Backup creado en: $DEST"
echo "  - registry.db              (base SQLite)"
echo "  - registry.db.registry-key (⚠️ SECRETO: clave privada del registro, 0600)"
echo "Guárdalo cifrado y fuera de cualquier repo. Restauración: RUNBOOK.md."
