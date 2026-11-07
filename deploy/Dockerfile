# GUILD — Registro (guild/server.py, SOLO stdlib de Python)
# Artefacto RECOMENDADO para el Día L. Ver RUNBOOK.md.
#
# Contexto de build: la RAÍZ del repo guild-plugin (este Dockerfile vive en
# deploy/, pero se construye desde la raíz para poder copiar el paquete guild/):
#   docker build -f deploy/Dockerfile -t guild-registry:0.6.1 .
#
# Sin dependencias que instalar: el servidor usa únicamente http.server,
# sqlite3 y el resto de la stdlib. Por eso la imagen es la oficial slim y
# no hay paso de pip.
FROM python:3.12-slim

# Usuario sin privilegios: el registro nunca debe correr como root.
RUN groupadd --system guild && useradd --system --gid guild --home-dir /app guild

WORKDIR /app

# Solo el paquete del servidor. Nada de tests, landings ni claves.
COPY guild/ ./guild/

# Directorio de datos: aquí viven, en un VOLUMEN persistente del host,
#   /data/registry.db            -> la base SQLite
#   /data/registry.db.registry-key -> el fichero de clave del registro (0600)
# El entrypoint garantiza directorio y permisos antes de arrancar.
RUN mkdir -p /data && chown guild:guild /data
VOLUME ["/data"]

# La clave del registro vive FUERA de la base. GUILD_REGISTRY_KEY_FILE la
# apunta a un fichero DENTRO del volumen de datos: sobrevive a recrear el
# contenedor y backup.sh lo copia junto a la DB.
ENV GUILD_DB=/data/registry.db \
    GUILD_REGISTRY_KEY_FILE=/data/registry.db.registry-key \
    GUILD_HOST=0.0.0.0 \
    GUILD_PORT=8787 \
    PYTHONUNBUFFERED=1

EXPOSE 8787

# Healthcheck: NO hay endpoint /health dedicado en guild/server.py.
# El endpoint público equivalente es GET /v1/stats (200 + JSON con
# registry_public_key). Se usa urllib de la propia stdlib: la imagen slim
# no trae curl ni wget.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/v1/stats', timeout=4).status==200 else 1)"

USER guild

# entrypoint inline: un fichero de clave preexistente montado con permisos
# laxos se aprieta a 0600 ANTES de arrancar (el servidor RECHAZA un
# GUILD_REGISTRY_KEY_FILE explícito más abierto que 0600, en su primer uso).
# Si el fichero no existe, el servidor lo crea con 0600 desde el primer
# byte (os.open con modo, en registry.py).
ENTRYPOINT ["sh", "-c", "if [ -f \"$GUILD_REGISTRY_KEY_FILE\" ]; then chmod 600 \"$GUILD_REGISTRY_KEY_FILE\"; fi && exec python3 -m guild.server --db \"$GUILD_DB\" --host \"$GUILD_HOST\" --port \"$GUILD_PORT\""]
