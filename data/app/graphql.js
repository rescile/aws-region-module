// ======================== GRAPHQL CONFIGURATION ========================
// Maps UI views to GraphQL queries based on AWS Network Hub models

window.VIEWS = {
  providers: {
    title: "Region",
    icon: "M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z",
    query: `{ site { location region endpoint availability_zone } }`,
    node: "site",
    columns: ["name", "region", "endpoints", "availability zones"],
  },
  subscriptions: {
    title: "Subscription",
    icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
    query: `{ subscription { name tenant stage } }`,
    node: "subscription",
    columns: ["name", "tenant", "stage"],
  },
  logins: {
    title: "Operator",
    icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z",
    query: `{ login { name function description } }`,
    node: "login",
    columns: ["name", "function", "description"],
  },
  routers: {
    title: "Gateway",
    icon: "M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z",
    query: `{ gateway { original_name function network { node { cidr} } } }`,
    node: "router",
    columns: ["name", "function", "network"],
  },
  regions: {
    title: "Endpoint Regions",
    icon: "M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9",
    query: `{ region { name function pid endpoint } }`,
    node: "region",
    columns: ["name", "function", "pid", "endpoint"],
  },
  accounts: {
    title: "Account",
    icon: "M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z",
    query: `{ account { name function } }`,
    node: "account",
    columns: ["name", "function"],
  },
};

