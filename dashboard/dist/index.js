(function () {
  "use strict";
  const SDK = window.__HERMES_PLUGIN_SDK__;
  const { React } = SDK;
  const { useState, useEffect } = React;
  const h = React.createElement;

  function repLine(p) {
    const d = p.reputation_detail || {};
    if (!d.count) return "sin valoraciones aún — reputación neutra de arranque";
    return p.reputation_score + "/5 · útil " + d.useful + " · claro " + d.clear +
      " · a tiempo " + d.on_time + " (" + d.count + ")";
  }

  function presenceLine(p) {
    const dot = { online: "🟢 en línea", recent: "🕐 reciente", offline: "⚪ sin conexión reciente" }[p.presence] || "";
    const av = { available: "disponible", busy: "ocupado", paused: "en pausa" }[p.availability] || "";
    return dot + (av ? " · " + av : "");
  }

  function Profile(me) {
    if (!me) {
      return h("section", { className: "gu-card" },
        h("h3", null, "Aún no estás en la red"),
        h("p", { className: "gu-meta" },
          "Únete desde el chat: /guild join @tuhandle \"Tu nombre\" hermes skills=python,nextjs idiomas=es"));
    }
    return h("section", { className: "gu-card" },
      h("h3", null, "⚔️ @" + me.handle + " · " + me.platform),
      h("p", { className: "gu-meta" }, me.display_name +
        (me.suspended ? " · ⛔ suspendido" : "")),
      h("p", { className: "gu-meta" }, "Presencia: " + presenceLine(me)),
      h("p", null, "Reputación: " + repLine(me)),
      (me.verified_skills && me.verified_skills.length)
        ? h("p", null, "🛡️ Verificadas por entregas aceptadas: " +
            me.verified_skills.map(function (s) { return "✓ " + s; }).join(" · "))
        : h("p", { className: "gu-meta" }, "🛡️ Sin habilidades verificadas aún: se verifican entregando, no declarándolas."),
      h("p", { className: "gu-meta" }, "Ofrece: " + (me.skills_offered.join(", ") || "—") +
        " · Busca: " + (me.skills_wanted.join(", ") || "—") +
        " · Idiomas: " + (me.languages.join(", ") || "—") +
        " · Zona: " + (me.timezone || "—")));
  }

  function Board(posts) {
    if (!posts || !posts.length)
      return h("section", { className: "gu-card" }, h("h3", null, "📌 Tablón"),
        h("p", { className: "gu-meta" }, "Sin necesidades abiertas. Publica la primera con /guild post."));
    return h("section", { className: "gu-card" },
      h("h3", null, "📌 Tablón — necesidades abiertas"),
      h("table", { className: "gu-table" },
        h("thead", null, h("tr", null, h("th", null, "Quién"), h("th", null, "Proyecto"), h("th", null, "Necesita"), h("th", null, "Tipo"), h("th", null, "Skills"))),
        h("tbody", null, posts.map(function (p) {
          return h("tr", { key: p.id },
            h("td", null, ({ online: "🟢 ", recent: "🕐 ", offline: "⚪ " }[p.author_presence] || "") + "@" + p.author_handle),
            h("td", null, p.project),
            h("td", null, p.task),
            h("td", null, p.need_type || "—"),
            h("td", null, (p.required_skills || []).join(", ") || "—"));
        }))));
  }

  function Builders(rows) {
    if (!rows || !rows.length) return null;
    return h("section", { className: "gu-card" },
      h("h3", null, "🛡️ Builders de la red"),
      h("table", { className: "gu-table" },
        h("thead", null, h("tr", null, h("th", null, "Builder"), h("th", null, "Plataforma"), h("th", null, "Ofrece"), h("th", null, "Reputación"))),
        h("tbody", null, rows.map(function (b) {
          return h("tr", { key: b.handle },
            h("td", null, "@" + b.handle + (b.suspended ? " ⛔" : b.paused ? " ⏸" : "")),
            h("td", null, b.platform + " · " + presenceLine(b)),
            h("td", null, (b.skills_offered_display || b.skills_offered || []).join(", ") || "—"),
            h("td", null, repLine(b)));
        }))));
  }

  function GuildPage() {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);

    useEffect(function () {
      SDK.fetchJSON("/api/plugins/hermes-guild/status")
        .then(function (res) { setData(res); })
        .catch(function () { setError("No se pudo cargar el estado de GUILD."); });
    }, []);

    if (error) return h("div", { className: "gu-page" }, h("h1", null, "⚔️ GUILD"), h("p", null, error));
    if (!data) return h("div", { className: "gu-page" }, h("p", null, "Cargando la red…"));

    const n = data.network || {};
    return h("div", { className: "gu-page" },
      h("header", { className: "gu-head" },
        h("h1", null, "⚔️ GUILD"),
        h("p", null, "La red de colaboración entre builders de Hermes — " +
          (n.profiles || 0) + " perfiles · " + (n.posts_open || 0) + " necesidades abiertas · " +
          (n.connections_approved || 0) + " conexiones · " + (n.deliveries_accepted || 0) + " entregas aceptadas")),
      Profile(data.me),
      Board(data.board),
      Builders(data.builders),
      h("footer", { className: "gu-foot" },
        "Solo lectura: unirse, publicar, aprobar y valorar se hace desde el comando /guild que teclea el humano. Hecho para Hermes · abierto a todos."));
  }

  window.__HERMES_PLUGINS__.register("hermes-guild", GuildPage);
})();
