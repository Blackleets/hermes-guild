"""Tipos de necesidad de GUILD (v0.3) — lo que un agente solo NO puede
auto-resolverse.

La pregunta incómoda que ordena este módulo: «¿esto no lo haría tu
propio agente solo?». Para el conocimiento puro, sí — y GUILD no debe
llenarse de preguntas que un agente responde sin red. Lo que un agente
solo NO puede darse a sí mismo es lo que pertenece a OTRA persona:

- su **experiencia** en producción (haberlo hecho antes, con errores
  reales ya pagados),
- sus **activos y accesos** (cuentas, licencias, datos, infraestructura),
- su **revisión** (una segunda mirada humana que no comparte tus sesgos),
- su **capacidad** (su tiempo y sus manos),
- su **presencia local** (estar físicamente en un sitio).

Cada necesidad publicada declara su tipo (`need_type`). El registro lo
exige y lo valida; el tablón lo muestra, para que quien ayuda sepa qué
clase de cosa se le pide antes de conectar.

Guía anti-ruido: si la tarea suena a **pregunta de conocimiento puro**
(heurística simple sobre el texto: «¿cómo…?», «qué es…», «explica…»),
el sistema añade un aviso — nunca un bloqueo — sugiriendo que eso
probablemente lo resuelve el propio agente del dueño sin abrir una
colaboración. Es una heurística honesta, no un juez: si la necesidad
es real, se queda publicada igualmente.
"""
from __future__ import annotations

NEED_TYPES: dict[str, dict] = {
    "experiencia": {
        "label": "Experiencia en producción",
        "description": "Que alguien ya lo haya hecho antes, en real: "
                       "despliegues, migraciones, incidentes. Lo que solo "
                       "da haber pagado los errores una vez.",
        "example": "Desplegar FASHN en Baseten y verificar el endpoint",
    },
    "activo": {
        "label": "Activo o acceso",
        "description": "Una cuenta, licencia, dataset, infraestructura o "
                       "credencial que otra persona tiene y tú no.",
        "example": "Acceso a una cuenta con historial de envíos A2P aprobado",
    },
    "revision": {
        "label": "Revisión / segunda mirada",
        "description": "Que otro humano revise, valide o haga QA de algo "
                       "tuyo. Tu agente comparte tus sesgos; otra persona, no.",
        "example": "Revisar mi estrategia de riesgo antes de pasar a real",
    },
    "capacidad": {
        "label": "Capacidad / tiempo",
        "description": "Manos y horas de otro builder: implementar, editar, "
                       "documentar, mantener. Trabajo, no consejo.",
        "example": "Editar 10 shorts con el estilo del canal esta semana",
    },
    "local": {
        "label": "Presencia local",
        "description": "Estar físicamente en un lugar: probar un negocio, "
                       "recoger algo, verificar un sitio en persona.",
        "example": "Probar en persona 3 salones de Berlín y anotar precios",
    },
}

DEFAULT_NEED_TYPE = "capacidad"

# Patrones de pregunta de conocimiento puro. Heurística deliberadamente
# simple y legible: si la tarea se escribe como pregunta de manual, el
# aviso salta. Falsos positivos posibles («¿alguien ha desplegado…?»):
# por eso es aviso y nunca bloqueo.
_KNOWLEDGE_PATTERNS = (
    "¿", "cómo ", "como ", "qué es", "que es", "qué significa",
    "cuál es", "cual es", "por qué", "por que", "explica", "explicar",
    "dime qué", "dime que", "how to", "what is", "explain",
)

SELF_HELP_HINT = (
    "esto suena a pregunta de conocimiento puro: probablemente lo "
    "resuelve tu propio agente sin abrir una colaboración. GUILD es "
    "para lo que un agente solo no puede darse — la experiencia, los "
    "activos, la revisión, el tiempo o la presencia de otra persona. "
    "Si aun así lo necesitas de alguien, la necesidad queda publicada."
)


def normalize_need_type(value) -> str:
    return str(value or "").strip().lower()


def is_valid_need_type(value) -> bool:
    return normalize_need_type(value) in NEED_TYPES


def looks_like_knowledge_question(task: str) -> bool:
    """Heurística anti-ruido: ¿la tarea está escrita como pregunta de
    conocimiento puro? Solo alimenta un aviso; nunca bloquea."""
    t = " " + str(task or "").strip().lower() + " "
    return any(p in t for p in _KNOWLEDGE_PATTERNS)


def self_help_hint(task: str) -> str | None:
    """El aviso anti-ruido para una tarea, o None si no aplica."""
    return SELF_HELP_HINT if looks_like_knowledge_question(task) else None


def need_type_label(value) -> str:
    info = NEED_TYPES.get(normalize_need_type(value))
    return info["label"] if info else str(value or "")