window.TOPOLOGY_VIEWS = {
  topo_hub: {
    title: "Network Hub Architecture",
    icon: "M13 10V3L4 14h7v7l9-11h-7z",
    description:
      "Visualizes the structural transit zone bridging AWS providers, endpoint regions, subscriptions, and edge routers.",
    buildQuery: function () {
      return `{
                provider { name function site }
                router { name function network { node { cidr } } }
                region { name function pid }
                subscription { name tenant stage }
            }`;
    },
    buildDiagram: function (data) {
      let lines = ["graph LR"];
      const providers = data?.provider || [];
      const routers = data?.router || [];
      const regions = data?.region || [];
      const subscriptions = data?.subscription || [];

      lines.push('  subgraph AWS["☁️ Cloud Provider Ecosystem"]');
      providers.forEach((p) => {
        const id = sanitizeId("prov_" + (p?.name || "unknown"));
        lines.push(`    ${id}["${esc(p?.function)}\\n<i>${esc(p?.name)}</i>"]`);
      });
      lines.push("  end");

      if (subscriptions.length > 0) {
        lines.push('  subgraph Subs["📦 Customer Subscriptions"]');
        subscriptions.forEach((s) => {
          const id = sanitizeId("sub_" + (s?.name || "unknown"));
          lines.push(
            `    ${id}("Tenant: ${esc(s?.tenant)}\\n[Stage: ${esc(s?.stage)}]")`,
          );
        });
        lines.push("  end");

        subscriptions.forEach((s) => {
          const sId = sanitizeId("sub_" + (s?.name || "unknown"));
          providers.forEach((p) => {
            lines.push(
              `  ${sId} -.->|BASELINE_TEMPLATE| ${sanitizeId("prov_" + (p?.name || "unknown"))}`,
            );
          });
        });
      }

      if (routers.length > 0) {
        lines.push('  subgraph TransitZone["🔀 Network Transit Zone"]');
        routers.forEach((r) => {
          const id = sanitizeId("rtr_" + (r?.name || "unknown"));
          let nets = (r?.network || [])
            .map((n) => n?.node?.cidr)
            .filter(Boolean)
            .join(", ");
          const netText = nets ? `\nNet: ${esc(nets)}` : "";
          lines.push(
            `    ${id}{{"${esc(r?.name)}\\nFn: ${esc(r?.function)}${netText}"}}`,
          );
        });
        lines.push("  end");

        routers.forEach((r) => {
          const rId = sanitizeId("rtr_" + (r?.name || "unknown"));
          const platformName = r?.provider?.[0]?.node?.name;
          if (platformName) {
            lines.push(
              `  ${sanitizeId("prov_" + platformName)} -->|PROVIDED_BY| ${rId}`,
            );
          } else {
            providers.forEach((p) =>
              lines.push(
                `  ${sanitizeId("prov_" + (p?.name || "unknown"))} -->|PROVIDED_BY| ${rId}`,
              ),
            );
          }
        });
      }

      if (regions.length > 0) {
        lines.push('  subgraph Endpoints["🌍 Region Endpoints"]');
        regions.forEach((r) => {
          const id = sanitizeId("reg_" + (r?.pid || "unknown"));
          lines.push(`    ${id}[/"Region: ${esc(r?.pid)}"\\]`);
        });
        lines.push("  end");

        providers.forEach((p) => {
          const pId = sanitizeId("prov_" + (p?.name || "unknown"));
          regions.forEach((r) => {
            lines.push(
              `  ${pId} -->|MANAGED_BY| ${sanitizeId("reg_" + (r?.pid || "unknown"))}`,
            );
          });
        });
      }

      lines.push(
        "  classDef provStyle fill:#fff7ed,stroke:#ea580c,stroke-width:2px,color:#9a3412",
      );
      lines.push(
        "  classDef subStyle fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#166534",
      );
      lines.push(
        "  classDef routerStyle fill:#eff6ff,stroke:#2563eb,stroke-width:2px,color:#1e40af",
      );
      lines.push(
        "  classDef regStyle fill:#f3e8ff,stroke:#9333ea,stroke-width:2px,color:#581c87",
      );

      providers.forEach((p) =>
        lines.push(
          `  class ${sanitizeId("prov_" + (p?.name || "unknown"))} provStyle`,
        ),
      );
      subscriptions.forEach((s) =>
        lines.push(
          `  class ${sanitizeId("sub_" + (s?.name || "unknown"))} subStyle`,
        ),
      );
      routers.forEach((r) =>
        lines.push(
          `  class ${sanitizeId("rtr_" + (r?.name || "unknown"))} routerStyle`,
        ),
      );
      regions.forEach((r) =>
        lines.push(
          `  class ${sanitizeId("reg_" + (r?.pid || "unknown"))} regStyle`,
        ),
      );

      return lines.join("\n");
    },
  },
  topo_governance: {
    title: "Identity & Access Governance",
    icon: "M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z",
    description:
      "Security model linking logical commercial/technical accounts to virtual identity logins handling the provider.",
    buildQuery: function () {
      return `{
                account { name function }
                login { name function description }
                provider { name function }
            }`;
    },
    buildDiagram: function (data) {
      let lines = ["graph TB"];
      const accounts = data?.account || [];
      const logins = data?.login || [];
      const providers = data?.provider || [];

      lines.push('  subgraph Orgs["🏢 Base Accounts"]');
      accounts.forEach((a) => {
        const id = sanitizeId("acc_" + (a?.name || "unknown"));
        lines.push(`    ${id}["${esc(a?.name)}\\nFn: ${esc(a?.function)}"]`);
      });
      lines.push("  end");

      lines.push('  subgraph Logins["🔑 Virtual IAM Logins"]');
      logins.forEach((l) => {
        const id = sanitizeId("log_" + (l?.name || "unknown"));
        lines.push(`    ${id}(["${esc(l?.name)}\\nFn: ${esc(l?.function)}"])`);
      });
      lines.push("  end");

      lines.push('  subgraph Provs["☁️ Managed Providers"]');
      providers.forEach((p) => {
        const id = sanitizeId("prov_" + (p?.name || "unknown"));
        lines.push(`    ${id}{{"${esc(p?.function)}\\n(${esc(p?.name)})"}}`);
      });
      lines.push("  end");

      accounts.forEach((a) => {
        const aId = sanitizeId("acc_" + (a?.name || "unknown"));
        providers.forEach((p) => {
          lines.push(
            `  ${aId} -->|DEFINED_BY| ${sanitizeId("prov_" + (p?.name || "unknown"))}`,
          );
        });
      });

      logins.forEach((l) => {
        const lId = sanitizeId("log_" + (l?.name || "unknown"));
        providers.forEach((p) => {
          const pId = sanitizeId("prov_" + (p?.name || "unknown"));
          let linked = false;
          const lFullName = `${l?.function}_${l?.name}`;

          if (
            p?.commercial_contact === l?.name ||
            p?.commercial_contact === l?.function ||
            p?.commercial_contact === lFullName ||
            l?.name?.includes("manager") ||
            l?.name?.includes("account")
          ) {
            lines.push(`  ${lId} -.->|RESPONSIBLE_FOR| ${pId}`);
            linked = true;
          }
          if (
            p?.technical_contact === l?.name ||
            p?.technical_contact === l?.function ||
            p?.technical_contact === lFullName ||
            l?.name?.includes("admin") ||
            l?.name?.includes("cloud")
          ) {
            lines.push(`  ${lId} -.->|MANAGED_BY| ${pId}`);
            linked = true;
          }

          if (
            !linked &&
            (l?.name?.includes("audit") ||
              l?.name?.includes("operator") ||
              l?.name?.includes("network") ||
              l?.name?.includes("platform"))
          ) {
            lines.push(`  ${lId} -.->|OPERATES| ${pId}`);
          }
        });
      });

      lines.push(
        "  classDef accStyle fill:#e2e8f0,stroke:#475569,stroke-width:2px,color:#0f172a",
      );
      lines.push(
        "  classDef logStyle fill:#fef08a,stroke:#ca8a04,stroke-width:2px,color:#713f12",
      );
      lines.push(
        "  classDef provStyle fill:#fff7ed,stroke:#ea580c,stroke-width:2px,color:#9a3412",
      );

      accounts.forEach((a) =>
        lines.push(
          `  class ${sanitizeId("acc_" + (a?.name || "unknown"))} accStyle`,
        ),
      );
      logins.forEach((l) =>
        lines.push(
          `  class ${sanitizeId("log_" + (l?.name || "unknown"))} logStyle`,
        ),
      );
      providers.forEach((p) =>
        lines.push(
          `  class ${sanitizeId("prov_" + (p?.name || "unknown"))} provStyle`,
        ),
      );

      return lines.join("\n");
    },
  },
};
