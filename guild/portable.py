"""Reputación portable firmada de GUILD (v0.3).

El foso: la reputación que un builder gana colaborando no debe quedar
encerrada en un registro. Este módulo define el **export portable**:
un JSON con el handle, la reputación dimensional, el nº de
colaboraciones y las habilidades verificadas de un perfil, **firmado
con la clave Ed25519 del REGISTRO** (la autoridad que computó esos
datos — firmarlo con la clave del propio perfil no probaría nada:
cualquiera se firmaría un 5.0).

Diseño de la firma:
- El registro genera UN par Ed25519 propio y guarda la privada FUERA
  de la base (v0.6): en un fichero con permisos 0600 junto a la DB, o
  donde apunten `GUILD_REGISTRY_KEY_FILE` / `GUILD_REGISTRY_PRIVATE_KEY`.
  Las bases antiguas que la llevaban dentro se migran solas (la clave
  no cambia). La pública se publica en `GET /v1/stats` para que
  cualquiera la contraste, y la rotación es una operación explícita
  del operador (los exports viejos solo verifican contra la clave
  antigua que llevan declarada).
- La firma cubre la **forma canónica** del payload (JSON con claves
  ordenadas, sin la propia firma): cualquier cambio en cualquier campo
  — una nota, una habilidad, un handle — invalida la firma.
- **Verificar es independiente del registro**: `verify_export` solo
  necesita el JSON y, para una verificación con confianza, la clave
  pública del registro obtenida por un canal fiable (la `trusted_key`
  fijada por quien verifica). Sin `trusted_key`, la función comprueba
  que la firma es internamente consistente, pero avisa de que la
  clave no está contrastada — un atacante podría autofirmarse un
  export con su propia clave y pasaría esa comprobación débil. La
  honestidad aquí es parte del diseño, no una nota al pie.
"""
from __future__ import annotations

import json

from . import identity

EXPORT_FORMAT = "guild-reputation/v1"

# Campos que firma el registro (todo el export menos la firma misma).
SIGNED_FIELDS = ("format", "handle", "display_name", "platform",
                 "reputation", "collaborations", "verified_skills",
                 "registry_public_key", "issued_at")


def canonical_payload(export: dict) -> str:
    """Forma canónica que se firma: solo los campos firmados, JSON con
    claves ordenadas y separadores fijos. Determinista entre máquinas."""
    payload = {k: export.get(k) for k in SIGNED_FIELDS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def sign_export(export: dict, registry_private_key: str) -> dict:
    """Devuelve una copia del export con su firma Ed25519 del registro."""
    out = dict(export)
    out["signature"] = identity.sign(registry_private_key, canonical_payload(out))
    return out


def verify_export(export: dict, trusted_registry_key: str | None = None) -> dict:
    """Verificación que cualquiera puede correr, sin el registro.

    - `signature_valid`: la firma Ed25519 corresponde al contenido y a
      la clave pública que el propio export declara.
    - `key_trusted`: solo True si se pasó `trusted_registry_key` (la
      pública del registro, obtenida por un canal fiable — p. ej. el
      `/v1/stats` del registro real) y coincide con la del export.
    - `valid`: firma válida Y (sin clave fijada → comprobación débil,
      `key_trusted=None`) — el llamante decide qué nivel exige. Para
      aceptar una reputación como prueba, exigir `key_trusted is True`.
    """
    if not isinstance(export, dict) or export.get("format") != EXPORT_FORMAT:
        return {"valid": False, "signature_valid": False, "key_trusted": None,
                "error": "formato no reconocido (se esperaba guild-reputation/v1)"}
    sig = export.get("signature") or ""
    pub = export.get("registry_public_key") or ""
    if not sig or not pub:
        return {"valid": False, "signature_valid": False, "key_trusted": None,
                "error": "export sin firma o sin clave pública del registro"}
    sig_ok = identity.verify(pub, canonical_payload(export), sig)
    if trusted_registry_key is None:
        key_trusted = None
    else:
        key_trusted = pub == str(trusted_registry_key).strip().lower()
    return {"valid": bool(sig_ok and key_trusted is not False),
            "signature_valid": bool(sig_ok), "key_trusted": key_trusted,
            "handle": export.get("handle"), "error": None}
