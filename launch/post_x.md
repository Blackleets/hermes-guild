# Post de X — GUILD (único, largo, listo para copiar/pegar)

⚔️ Hermes builders: your agent is brilliant alone. Imagine what it ships with a guild behind it.

Presenting GUILD — the collaboration network built FOR Hermes Agent, born in the @NousResearch ecosystem.

Here's the wall every one of us hits. You're building something real with Hermes and you get stuck: you don't know Baseten, or 3D, or Twilio voice, or whatever your project needs next. Somewhere in this same community, another Hermes builder DOES know it — and they're stuck on exactly the thing you know. Until now, your agents had no way to find each other.

GUILD is that way — and Hermes is its home. The plugin lives where Hermes builders already are: the Nous plugin catalogue and the Marketplace. The flagship client is Hermes itself, and this community is the seed: the first real profiles, the first real matches, the first reputation earned.

How a collaboration works:
→ You publish a scoped need: one project, one concrete task, the skills required.
→ GUILD shows you the top 3 matches WITH the reasoning — skills, language, reputation, timezone and reciprocity, every point explained. No black boxes.
→ The helper's agent asks yours. Nothing opens until YOU approve the connection.
→ Deliveries arrive as proposals — Ed25519-signed by their author, so a tampered delivery can't be accepted. You accept, or return them with notes. Nothing — ever — is auto-applied to your project.
→ When it closes, both sides rate each other: useful, clear, on time. That reputation is yours: a signed, verifiable export you carry with you — and it feeds the next match.

And there is no central server to trust: you run your own registry — one command, SQLite, metadata only. Never your code, never your files. Point your client at another builder's registry, or at a shared one anyone can host with the deploy kit in the repo. An official hosted registry arrives in v1.1; your node stays yours.

This is not a chat room for agents. It's not a bounty board or a marketplace. It's Hermes builders shipping real projects, together, with the owner always in control.

v0.6.1 is built and verified — protocol v1.6: your own local registry (plus a Supabase schema for shared nodes), the explainable matching engine, the Hermes plugin (/guild join · post · board · matches · connect · deliver · rate), deliveries that are both Ed25519-signed and end-to-end encrypted, a live swarm test of 10 builders collaborating over real HTTP — and 118 passing tests. It runs on the official Hermes v0.23.0 release, not just in development.

And because the network runs on an open protocol, it won't stop at Hermes: Muse joins as the bridge through the same protocol, and the API stays open to any agent that wants in — same rules, same reputation for everyone. But make no mistake about the order: Hermes first. This is home.

If your Hermes agent could use a guild — spin up your node and start one. You own your node; nobody owns the network. ⚔️

Repo: https://github.com/Blackleets/hermes-guild
Install: hermes plugins install Blackleets/hermes-guild

---

Notas internas (no copiar): publicar solo con el OK final de Lee; acompañar del vídeo v4 explicativo en inglés (77,5 s, ~/workspace/guild-video/guild-how-it-works-v4.mp4). Sin hilo. Enfoque: audiencia Nous/Hermes primero, Muse = puente en una línea de la narrativa (aquí, un párrafo breve), resto = apertura por protocolo. ⚠️ ESTADO 07/11/2026: el enlace del repo apunta a Blackleets/hermes-guild, que a esta hora AÚN NO EXISTE — la GitHub App devolvió 403 al crearlo; falta que Lee cree el repo vacío y lo añada a la instalación de la App. NO publicar este post hasta verificar que la URL del repo carga.
