---
title: "Runtime & Memory"
nav_order: 9
has_children: true
---

# Runtime & Memory

AgentCore Runtime runs each agent session inside an isolated microVM, providing per-session process isolation, auto-scaling, and built-in authentication — all from a single container image. Memory extends the runtime with managed storage that lives outside the microVM so agents accumulate knowledge across sessions. This section also covers the A2A protocol for agent-to-agent communication and the Prompt Registry for versioned prompt management.

| Page | What it covers |
|------|---------------|
| [Runtime](runtime/runtime) | AgentCore Runtime internals — `/invocations` + `/ping` contract, `AgentCoreApp`, `GenericHandler`, OTel telemetry flush, streaming |
| [Memory](runtime/memory) | Short-term event store + long-term strategy-extracted semantic memory, wiring, branching |
| [A2A Communication](runtime/a2a) | Agent-to-agent protocol — agent cards, coordinator/specialist pattern, M2M auth, port convention |
| [Prompt Registry](runtime/prompts) | Versioned prompt management — S3 + DynamoDB storage, lifecycle, mode-gated resolution |
