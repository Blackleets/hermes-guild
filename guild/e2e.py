"""Cifrado extremo a extremo de entregas GUILD (v0.6) — el «Blindaje».

El registro guarda metadatos; desde v0.6, el CONTENIDO de una entrega
(el payload) puede viajar **cifrado de la clave del autor a la del
dueño**, y el registro solo ve bytes que no puede leer: ciphertext,
nonce, clave efímera pública y MAC. Título y resumen siguen en claro
a propósito — son lo que el dueño lee para decidir; está declarado
en PROTOCOL y no es un descuido.

Construcción (SOLO primitivas de la stdlib: hashlib, hmac, secrets —
sin dependencias, en coherencia con el resto del proyecto). Tiene
nombre propio y honesto, y NO es ChaCha20 ni AES:

    **GUILD-E2E-1 = X25519 + HKDF-SHA256 + HMAC-CTR + Encrypt-then-MAC**

1. El autor genera un par X25519 **efímero por entrega** y calcula el
   secreto compartido con la clave pública de cifrado del dueño
   (`enc_public_key` de su perfil, RFC 7748 — ver guild/identity.py).
2. Del secreto se derivan 64 bytes con **HKDF-SHA256** (RFC 5869),
   salt = nonce, info = "guild-e2e-1": 32 para el flujo y 32 para MAC.
3. **HMAC-CTR**: el bloque i del flujo es
   `HMAC-SHA256(clave_flujo, nonce ‖ i)` con i en 8 bytes big-endian;
   el ciphertext es el texto XOR el flujo. Como la clave es efímera
   por entrega y el nonce es aleatorio de 16 bytes, el flujo jamás
   se reutiliza entre dos entregas.
4. **Encrypt-then-MAC**: `MAC = HMAC-SHA256(clave_mac, dominio ‖
   pública_efímera ‖ nonce ‖ AAD ‖ ciphertext)`, verificado en
   tiempo constante ANTES de descifrar. El AAD liga el cifrado a su
   contexto (conexión y autor): un ciphertext trasplantado a otra
   entrega no verifica.

Límites declarados (también en PROTOCOL): es una construcción con
primitivas estándar implementada en Python puro para no añadir
dependencias — no ha pasado una auditoría externa como la que tiene
libsodium, y quien opere un despliegue serio debe saberlo. La
privada de cifrado del dueño es de larga duración: si un día se
filtra, los ciphertexts históricos guardados en el registro serían
descifrables con ella (el par efímero del autor da secreto por
entrega, no secreto perfecto hacia adelante frente al compromiso
de la clave del receptor). Los metadatos (título, resumen, quién,
cuándo) viajan en claro por diseño.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from . import identity

_INFO = b"guild-e2e-1"
_DOMAIN = b"guild-e2e-1/mac"
NONCE_LEN = 16


class E2EError(Exception):
    """El cifrado/descifrado E2E no verifica o está incompleto."""


# --------------------------------------------------------------------------
# HKDF-SHA256 (RFC 5869): extract + expand, solo con hmac de la stdlib.
# --------------------------------------------------------------------------

def hkdf_sha256(ikm: bytes, salt: bytes | None, info: bytes, length: int) -> bytes:
    if salt is None:
        salt = b"\x00" * hashlib.sha256().digest_size
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    okm, block, counter = b"", b"", 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([counter]),
                         hashlib.sha256).digest()
        okm += block
        counter += 1
    return okm[:length]


def _keystream(key: bytes, nonce: bytes, nbytes: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"),
                        hashlib.sha256).digest()
        counter += 1
    return bytes(out[:nbytes])


def _derive(shared: bytes, nonce: bytes) -> tuple[bytes, bytes]:
    km = hkdf_sha256(shared, nonce, _INFO, 64)
    return km[:32], km[32:]


def encrypt_for(recipient_enc_public_key: str, plaintext: bytes,
                aad: bytes = b"") -> dict:
    """Cifra `plaintext` para la clave pública de cifrado del dueño.
    Devuelve el sobre que guarda el registro (todo en hex):
    ciphertext, nonce, ephemeral_public_key, mac. El autor no
    necesita guardar nada: su clave efímera muere con la llamada."""
    if not recipient_enc_public_key:
        raise E2EError("el dueño no tiene clave de cifrado X25519 "
                       "publicada (enc_public_key vacía)")
    eph = identity.generate_enc_keypair()
    try:
        shared = identity.x25519_shared(eph["private_key"],
                                        recipient_enc_public_key)
    except ValueError as exc:
        raise E2EError(f"intercambio X25519 rechazado: {exc}") from exc
    nonce = secrets.token_bytes(NONCE_LEN)
    enc_key, mac_key = _derive(shared, nonce)
    stream = _keystream(enc_key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
    mac = hmac.new(mac_key,
                   _DOMAIN + bytes.fromhex(eph["public_key"]) + nonce
                   + aad + ciphertext,
                   hashlib.sha256).hexdigest()
    return {"ciphertext": ciphertext.hex(), "nonce": nonce.hex(),
            "ephemeral_public_key": eph["public_key"], "mac": mac}


def decrypt_with(recipient_enc_private_key: str, record: dict,
                 aad: bytes = b"") -> bytes:
    """Descifra un sobre de encrypt_for con la privada del dueño.
    Verifica el MAC (Encrypt-then-MAC) ANTES de descifrar: cualquier
    manipulación — un byte del ciphertext, otro receptor, otro
    contexto — lanza E2EError sin devolver ni un byte de texto."""
    if not recipient_enc_private_key:
        raise E2EError("este cliente no tiene clave privada de cifrado")
    try:
        ciphertext = bytes.fromhex(record["ciphertext"])
        nonce = bytes.fromhex(record["nonce"])
        eph_pub = bytes.fromhex(record["ephemeral_public_key"])
        mac_hex = str(record["mac"])
    except (KeyError, TypeError, ValueError) as exc:
        raise E2EError(f"sobre de entrega cifrada incompleto o corrupto: {exc}") from exc
    try:
        shared = identity.x25519_shared(recipient_enc_private_key,
                                        eph_pub.hex())
    except ValueError as exc:
        raise E2EError(f"intercambio X25519 rechazado: {exc}") from exc
    enc_key, mac_key = _derive(shared, nonce)
    expected = hmac.new(mac_key, _DOMAIN + eph_pub + nonce + aad + ciphertext,
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, mac_hex):
        raise E2EError("MAC inválido: el contenido cifrado fue manipulado, "
                       "no es para esta clave o no es de este contexto")
    stream = _keystream(enc_key, nonce, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, stream))
