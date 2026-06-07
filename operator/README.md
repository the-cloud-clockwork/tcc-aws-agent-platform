# operator/ — Internal Design & State Documentation

> **Internal only — not part of the public docs site.**
> These files track active project state, design decisions, and work history.
> They are excluded from the GitHub Pages build via `_config.yml`.

---

## Index

| File | Purpose |
|------|---------|
| [VISION.md](VISION.md) | Operator-owned product vision — the 12 building blocks, platform vs. domain split, consumption model. Read-only except by the operator. |
| [SPECS.md](SPECS.md) | Technical specifications — architecture, runtime contract, gateway, memory, observability, evaluation, policy, A2A, infrastructure, dependencies, and constraints. |
| [BLOCKS.md](BLOCKS.md) | Work block ledger — completed blocks (1–5) and the current backlog. Each block has a Definition of Done and evidence. |
| [STATE.md](STATE.md) | Project state assessment — dimensional scores, strengths, weaknesses, and assessment history. |
| [TODO.md](TODO.md) | Smaller open items and pending decisions not large enough for a full block — IAM hardening follow-ups, platform hardening, application-level gaps. |
| [BUGS.md](BUGS.md) | Bug tracker (P0–P3). Currently empty — all known bugs were resolved in Blocks 1–5 or reclassified. |
| [KNOWN-ISSUES.md](KNOWN-ISSUES.md) | Tracked known issues with workarounds: KI-001 (Gateway MCP tools/call AWS bug), KI-002 (Cedar policies SDK-managed). |
| [ENHANCEMENTS.md](ENHANCEMENTS.md) | Enhancement tracking — 14 done in Blocks 1–4, 8 Next Moves (NM-001–NM-008), and the unchanged backlog. |
| [MVP.md](MVP.md) | MVP status — what's running, completed blocks summary, release criteria checklist, and audit findings. |
| [inference-migration.md](inference-migration.md) | Full story of the provider-agnostic inference migration: coupling audit, decoupling strategy (Stages 1–3), implementation checklist, and env var reference. Stage 1+2 complete and production-validated. Stage 3 postponed. |

---

## Subdirectories

| Directory | Contents |
|-----------|----------|
| [references/](references/) | Reference docs imported from external analysis: CONCEPTS.md, TECHNICAL-GUIDE.md, PLATFORM-REFERENCE.md. Content preserved as-is. |
| [drafts/](drafts/) | Work-in-progress scratch files (currently empty). |
| [incidents/](incidents/) | Incident post-mortems (currently empty). |
| [images/](images/) | Diagrams and screenshots referenced from operator docs. |

---

## Current Reality (as of 2026-06-07)

- **Phases 1 + 2 are production-validated.** Provider-agnostic inference (bedrock / anthropic / litellm / vertex) and observability decoupling are both live.
- **Stage 3 (runtime/memory/gateway optionality) is postponed.** See `inference-migration.md` for the reasoning.
- **Recent bug fixes landed on `dev`:**
  - `8c784df` — StructuredOutputEnforcer fallback deleted; Strands native structured output used for all providers (strands-agents ≥ 1.41.0 resolves the upstream bugs).
  - `4c57d6c` — Graph coordinator synthesis turn now fires correctly after graph nodes complete (Bug F + Bug A).
  - `8f8b367` — Agent reasoning captured in Langfuse trace input/output (Bug H).
  - `319ba11` — platform-deps Lambda layer built hermetically in Terraform (no more local pip install in CI).
- **Active known issues:** KI-001 (Gateway MCP tools/call, AWS #809) and KI-002 (Cedar SDK-managed, no IaC drift detection) remain open.
