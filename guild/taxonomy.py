"""Taxonomía de habilidades de GUILD.

Tags en kebab-case, agrupados por categoría. La taxonomía es abierta:
un perfil puede usar tags fuera de la lista, pero los de aquí puntúan
igual y se sugieren en el onboarding para que el matching sea comparable.
"""
from __future__ import annotations

TAXONOMY: dict[str, list[str]] = {
    "voz-y-mensajeria": ["twilio-voz", "twilio-sms", "whatsapp-api", "telegram-bots",
                          "agentes-de-voz", "a2p-registro", "stt-tts", "webrtc"],
    "web-y-frontend": ["nextjs", "react", "vue", "typescript", "javascript",
                        "tailwind", "html-css", "pwa", "vercel", "seo"],
    "backend-y-datos": ["python", "nodejs", "fastapi", "supabase", "postgres",
                         "sqlite", "redis", "apis-rest", "webhooks", "auth"],
    "ia-y-agentes": ["llm-agents", "hermes-plugins", "muse-skills", "prompting",
                      "rag", "fine-tuning", "embeddings", "mcp", "baseten",
                      "openai-api", "gemini-api", "evaluacion-llm"],
    "video-y-contenido": ["edicion-video", "video-ia", "youtube-shorts", "tiktok",
                           "miniaturas", "guiones", "motion-graphics", "bilibili"],
    "diseno-y-3d": ["diseno-3d", "blender", "figma", "ui-ux", "branding",
                     "ilustracion", "animacion-2d", "threejs"],
    "trading-y-cripto": ["trading-algoritmico", "paper-trading", "solana", "bsc",
                          "smart-contracts", "defi", "backtesting", "risk-management"],
    "devops-y-sistemas": ["docker", "ci-cd", "github-actions", "linux", "railway",
                           "render", "vps", "monitoring"],
    "negocio-y-ventas": ["ventas-locales", "copywriting", "automatizacion-pymes",
                          "crm", "stripe", "shopify", "wordpress"],
    "idiomas-y-otros": ["traduccion", "ingles-tecnico", "documentacion",
                         "testing-qa", "scraping", "electron"],
}

ALL_SKILLS: frozenset[str] = frozenset(s for v in TAXONOMY.values() for s in v)

# Alias / sinónimos (matching v2): formas que los builders usan de verdad
# — en inglés, cortas o genéricas — y su forma canónica de la taxonomía.
# Criterio: un alias solo se acepta si un humano diría «es lo mismo» sin
# dudar; nada de vecindades vagas (eso sería inflar matches). La lista es
# corta a propósito y crece con uso real, no por imaginación.
ALIASES: dict[str, str] = {
    # voz y mensajería
    "voz": "agentes-de-voz", "voice": "agentes-de-voz",
    "voice-agents": "agentes-de-voz", "voicebots": "agentes-de-voz",
    "sms": "twilio-sms", "whatsapp": "whatsapp-api",
    "chatbots": "telegram-bots", "tts-stt": "stt-tts",
    # web y frontend
    "frontend": "react", "front-end": "react", "js": "javascript",
    "ts": "typescript", "css": "html-css", "html": "html-css",
    # backend y datos
    "backend": "apis-rest", "api": "apis-rest", "apis": "apis-rest",
    "sql": "postgres", "db": "postgres", "bdd": "postgres",
    # ia y agentes
    "ia": "llm-agents", "ai": "llm-agents", "agentes": "llm-agents",
    "agents": "llm-agents", "llm": "llm-agents", "prompts": "prompting",
    "plugins-hermes": "hermes-plugins", "skills-muse": "muse-skills",
    # vídeo y contenido
    "video": "edicion-video", "edicion": "edicion-video",
    "shorts": "youtube-shorts", "reels": "youtube-shorts",
    # diseño y 3d
    "3d": "diseno-3d", "diseno": "diseno-3d", "design": "ui-ux",
    "ui": "ui-ux", "ux": "ui-ux",
    # trading y cripto
    "trading": "trading-algoritmico", "markets": "trading-algoritmico",
    "mercados": "trading-algoritmico", "cripto": "defi", "crypto": "defi",
    "algoritmos-trading": "trading-algoritmico",
    # devops y sistemas
    "devops": "ci-cd", "deploy": "ci-cd", "despliegue": "ci-cd",
    "servidores": "vps",
    # negocio y ventas
    "ventas": "ventas-locales", "sales": "ventas-locales",
    "pagos": "stripe", "ecommerce": "shopify",
    # otros
    "qa": "testing-qa", "testing": "testing-qa", "docs": "documentacion",
}


def normalize(tag: str) -> str:
    return "-".join(str(tag).strip().lower().replace("_", " ").split()).replace(" ", "-")


def canonical(tag: str) -> str:
    """Forma canónica de un tag: resuelve alias; si no hay, el tag mismo."""
    n = normalize(tag)
    return ALIASES.get(n, n)


def expand_with_aliases(tags) -> dict[str, str]:
    """{canónica: tag_original} — conserva el original para poder decir
    en la razón del match «tu «voz» cuenta como «agentes-de-voz»»."""
    out: dict[str, str] = {}
    for t in tags or []:
        out.setdefault(canonical(t), normalize(t))
    return out


def normalize_all(tags) -> list[str]:
    out, seen = [], set()
    for t in tags or []:
        n = normalize(t)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def category_of(tag: str) -> str | None:
    n = normalize(tag)
    for cat, skills in TAXONOMY.items():
        if n in skills:
            return cat
    return None


def related(tag: str) -> list[str]:
    """Habilidades de la misma categoría (útiles para sugerir en onboarding)."""
    cat = category_of(tag)
    return list(TAXONOMY[cat]) if cat else []
