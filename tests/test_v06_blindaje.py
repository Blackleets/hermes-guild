"""GUILD v0.6.0 «Blindaje» — tests de ataque.

Tres frentes, y los tests están escritos como ataques, no como
trámites:

1. E2E: el texto en claro NO aparece ni en la base SQLite ni en
   ninguna respuesta del servidor (escaneo literal de bytes y de
   JSON); un byte manipulado del ciphertext → MAC inválido y
   descifrado rechazado; la clave de un tercero no descifra; el
   roundtrip autor→dueño funciona por la vía HTTP completa; y las
   entregas de solo metadatos (flujo v0.5) siguen funcionando.
2. La clave privada del registro NO está en la base: vive en un
   fichero 0600, migra sola desde las bases antiguas (sin cambiar
   la clave: los exports viejos siguen verificando) y rota con una
   operación explícita.
3. /guild deliver firma de verdad con la clave local (fichero 0600
   creado al unirse), /guild keys forget la borra, y sin clave el
   comando entrega pero AVISANDO de que va sin firmar.

Las primitivas se validan así (declarado con honestidad en
PROTOCOL): X25519 contra el vector de clave de Alice de RFC 7748
§6.1 reproducido byte a byte; HKDF-SHA256 implementado según
RFC 5869 y validado por propiedades (el vector oficial no se
reprodujo con certeza al implementar, no se finge); la simetría DH
por roundtrip con claves generadas.
"""
from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

import pytest

from guild import e2e, identity
from guild.client import GuildClient
from guild.portable import verify_export
from guild.registry import GuildError, Registry
from guild.server import make_server

SECRETO = "CONTENIDO-E2E-SECRETO-7f3a :: la receta manuscrita del truss"


