"""Transporte del canal GUILD — cómo viaja el aviso de «canal abierto».

El contenido de una colaboración son metadatos en el registro; lo que
necesita transporte es el AVISO a la otra instalación («el dueño
aprobó tu solicitud, el canal está abierto»). Dos implementaciones
tras la misma interfaz:

- **RelayTransport** (por defecto): el relay del propio registro.
  El aviso queda como evento auditable en el registro y la otra
  parte lo ve en su inbox. Siempre disponible, es el suelo de la red.
- **HermesPeerTransport**: si la instalación tiene Hermes con Bot
  Mode (v0.21+), el aviso puede viajar por su mensajería nativa:
  `hermes peer <handle> <mensaje>`. Se detecta el binario con
  `shutil.which`; si no existe, o la llamada falla, **degrada al
  relay sin romper el flujo** y el resultado lo registra.

Selección por configuración: `transport: auto|relay|peer`
(`auto` = peer si el binario existe, relay si no).

Honestidad de la implementación de referencia: la invocación de
`hermes peer` se modela según la documentación de orquestación de
Hermes y la cobertura de la v0.21; está probada con un doble del
binario, pendiente de prueba contra un Hermes real con Bot Mode.
"""
from __future__ import annotations

import shutil
import subprocess

SETTINGS = ("auto", "relay", "peer")


class RelayTransport:
    """El relay del registro: el aviso queda en el registro (evento)
    y en el inbox del destinatario. No necesita nada externo."""
    name = "relay"

    def available(self) -> bool:
        return True

    def notify(self, handle: str, message: str) -> dict:
        return {"transport": self.name, "delivered": True,
                "detail": "aviso en el relay del registro (evento + inbox "
                          "del destinatario)"}


class HermesPeerTransport:
    """Mensajería nativa de Hermes (`hermes peer`) cuando existe."""
    name = "peer"

    def __init__(self, binary: str | None = None):
        # binary explícito para tests; si no, se detecta en el PATH.
        self.binary = binary if binary is not None else shutil.which("hermes")

    def available(self) -> bool:
        return bool(self.binary)

    def notify(self, handle: str, message: str) -> dict:
        if not self.binary:
            return {"transport": self.name, "delivered": False,
                    "detail": "binario `hermes` no encontrado en el PATH"}
        try:
            proc = subprocess.run([self.binary, "peer", handle, message],
                                  capture_output=True, text=True, timeout=15)
        except Exception as exc:  # timeout, permisos, lo que sea
            return {"transport": self.name, "delivered": False,
                    "detail": f"`hermes peer` no se pudo ejecutar: {exc}"}
        if proc.returncode != 0:
            return {"transport": self.name, "delivered": False,
                    "detail": f"`hermes peer` salió con código {proc.returncode}: "
                              f"{(proc.stderr or '').strip()[:200]}"}
        return {"transport": self.name, "delivered": True,
                "detail": f"aviso enviado con `hermes peer` a @{handle}"}


def get_transport(setting: str = "auto"):
    """La implementación que toca según la configuración."""
    setting = (setting or "auto").lower()
    if setting == "relay":
        return RelayTransport()
    peer = HermesPeerTransport()
    if setting == "peer":
        return peer
    return peer if peer.available() else RelayTransport()  # auto


def notify_channel_open(connection: dict, requester_handle: str,
                        registry=None, setting: str = "auto") -> dict:
    """Avisa al solicitante de que su canal está abierto.

    Nunca lanza: si el transporte elegido falla (p. ej. `hermes peer`
    devuelve error), degrada al relay y el resultado lo dice. Si se
    pasa el registro, el aviso queda como evento auditable."""
    message = (f"⚔️ GUILD: canal abierto — el dueño aprobó tu solicitud "
               f"de conexión {connection['id']}"
               + (f" (necesidad {connection['post_id']})"
                  if connection.get("post_id") else "")
               + ". A colaborar: las entregas se proponen, el dueño decide.")
    transport = get_transport(setting)
    result = transport.notify(requester_handle, message)
    result = {**result, "fallback": False}
    if not result["delivered"] and transport.name == "peer":
        relay_detail = result["detail"]
        result = RelayTransport().notify(requester_handle, message)
        result = {**result, "fallback": True,
                  "detail": f"peer no disponible ({relay_detail}); "
                            + result["detail"]}
    if registry is not None:
        try:
            registry.log_event(
                connection["requester_id"], "channel_notified",
                f"conexión {connection['id']} · transporte {result['transport']}"
                + (" · con degradación al relay" if result["fallback"] else ""))
        except Exception:
            pass  # el aviso jamás rompe el flujo por un fallo de log
    return result
