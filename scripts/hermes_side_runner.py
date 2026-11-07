#!/usr/bin/env python3
"""Lado Hermes de la prueba real de GUILD (nació en v0.5.0).

Este script NO se ejecuta con el Python de GUILD: lo lanza
scripts/demo_hermes_real.py con el intérprete del entorno real de
Hermes (el venv que PM provisiona para el checkout) porque importa
hermes_cli de verdad:

  1. Lee el manifiesto plugin.yaml con parse_manifest_file (el parser
     real de Hermes) y aplica la puerta requires_hermes.
  2. Carga el plugin con PluginManager._load_plugin — el mismo camino
     que usa la discovery real — sobre una COPIA del plugin en un
     directorio temporal (el checkout de Hermes no se toca).
  3. Según --phase, ejercita el comando /guild a través del handler
     registrado en el manager, despacha tools vía PluginContext
     (ctx.dispatch_tool, la API real del ctx) e invoca el hook
     on_session_start vía manager.invoke_hook.

Salida: líneas legibles + una línea final «RESULT {json}» por fase
para que el driver verifique sin adivinar.
Variables de entorno (las fija el driver): HERMES_HOME (temporal),
GUILD_DATA_DIR (temporal, compartido con el servidor GUILD).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

PLUGIN_FILES = ["__init__.py", "commands.py", "hooks.py", "tools.py",
                "schemas.py", "plugin.yaml"]
PLUGIN_DIRS = ["guild", "skills"]


def copy_plugin(src: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for name in PLUGIN_FILES:
        shutil.copy2(src / name, dst / name)
    for name in PLUGIN_DIRS:
        shutil.copytree(src / name, dst / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dst


def latest_connection_id(db_file: Path, requester_id: str) -> str | None:
    if not db_file.exists():
        return None
    conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT id FROM connections WHERE requester_id = ? "
            "ORDER BY created_at DESC LIMIT 1", (requester_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkout", required=True)
    ap.add_argument("--plugin-src", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--phase", required=True,
                    choices=["load", "act1", "act2", "act3"])
    ap.add_argument("--post-id", default="")
    ap.add_argument("--conn-id", default="")
    args = ap.parse_args()

    workdir = Path(args.workdir)
    os.environ.setdefault("HERMES_HOME", str(workdir / "hermes-home"))
    os.environ.setdefault("GUILD_DATA_DIR", str(workdir / "guild-data"))
    Path(os.environ["HERMES_HOME"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["GUILD_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

    plugin_copy = copy_plugin(Path(args.plugin_src), workdir / "plugin-copy")

    sys.path.insert(0, args.checkout)
    from hermes_cli.plugins import PluginContext, PluginManager
    from hermes_cli.plugins_manifest import (parse_manifest_file,
                                             requires_hermes_error)

    manifest = parse_manifest_file(plugin_copy / "plugin.yaml",
                                   plugin_copy, "user", "")
    gate = requires_hermes_error(manifest)
    print(f"[runner] manifiesto: {manifest.name} v{manifest.version} · "
          f"requires_hermes={manifest.requires_hermes} · puerta: {gate!r}")

    mgr = PluginManager(scope_key=os.environ["HERMES_HOME"])
    mgr._load_plugin(manifest)
    loaded = list(mgr._plugins.values())
    assert len(loaded) == 1, f"plugins cargados inesperados: {list(mgr._plugins)}"
    plugin = loaded[0]

    result: dict = {
        "phase": args.phase,
        "manifest": {"name": manifest.name, "version": manifest.version},
        "requires_hermes_error": gate,
        "load_error": plugin.error,
        "enabled": plugin.enabled,
        "tools": plugin.tools_registered,
        "hooks": plugin.hooks_registered,
        "commands": plugin.commands_registered,
        "skills": sorted(mgr._plugin_skills),
    }
    print(f"[runner] cargado: enabled={plugin.enabled} error={plugin.error}")
    print(f"[runner] tools={plugin.tools_registered}")
    print(f"[runner] hooks={plugin.hooks_registered} "
          f"commands={plugin.commands_registered} skills={result['skills']}")

    handler = mgr._plugin_commands["guild"]["handler"]
    ctx = PluginContext(manifest, mgr)

    def show(label: str, text) -> None:
        print(f"--- {label} ---")
        print(text if text is not None else "(sin salida)")
        result.setdefault("outputs", {})[label] = (
            text if isinstance(text, str) else repr(text))

    if args.phase == "load":
        show("tool guild_board (ctx.dispatch_tool)",
             ctx.dispatch_tool("guild_board", {}))
        hooks_result = mgr.invoke_hook("on_session_start")
        show("hook on_session_start (manager.invoke_hook, Marco aún no unido)",
             json.dumps(hooks_result, ensure_ascii=False, default=str))

    elif args.phase == "act1":
        show("/guild join", handler(
            'join @marco "Marco" hermes skills=baseten,python '
            "idiomas=es,de tz=Europe/Berlin"))
        show("/guild board", handler("board"))
        show(f"/guild matches {args.post_id}",
             handler(f"matches {args.post_id}"))
        show("/guild connect", handler(
            f"connect @lee {args.post_id} "
            '"Ya desplegué FASHN v1.5 en Baseten para un piloto: te dejo '
            'el despliegue reproducible y revisamos juntos el 403." '
            'contrato="Despliegue FASHN VTON v1.5 reproducible en Baseten" '
            'hecho="URL pública responde y commit con el truss y el adaptador" '
            "fecha=2026-11-20"))
        state = json.loads((Path(os.environ["GUILD_DATA_DIR"])
                            / "state.json").read_text())
        conn_id = latest_connection_id(
            Path(os.environ["GUILD_DATA_DIR"]) / "guild.db",
            state["profile_id"])
        result["conn_id"] = conn_id
        result["marco_profile_id"] = state["profile_id"]
        print(f"[runner] connection_id={conn_id}")

    elif args.phase == "act2":
        show("/guild deliver", handler(
            f'deliver {args.conn_id} "Despliegue FASHN reproducible" '
            '"Truss y adaptador listos: la URL pública responde y el '
            'commit queda enlazado en el hilo de la conexión."'))

    elif args.phase == "act3":
        show("/guild rate", handler(
            f"rate @lee 5 4 5 {args.conn_id}"))
        show("/guild post", handler(
            'post "Agentes de voz" "Revisar la latencia de mi agente '
            'de voz en producción" skills=python tipo=capacidad'))
        # El hook va ANTES de abrir el inbox a propósito: es lo que
        # pasa en una sesión real (el hook salta al arrancar) y
        # /guild inbox marca los matches como leídos al abrirse.
        hooks_result = mgr.invoke_hook("on_session_start")
        show("hook on_session_start (manager.invoke_hook)",
             json.dumps(hooks_result, ensure_ascii=False, default=str))
        show("/guild status", handler("status"))
        show("/guild inbox", handler("inbox"))
        show("tool guild_status (ctx.dispatch_tool)",
             ctx.dispatch_tool("guild_status", {}))

    print("RESULT " + json.dumps(result, ensure_ascii=False))
    return 0 if plugin.error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
