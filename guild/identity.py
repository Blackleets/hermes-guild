"""Identidad GUILD — Ed25519 real (RFC 8032) en Python puro, solo stdlib.

Dos capas, honestas sobre lo que son:

1. **API key** — secreto aleatorio para autenticarse contra el registro
   (`Authorization: Bearer …`). El registro guarda solo su hash SHA-256.

2. **Ed25519 (la identidad de firma)** — cada instalación genera un par
   de claves Ed25519 de verdad, implementado aquí según RFC 8032 con
   aritmética de curva en Python puro (sin dependencias: solo hashlib).
   - La clave privada es una semilla de 32 bytes que NUNCA sale de la
     instalación: el cliente la guarda y firma localmente.
   - La clave pública (32 bytes) viaja en el perfil y cualquiera puede
     verificar firmas con ella — el registro verifica la firma de cada
     entrega antes de guardarla, y el dueño la re-verifica antes de
     aceptarla. Si el contenido cambia, la verificación falla.
   - Rendimiento: la aritmética en coordenadas extendidas firma y
     verifica en milisegundos; de sobra para metadatos de registro.

Compatibilidad/degradación (v0.1 → v0.2): la v1 local firmaba con
HMAC-SHA256 (la «privada» era también el secreto de verificación, así
que no era firma asimétrica real). Ese esquema queda como
`sign_hmac_legacy` / `verify_hmac_legacy`, SOLO para leer datos
antiguos en modo local; todo lo nuevo se firma con Ed25519. Las claves
generadas por `generate_keypair` son semillas Ed25519 desde v0.2.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

# --------------------------------------------------------------------------
# API key (autenticación contra el registro)
# --------------------------------------------------------------------------

def generate_api_key() -> str:
    return "guild_" + secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def check_api_key(api_key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(api_key), stored_hash)


# --------------------------------------------------------------------------
# Ed25519 (RFC 8032) — curva: -x² + y² = 1 + d·x²·y²  sobre GF(2^255 - 19)
# Puntos en coordenadas extendidas (X, Y, T, Z) con x=X/Z, y=Y/Z, T=XY/Z.
# --------------------------------------------------------------------------

_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _Q - 2, _Q)) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)  # sqrt(-1) mod q


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _Q - 2, _Q) % _Q
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = x * _I % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_BY = 4 * pow(5, _Q - 2, _Q) % _Q
_BX = _xrecover(_BY)
_B = (_BX, _BY, _BX * _BY % _Q, 1)  # punto base en extendidas
_IDENTITY_PT = (0, 1, 0, 1)


def _pt_add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _Q
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _Q
    C = 2 * _D * P[2] * Q[2] % _Q
    D = 2 * P[3] * Q[3] % _Q
    E, F, G, H = (B - A) % _Q, (D - C) % _Q, (D + C) % _Q, (B + A) % _Q
    return (E * F % _Q, G * H % _Q, E * H % _Q, F * G % _Q)


def _pt_double(P):
    A = P[0] * P[0] % _Q
    B = P[1] * P[1] % _Q
    C = 2 * P[3] * P[3] % _Q
    D = (-A) % _Q
    E = ((P[0] + P[1]) * (P[0] + P[1]) - A - B) % _Q
    G, F, H = (D + B) % _Q, (D + B - C) % _Q, (D - B) % _Q
    return (E * F % _Q, G * H % _Q, E * H % _Q, F * G % _Q)


def _scalarmult(P, e: int):
    Q = _IDENTITY_PT
    while e > 0:
        if e & 1:
            Q = _pt_add(Q, P)
        P = _pt_double(P)
        e >>= 1
    return Q


def _pt_encode(P) -> bytes:
    zinv = pow(P[3], _Q - 2, _Q)
    x, y = P[0] * zinv % _Q, P[1] * zinv % _Q
    bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))


def _pt_decode(data: bytes):
    if len(data) != 32:
        raise ValueError("punto Ed25519 debe ser 32 bytes")
    y = int.from_bytes(data, "little") & ((1 << 255) - 1)
    sign = (data[31] >> 7) & 1
    if y >= _Q:
        raise ValueError("y fuera de rango")
    x = _xrecover(y)
    if (x & 1) != sign:
        x = _Q - x
    return (x, y, x * y % _Q, 1)


def _pt_equal(P, Q) -> bool:
    return ((P[0] * Q[3] - Q[0] * P[3]) % _Q == 0
            and (P[1] * Q[3] - Q[1] * P[3]) % _Q == 0)


def _clamp(h32: bytes) -> int:
    a = int.from_bytes(h32, "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a


# --------------------------------------------------------------------------
# Par de claves y firma (API pública del módulo)
# --------------------------------------------------------------------------

def generate_keypair() -> dict:
    """Nuevo par Ed25519. private_key = semilla de 32B en hex (no sale
    nunca de la instalación); public_key = 32B en hex, va en el perfil."""
    seed = secrets.token_bytes(32)
    return {"private_key": seed.hex(), "public_key": public_key_of(seed.hex())}


def public_key_of(private_key: str) -> str:
    seed = bytes.fromhex(private_key)
    h = hashlib.sha512(seed).digest()
    A = _scalarmult(_B, _clamp(h[:32]))
    return _pt_encode(A).hex()


def fingerprint(public_key: str) -> str:
    return public_key[:16]


def sign(private_key: str, message: str) -> str:
    """Firma Ed25519 del mensaje (str) → firma de 64B en hex."""
    seed = bytes.fromhex(private_key)
    h = hashlib.sha512(seed).digest()
    a = _clamp(h[:32])
    pk = _pt_encode(_scalarmult(_B, a))
    msg = message.encode()
    r = int.from_bytes(hashlib.sha512(h[32:] + msg).digest(), "little") % _L
    R = _pt_encode(_scalarmult(_B, r))
    k = int.from_bytes(hashlib.sha512(R + pk + msg).digest(), "little") % _L
    S = (r + k * a) % _L
    return (R + S.to_bytes(32, "little")).hex()


def verify(public_key: str, message: str, signature: str) -> bool:
    """Verificación asimétrica real: solo necesita la clave pública."""
    try:
        sig = bytes.fromhex(signature)
        if len(sig) != 64:
            return False
        R = _pt_decode(sig[:32])
        A = _pt_decode(bytes.fromhex(public_key))
        S = int.from_bytes(sig[32:], "little")
        if S >= _L:
            return False
        k = int.from_bytes(
            hashlib.sha512(sig[:32] + bytes.fromhex(public_key)
                           + message.encode()).digest(), "little") % _L
        return _pt_equal(_scalarmult(_B, S), _pt_add(R, _scalarmult(A, k)))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# X25519 (RFC 7748) — intercambio de claves para el cifrado E2E (v0.6).
# Curve25519 en forma de Montgomery: v² = u³ + 486662·u² + u sobre el
# MISMO campo GF(2^255 - 19) de Ed25519 (constante _Q de arriba), con
# la escalera de Montgomery y el clamp de la RFC. Python puro, solo
# hashlib/secrets como el resto del módulo.
#
# Validación: el vector de clave de Alice de RFC 7748 §6.1
# (X25519(privada_alice, punto base) = pública_alice) se comprueba
# byte a byte en la suite. El secreto compartido de ese mismo ejemplo
# NO se usa como vector (no pudo reproducirse con certeza al
# implementarlo): la simetría DH se valida por roundtrip con claves
# generadas (ambos lados derivan el mismo secreto; un tercero, no).
# --------------------------------------------------------------------------

_A24 = 121665  # (486662 - 2) / 4


def _clamp25519(k: bytearray) -> int:
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    return int.from_bytes(k, "little")


def x25519(scalar: bytes, u_coordinate: bytes) -> bytes:
    """X25519 de RFC 7748: escalar de 32B × coordenada u de 32B → 32B.
    Devuelve 32 bytes en cero si el resultado es el punto de orden
    bajo (entrada no contributiva): quien llama debe rechazarlo."""
    if len(scalar) != 32 or len(u_coordinate) != 32:
        raise ValueError("X25519 opera con valores de 32 bytes")
    k = _clamp25519(bytearray(scalar))
    x1 = int.from_bytes(u_coordinate, "little") & ((1 << 255) - 1)
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in range(254, -1, -1):
        bit = (k >> t) & 1
        swap ^= bit
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = bit
        a = (x2 + z2) % _Q
        aa = a * a % _Q
        b = (x2 - z2) % _Q
        bb = b * b % _Q
        e = (aa - bb) % _Q
        c = (x3 + z3) % _Q
        d = (x3 - z3) % _Q
        da = d * a % _Q
        cb = c * b % _Q
        x3 = (da + cb) * (da + cb) % _Q
        z3 = x1 * ((da - cb) * (da - cb) % _Q) % _Q
        x2 = aa * bb % _Q
        z2 = e * (aa + _A24 * e) % _Q
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    return (x2 * pow(z2, _Q - 2, _Q) % _Q).to_bytes(32, "little")


def generate_enc_keypair() -> dict:
    """Par X25519 para CIFRADO (v0.6): distinto del par Ed25519 de
    firma. private_key = 32B aleatorios en hex (nunca sale del
    cliente); public_key = X25519(privada, punto base) en hex, y es
    la que se publica en el perfil como `enc_public_key`."""
    priv = secrets.token_bytes(32)
    pub = x25519(priv, (9).to_bytes(32, "little"))
    return {"private_key": priv.hex(), "public_key": pub.hex()}


def enc_public_of(private_key: str) -> str:
    return x25519(bytes.fromhex(private_key),
                  (9).to_bytes(32, "little")).hex()


def x25519_shared(private_key: str, peer_public_key: str) -> bytes:
    """Secreto compartido crudo de 32B. Lanza ValueError si el
    resultado es todo ceros (clave pública de orden bajo: intercambio
    no contributivo, hay que rechazarlo)."""
    shared = x25519(bytes.fromhex(private_key), bytes.fromhex(peer_public_key))
    if shared == b"\x00" * 32:
        raise ValueError("intercambio X25519 no contributivo (secreto nulo)")
    return shared


# --------------------------------------------------------------------------
# LEGACY v0.1 (HMAC) — solo lectura de datos antiguos en modo local.
# No usar para firmar nada nuevo: no es asimétrico (quien verifica
# necesita el secreto). Se mantiene documentado por compatibilidad.
# --------------------------------------------------------------------------

def sign_hmac_legacy(private_key: str, message: str) -> str:
    return hmac.new(bytes.fromhex(private_key), message.encode(),
                    hashlib.sha256).hexdigest()


def verify_hmac_legacy(private_key: str, message: str, signature: str) -> bool:
    return hmac.compare_digest(sign_hmac_legacy(private_key, message), signature)
