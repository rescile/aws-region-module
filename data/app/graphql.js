// ======================== GRAPHQL CONFIGURATION ========================
// Maps UI views to GraphQL queries based on Salesforce Hyperforce Connect models

window.VIEWS = {
  subscriptions: {
    title: "Management Domains",
    icon: "M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z",
    query: `{ network(filter: { function: "transit" }) { name description function } }`,
    node: "network",
    columns: ["name", "description"],
  },
  applications: {
    title: "Application Domains",
    icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
    query: `{ network(filter: { function: "application" }) { name description function } }`,
    node: "network",
    columns: ["name", "function", "description"],
  },
  solutions: {
    title: "Salesforce Environments",
    icon: "M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9",
    query: `{ solution { name owner active description } }`,
    node: "solution",
    columns: ["name", "owner", "active", "description"],
  },
};

window.TOPOLOGY_VIEWS = {
  topo_hub: {
    title: "Network Hub Architecture",
    icon: "M13 10V3L4 14h7v7l9-11h-7z",
    description:
      "Visualizes the structural private connect pathways mapping networks to logical cloud solutions.",
    buildQuery: function () {
      return `{
                network { name function description }
                solution { name description }
            }`;
    },
    buildDiagram: function (data) {
      let lines = ["graph LR"];
      const networks = data?.network || [];
      const solutions = data?.solution || [];

      // Subgraph 1: Core Transit Layer
      lines.push('  subgraph Transit["🔀 Network Transit Hubs"]');
      networks.forEach((n) => {
        const id = sanitizeId("net_" + (n?.name || "unknown"));
        lines.push(
          `    ${id}["${esc(n?.function || "Transit Edge")}\\n<i>${esc(n?.name)}</i>"]`,
        );
      });
      lines.push("  end");

      // Subgraph 2: Target Cloud Infrastructure
      if (solutions.length > 0) {
        lines.push('  subgraph CloudSols["☁️ Salesforce Solutions"]');
        solutions.forEach((s) => {
          const id = sanitizeId("sol_" + (s?.name || "unknown"));
          lines.push(`    ${id}("[Platform: ${esc(s?.name)}]")`);
        });
        lines.push("  end");

        // Establish relationships between networks and targets
        networks.forEach((n) => {
          const nId = sanitizeId("net_" + (n?.name || "unknown"));
          solutions.forEach((s) => {
            const sId = sanitizeId("sol_" + (s?.name || "unknown"));
            lines.push(`  ${nId} -->|ROUTES_TO| ${sId}`);
          });
        });
      }

      // Salesforce-focused color palette
      lines.push(
        "  classDef netStyle fill:#f0f9ff,stroke:#0176d3,stroke-width:2px,color:#082f49",
      );
      lines.push(
        "  classDef solStyle fill:#ecfeff,stroke:#0891b2,stroke-width:2px,color:#083344",
      );

      networks.forEach((n) =>
        lines.push(
          `  class ${sanitizeId("net_" + (n?.name || "unknown"))} netStyle`,
        ),
      );
      solutions.forEach((s) =>
        lines.push(
          `  class ${sanitizeId("sol_" + (s?.name || "unknown"))} solStyle`,
        ),
      );

      return lines.join("\n");
    },
  },
  topo_governance: {
    title: "Identity & Access Governance",
    icon: "M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z",
    description:
      "Security boundaries demonstrating logical IAM logins overseeing operational transits.",
    buildQuery: function () {
      return `{
                login { name function description }
                network { name function }
            }`;
    },
    buildDiagram: function (data) {
      let lines = ["graph TB"];
      const logins = data?.login || [];
      const networks = data?.network || [];

      lines.push('  subgraph Logins["🔑 Virtual IAM Logins"]');
      logins.forEach((l) => {
        const id = sanitizeId("log_" + (l?.name || "unknown"));
        lines.push(`    ${id}(["${esc(l?.name)}\\nFn: ${esc(l?.function)}"])`);
      });
      lines.push("  end");

      lines.push('  subgraph Hubs["🔀 Monitored Infrastructure"]');
      networks.forEach((n) => {
        const id = sanitizeId("net_" + (n?.name || "unknown"));
        lines.push(
          `    ${id}{{"${esc(n?.function || "Network Context")}\\n(${esc(n?.name)})"}}`,
        );
      });
      lines.push("  end");

      logins.forEach((l) => {
        const lId = sanitizeId("log_" + (l?.name || "unknown"));
        networks.forEach((n) => {
          const nId = sanitizeId("net_" + (n?.name || "unknown"));

          if (l?.name?.includes("admin") || l?.function?.includes("network")) {
            lines.push(`  ${lId} -.->|MANAGES| ${nId}`);
          } else {
            lines.push(`  ${lId} -.->|AUDITS| ${nId}`);
          }
        });
      });

      lines.push(
        "  classDef logStyle fill:#faf5ff,stroke:#7e22ce,stroke-width:2px,color:#3b0764",
      );
      lines.push(
        "  classDef netStyle fill:#f0f9ff,stroke:#0176d3,stroke-width:2px,color:#082f49",
      );

      logins.forEach((l) =>
        lines.push(
          `  class ${sanitizeId("log_" + (l?.name || "unknown"))} logStyle`,
        ),
      );
      networks.forEach((n) =>
        lines.push(
          `  class ${sanitizeId("net_" + (n?.name || "unknown"))} netStyle`,
        ),
      );

      return lines.join("\n");
    },
  },
};
