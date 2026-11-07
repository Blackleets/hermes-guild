"""Hermes GUILD plugin — registration.

Wires the read-only discovery tools, the heartbeat hook and the
human-driven /guild command into Hermes, using only the public plugin
surface (register(ctx)). Decisions (approve, accept, rate) live in the
command, typed by the human — the agent proposes, the owner disposes.
"""

import logging
import sys
from pathlib import Path

try:
    from . import commands, hooks, schemas, tools
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import commands  # type: ignore
    import hooks  # type: ignore
    import schemas  # type: ignore
    import tools  # type: ignore

logger = logging.getLogger(__name__)


def register(ctx):
    ctx.register_tool(name="guild_board", toolset="hermes-guild",
                      schema=schemas.GUILD_BOARD, handler=tools.guild_board)
    ctx.register_tool(name="guild_matches", toolset="hermes-guild",
                      schema=schemas.GUILD_MATCHES, handler=tools.guild_matches)
    ctx.register_tool(name="guild_status", toolset="hermes-guild",
                      schema=schemas.GUILD_STATUS, handler=tools.guild_status)
    ctx.register_tool(name="guild_inbox", toolset="hermes-guild",
                      schema=schemas.GUILD_INBOX, handler=tools.guild_inbox)

    try:
        ctx.register_hook("on_session_start", hooks.on_session_start)
    except Exception:
        logger.debug("guild: on_session_start hook not available, heartbeat via command only")

    ctx.register_command("guild", commands.guild_command,
                         description="GUILD: open cross-platform builder collaboration — join, post needs, match, connect, deliver, rate")

    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.exists():
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                ctx.register_skill(child.name, skill_md)

    logger.info("hermes-guild registered: guild_board, guild_matches, guild_status, guild_inbox, /guild")
