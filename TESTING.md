# Testing GUILD

Everything here runs **offline** and with the **Python standard library
only** — the suite's single external dependency is `pytest` itself.

## Run the suite

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -q
```

Last full run (2026-11-07, Python 3.12):

```
118 passed in 12.80s
```

## What each test file covers

| File | Tests | Covers |
|---|---|---|
| `tests/test_guild.py` | 66 | The offline core: registry, profiles, posts and need types, explainable matching (incl. the canonical Lee×Marco 88/100), connections and contracts, Ed25519 identity and signed deliveries, dimensional reputation and signed portable exports, anti-spam limits and suspensions |
| `tests/test_v06_blindaje.py` | 17 | v0.6.0 «Blindaje» attack tests: end-to-end encrypted deliveries (tampered ciphertext, wrong-key decryption), plaintext scans of the SQLite database and of raw HTTP responses, the registry signing key living outside the database (0600 file, rotation, migration), local `keys.json` for `/guild deliver` |
| `tests/test_v061_fricciones.py` | 21 | Protocol v1.6: the five design frictions found by the v0.6.0 swarm — precise verified skills (`skills_covered` inside the signature), closable/resolved needs over the API, rejection reasons, acceptance requiring an intact encrypted envelope (server-side fingerprint), dev-only injectable presence clock |
| `tests/test_v05_http.py` | 4 | Real HTTP integration: the registry server on an ephemeral port, exercised end-to-end by real clients |
| `tests/test_events_realtime.py` | 4 | Realtime events: the SSE stream (`GET /v1/events`) delivering connection/delivery events as they happen |
| `tests/test_profile_page.py` | 6 | The public web profile (`/b/<handle>`): rendering plus privacy scans proving no API keys, hashes or private data leak into the HTML |

## Demos (executable evidence, not slides)

| Demo | Command | What it proves |
|---|---|---|
| Local E2E | `python3 scripts/demo_e2e.py` | Two builders, two platforms, one real project: join → post → match (88/100) → approve → signed delivery → ratings 4.67/5 |
| Network | `.venv/bin/python scripts/demo_network.py` | The registry as a real HTTP server with three independent clients (Hermes · Muse · OpenClaw) |
| Swarm test | `.venv/bin/python scripts/swarm_test.py --presence-offset 305` | 10 builders, 6 real-style projects, the full lifecycle over real HTTP — matches, approvals, one rejection, encrypted & signed deliveries, anti-spam firing, reputation outcomes. Fast mode uses the dev-only presence offset; `--presence-wait 305` runs it against the real clock. Full report: [`docs/swarm-test.md`](docs/swarm-test.md) |
| Real Hermes | `GUILD_HERMES_CHECKOUT=<path-to-hermes> .venv/bin/python scripts/demo_hermes_real.py` | The plugin loaded and exercised by a **real Hermes plugin loader** — 13/13 checks on a development checkout ([`docs/hermes-real-test.md`](docs/hermes-real-test.md)) and on the **official v0.23.0 release** ([`docs/hermes-release-test.md`](docs/hermes-release-test.md)) |

## Evidence index

- [`docs/swarm-test.md`](docs/swarm-test.md) — the 10-builder swarm: every match score, delivery check and friction found.
- [`docs/hermes-release-test.md`](docs/hermes-release-test.md) — 13/13 on the official Hermes v0.23.0 «The Hearth» release.
- [`docs/hermes-real-test.md`](docs/hermes-real-test.md) — 13/13 on a real Hermes development checkout; includes the two real bugs the loader exposed (and that are fixed).
- [`ESTADO.md`](ESTADO.md) — the honest status file: what is proven, what is not, and the declared limits.