# ------------------------------------------------------------ primitivas
def test_x25519_vector_rfc7748_alice():
    """Vector oficial RFC 7748 §6.1: X25519(privada de Alice, base)
    = pública de Alice, byte a byte."""
    alice_priv = bytes.fromhex(
        "77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
    assert identity.x25519(alice_priv, (9).to_bytes(32, "little")).hex() == (
        "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a")


def test_x25519_dh_simetrico_y_tercero_no():
    a = identity.generate_enc_keypair()
    b = identity.generate_enc_keypair()
    c = identity.generate_enc_keypair()
    sab = identity.x25519_shared(a["private_key"], b["public_key"])
    assert sab == identity.x25519_shared(b["private_key"], a["public_key"])
    assert identity.x25519_shared(a["private_key"], c["public_key"]) != sab


def test_hkdf_propiedades():
    a = e2e.hkdf_sha256(b"ikm", b"salt", b"info", 64)
    assert a == e2e.hkdf_sha256(b"ikm", b"salt", b"info", 64)
    assert len(a) == 64
    assert a != e2e.hkdf_sha256(b"ikm", b"salt", b"otro-info", 64)
    assert a != e2e.hkdf_sha256(b"otro-ikm", b"salt", b"info", 64)
    assert a[:42] == e2e.hkdf_sha256(b"ikm", b"salt", b"info", 42)


def test_e2e_unidad_y_aad_liga_el_contexto():
    dueño = identity.generate_enc_keypair()
    sobre = e2e.encrypt_for(dueño["public_key"], "hola".encode(), aad=b"ctx1")
    assert e2e.decrypt_with(dueño["private_key"], sobre, aad=b"ctx1") == b"hola"
    with pytest.raises(e2e.E2EError):
        e2e.decrypt_with(dueño["private_key"], sobre, aad=b"otro-contexto")


# ------------------------------------------------------------- red local
@pytest.fixture()
def reg(tmp_path):
    r = Registry(tmp_path / "t.db")
    yield r
    r.close()


def _pareja_local(reg):
    lee = GuildClient(registry=reg)
    lee.join("lee", "Lee", "Muse", skills_offered=["python"], languages=["es"])
    marco = GuildClient(registry=reg)
    marco.join("marco", "Marco", "hermes", skills_offered=["baseten"],
               languages=["es"])
    post = lee.post_need("La Asistenta", "Desplegar FASHN en Baseten",
                         ["baseten"], need_type="experiencia")
    conn = marco.connect(lee.profile_id, post["id"], "puedo ayudarte")
    lee.approve_connection(conn["id"], True)
    return lee, marco, conn["id"]


def test_e2e_local_roundtrip_y_claro_ausente_de_la_base(reg, tmp_path):
    lee, marco, cid = _pareja_local(reg)
    d = marco.deliver(cid, "Truss verificado", summary="resumen en claro",
                      payload=SECRETO)
    assert d["encrypted"] is True
    assert d["payload_ref"].startswith("e2e:")
    assert reg.verify_delivery(d["id"])["valid"] is True
    # El dueño descifra en SU cliente; el texto coincide byte a byte.
    assert lee.decrypt_delivery(d) == SECRETO.encode()
    # ATAQUE (a, local): el claro no está en la base ni en respuestas.
    assert SECRETO.encode() not in (tmp_path / "t.db").read_bytes()
    assert SECRETO not in json.dumps(reg.get_delivery(d["id"]))
    assert SECRETO not in json.dumps(reg.inbox(lee.profile_id))


def test_e2e_manipulacion_rechazada(reg):
    lee, marco, cid = _pareja_local(reg)
    d = marco.deliver(cid, "Truss", payload=SECRETO)
    # ATAQUE (b1): un byte del ciphertext cambiado en la propia base.
    ct = d["enc_ciphertext"]
    tocado = ("0" if ct[0] != "0" else "1") + ct[1:]
    reg.db.execute("UPDATE deliveries SET enc_ciphertext=? WHERE id=?",
                   (tocado, d["id"]))
    reg.db.commit()
    with pytest.raises(GuildError, match="MAC"):
        lee.decrypt_delivery(reg.get_delivery(d["id"]))
    # ATAQUE (b2): un byte del MAC cambiado.
    d2 = marco.deliver(cid, "Truss 2", payload=SECRETO)
    mac = d2["enc_mac"]
    reg.db.execute("UPDATE deliveries SET enc_mac=? WHERE id=?",
                   (("0" if mac[0] != "0" else "1") + mac[1:], d2["id"]))
    reg.db.commit()
    with pytest.raises(GuildError, match="MAC"):
        lee.decrypt_delivery(reg.get_delivery(d2["id"]))


def test_e2e_tercero_y_autor_no_descifran(reg):
    lee, marco, cid = _pareja_local(reg)
    ana = GuildClient(registry=reg)
    ana.join("ana", "Ana", "openclaw", skills_offered=["diseno"],
             languages=["es"])
    d = marco.deliver(cid, "Truss", payload=SECRETO)
    # ATAQUE (c): ni una tercera con su propia clave, ni el AUTOR
    # (que cifró pero no tiene la privada del dueño) pueden leerlo.
    with pytest.raises(GuildError):
        ana.decrypt_delivery(d)
    with pytest.raises(GuildError):
        marco.decrypt_delivery(d)


def test_e2e_dueño_sin_clave_publicada_no_recibe_cifrado(reg):
    lee, marco, cid = _pareja_local(reg)
    # Perfil heredado (pre-v0.6): sin enc_public_key no hay cifrado.
    reg.db.execute("UPDATE profiles SET enc_public_key='' WHERE id=?",
                   (lee.profile_id,))
    reg.db.commit()
    with pytest.raises(GuildError, match="no tiene clave de cifrado"):
        marco.deliver(cid, "Truss", payload=SECRETO)


def test_entrega_solo_metadatos_sigue_funcionando(reg):
    """(e) El flujo v0.5 no se toca: sin payload, entrega clásica."""
    lee, marco, cid = _pareja_local(reg)
    d = marco.deliver(cid, "Informe", summary="solo metadatos")
    assert d["encrypted"] is False
    assert reg.verify_delivery(d["id"])["valid"] is True
    lee.decide_delivery(d["id"], accept=True)
    assert reg.get_delivery(d["id"])["status"] == "accepted"


# ------------------------------------------------------------ red por HTTP
@pytest.fixture()
def net(tmp_path):
    db = tmp_path / "net.db"
    server = make_server(str(db), "127.0.0.1", 0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", db
    server.shutdown()


def _pareja_http(base):
    lee = GuildClient(base_url=base)
    lee.join("lee", "Lee", "Muse", skills_offered=["python"], languages=["es"])
    marco = GuildClient(base_url=base)
    marco.join("marco", "Marco", "hermes", skills_offered=["baseten"],
               languages=["es"])
    post = lee.post_need("La Asistenta", "Desplegar FASHN en Baseten",
                         ["baseten"], need_type="experiencia")
    conn = marco.connect(lee.profile_id, post["id"], "puedo ayudarte")
    lee.approve_connection(conn["id"], True)
    return lee, marco, conn["id"]


def test_e2e_http_roundtrip_y_claro_ausente_en_todo(net):
    base, db = net
    lee, marco, cid = _pareja_http(base)
    d = marco.deliver(cid, "Truss verificado", summary="resumen en claro",
                      payload=SECRETO)
    assert d["encrypted"] is True
    # ATAQUE (a, HTTP): el claro no aparece en NINGUNA respuesta del
    # servidor ni en los bytes de la base del registro.
    assert SECRETO not in json.dumps(d)
    recuperada = lee.get_delivery(d["id"])
    assert SECRETO not in json.dumps(recuperada)
    assert SECRETO.encode() not in db.read_bytes()
    # (d) Roundtrip completo por HTTP: el dueño descifra en local.
    assert lee.decrypt_delivery(recuperada) == SECRETO.encode()
    assert lee.verify_delivery(d["id"])["valid"] is True
    # Un tercero ni siquiera puede LEER la entrega por la API.
    ana = GuildClient(base_url=base)
    ana.join("ana", "Ana", "openclaw", languages=["es"])
    with pytest.raises(GuildError, match="403"):
        ana.get_delivery(d["id"])


# --------------------------------------------- clave del registro (pieza 2)
@pytest.fixture(autouse=True)
def _sin_env_de_clave(monkeypatch):
    monkeypatch.delenv("GUILD_REGISTRY_KEY_FILE", raising=False)
    monkeypatch.delenv("GUILD_REGISTRY_PRIVATE_KEY", raising=False)


def test_clave_del_registro_vive_fuera_de_la_base(tmp_path):
    db = tmp_path / "r.db"
    reg = Registry(db)
    kp = reg.registry_keypair()
    prof = reg.create_profile("lee", "Lee", platform="Muse")
    reg.export_reputation(prof["id"])  # operar firmando de verdad
    reg.close()
    fichero = Path(str(db) + ".registry-key")
    assert fichero.exists()
    assert stat.S_IMODE(fichero.stat().st_mode) == 0o600
    assert fichero.read_text().strip() == kp["private_key"]
    # La privada NO está en la base: ni en los bytes ni en la tabla.
    assert kp["private_key"].encode() not in db.read_bytes()
    reg2 = Registry(db)
    filas = reg2.db.execute(
        "SELECT COUNT(*) AS n FROM registry_meta WHERE key='signing_keypair'"
    ).fetchone()["n"]
    assert filas == 0
    # Y la clave es la MISMA tras reabrir (del fichero, no regenerada).
    assert reg2.registry_keypair()["public_key"] == kp["public_key"]
    reg2.close()


def test_migracion_desde_base_antigua_conserva_la_clave(tmp_path):
    db = tmp_path / "legacy.db"
    kp_vieja = identity.generate_keypair()
    reg = Registry(db)
    # Base heredada ≤v0.5: el par vive DENTRO de registry_meta.
    reg.db.execute(
        "INSERT INTO registry_meta(key,value) VALUES('signing_keypair',?)",
        (json.dumps(kp_vieja),))
    reg.db.commit()
    prof = reg.create_profile("lee", "Lee", platform="Muse")
    # El primer uso que necesita la clave dispara la migración.
    export = reg.export_reputation(prof["id"])
    assert reg.registry_keypair()["public_key"] == kp_vieja["public_key"]
    assert reg.db.execute(
        "SELECT COUNT(*) AS n FROM registry_meta WHERE key='signing_keypair'"
    ).fetchone()["n"] == 0
    fichero = Path(str(db) + ".registry-key")
    assert stat.S_IMODE(fichero.stat().st_mode) == 0o600
    assert kp_vieja["private_key"].encode() not in db.read_bytes()
    # Los exports firmados con la clave migrada verifican FUERTE.
    res = verify_export(export, trusted_registry_key=kp_vieja["public_key"])
    assert res["signature_valid"] is True and res["key_trusted"] is True
    kinds = {r["kind"] for r in reg.db.execute(
        "SELECT kind FROM events WHERE kind='registry_key_migrated'")}
    assert kinds == {"registry_key_migrated"}
    reg.close()


def test_fichero_explicito_exige_0600(tmp_path, monkeypatch):
    kp = identity.generate_keypair()
    fichero = tmp_path / "clave-operador.key"
    fichero.write_text(kp["private_key"] + "\n")
    fichero.chmod(0o644)
    monkeypatch.setenv("GUILD_REGISTRY_KEY_FILE", str(fichero))
    reg = Registry(tmp_path / "x.db")
    with pytest.raises(GuildError, match="0600"):
        reg.registry_keypair()
    fichero.chmod(0o600)
    assert reg.registry_keypair()["public_key"] == kp["public_key"]
    reg.close()


def test_rotacion_de_la_clave_del_registro(tmp_path):
    reg = Registry(tmp_path / "rot.db")
    prof = reg.create_profile("lee", "Lee", platform="Muse")
    antes = reg.export_reputation(prof["id"])
    pub_vieja = antes["registry_public_key"]
    res = reg.rotate_registry_key()
    assert res["old_public_key"] == pub_vieja
    assert res["new_public_key"] != pub_vieja
    assert reg.stats()["registry_public_key"] == res["new_public_key"]
    despues = reg.export_reputation(prof["id"])
    # El export nuevo verifica fuerte contra la clave nueva…
    ok = verify_export(despues, trusted_registry_key=res["new_public_key"])
    assert ok["signature_valid"] is True and ok["key_trusted"] is True
    # …el antiguo sigue verificando contra la ANTIGUA (su firma es
    # real), pero NO contra la nueva: rotar no reescribe el pasado.
    viejo = verify_export(antes, trusted_registry_key=pub_vieja)
    assert viejo["signature_valid"] is True and viejo["key_trusted"] is True
    cruzado = verify_export(antes, trusted_registry_key=res["new_public_key"])
    assert cruzado["key_trusted"] is False
    reg.close()


# --------------------------------------- firma desde /guild deliver (p. 3)
def _setup_comandos(tmp_path, monkeypatch):
    monkeypatch.setenv("GUILD_DATA_DIR", str(tmp_path / "cmd"))
    import commands
    salida = commands.guild_command(
        'join @lee "Lee Renteria" muse skills=python idiomas=es')
    from guild.paths import db_path
    reg = Registry(db_path())
    marco = reg.create_profile("marco", "Marco", platform="hermes",
                               skills_offered=["baseten"], languages=["es"])
    lee_id = reg.get_profile_by_handle("lee")["id"]
    conn = reg.request_connection(marco["id"], lee_id, message="colaboro")
    reg.decide_connection(conn["id"], True)
    reg.close()
    return commands, salida, conn["id"]


def test_join_guarda_la_clave_local_con_0600(tmp_path, monkeypatch):
    _commands, salida, _cid = _setup_comandos(tmp_path, monkeypatch)
    from guild.paths import keys_path
    assert "🔐" in salida and "keys.json" in salida
    kp = keys_path()
    assert kp.exists()
    assert stat.S_IMODE(kp.stat().st_mode) == 0o600
    datos = json.loads(kp.read_text())
    assert datos["private_key"] and datos["enc_private_key"]


def test_deliver_del_comando_firma_de_verdad(tmp_path, monkeypatch):
    commands, _salida, cid = _setup_comandos(tmp_path, monkeypatch)
    out = commands.guild_command(f'deliver {cid} "Truss" "resumen"')
    assert "Firmada Ed25519" in out
    from guild.paths import db_path
    reg = Registry(db_path())
    entregas = reg.list_deliveries(cid)
    assert len(entregas) == 1 and entregas[0]["signature"]
    assert reg.verify_delivery(entregas[0]["id"])["valid"] is True
    reg.close()


def test_deliver_sin_clave_local_avisa_no_calla(tmp_path, monkeypatch):
    commands, _salida, cid = _setup_comandos(tmp_path, monkeypatch)
    from guild.paths import keys_path
    # El usuario borra su clave: el comando SIGUE funcionando…
    out_forget = commands.guild_command("keys forget")
    assert "borrada" in out_forget
    assert not keys_path().exists()
    out = commands.guild_command(f'deliver {cid} "Truss" "resumen"')
    # …pero avisando en voz alta de que va SIN firmar. Nunca en silencio.
    assert "SIN firmar" in out
    from guild.paths import db_path
    reg = Registry(db_path())
    entregas = reg.list_deliveries(cid)
    assert len(entregas) == 1 and not entregas[0]["signature"]
    reg.close()
    # Y /guild keys lo cuenta tal cual.
    assert "Sin clave privada local" in commands.guild_command("keys")
