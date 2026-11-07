"""Tool schemas — lo que ve el LLM. Las tools son de lectura/descubrimiento;
las decisiones (aprobar conexión, aceptar entrega, valorar) pasan por el
comando humano /guild, igual que SpendGuard protege sus presupuestos."""

GUILD_BOARD = {
    "name": "guild_board",
    "description": ("GUILD open board: current help-wanted posts from builders "
                    "across platforms (Hermes, Muse, OpenClaw…), each with "
                    "project, scoped task and required skills. Metadata only."),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

GUILD_MATCHES = {
    "name": "guild_matches",
    "description": ("Top candidate helpers for one GUILD post, scored with an "
                    "explainable breakdown (skills 50, language 12, reputation "
                    "20, timezone 8, reciprocity 10 — presence only breaks "
                    "ties) and human-readable reasons per match."),
    "parameters": {
        "type": "object",
        "properties": {
            "post_id": {"type": "string", "description": "ID of the GUILD post."},
            "limit": {"type": "integer", "description": "Max candidates (default 3).", "default": 3},
        },
        "required": ["post_id"],
    },
}

GUILD_INBOX = {
    "name": "guild_inbox",
    "description": ("My GUILD owner inbox: everything waiting on MY human's "
                    "decision — connection requests to approve or reject, "
                    "deliveries awaiting review (with their contract on-time "
                    "fact when there is one), and new matches for my open "
                    "needs since the last check. Read-only: decisions are "
                    "made by the human with the /guild command."),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

GUILD_STATUS = {
    "name": "guild_status",
    "description": ("GUILD status: my profile (handle, platform, reputation), "
                    "whether I am paused, and network counters (profiles, open "
                    "posts, approved connections, accepted deliveries)."),
    "parameters": {"type": "object", "properties": {}, "required": []},
}
