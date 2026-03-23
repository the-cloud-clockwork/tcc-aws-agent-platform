# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- Memory Strategies
#
# Creates AgentCore memory strategies extracted from agent blueprints.
# Each strategy defines how long-term memories are processed:
#   - SUMMARIZATION: produces session summaries (blueprint alias: SUMMARY)
#   - SEMANTIC: extracts factual knowledge
#   - USER_PREFERENCE: learns user preferences from conversations
#   - EPISODIC: captures meaningful interaction slices for contextual recall
#   - CUSTOM: user-defined strategy logic
#
# The AgentCore Memory API allows only ONE strategy per type on a given
# memory resource. When multiple agents declare the same strategy type,
# we deduplicate by resolved API type — first name wins, namespaces are
# merged from all agents declaring that type.
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Type mapping: blueprint convenience names → API values
  # Full API type list: SEMANTIC, SUMMARIZATION, USER_PREFERENCE, CUSTOM, EPISODIC
  strategy_type_map = {
    "SUMMARY"         = "SUMMARIZATION"
    "SUMMARIZATION"   = "SUMMARIZATION"
    "SEMANTIC"        = "SEMANTIC"
    "USER_PREFERENCE" = "USER_PREFERENCE"
    "CUSTOM"          = "CUSTOM"
    "EPISODIC"        = "EPISODIC"
  }

  # Resolve each strategy's API type, collect all namespaces per type
  _strategies_with_api_type = [
    for s in local.agent_memory_strategies : {
      api_type  = lookup(local.strategy_type_map, s.type, s.type)
      name      = s.name
      namespace = s.namespace
    }
  ]

  # Group by API type — collect all namespaces, take first name
  _strategies_by_type = {
    for s in local._strategies_with_api_type :
    s.api_type => s...
  }

  # Deduplicated map: one entry per API type
  memory_strategy_map = {
    for api_type, entries in local._strategies_by_type :
    api_type => {
      name       = entries[0].name
      api_type   = api_type
      namespaces = distinct([for e in entries : e.namespace if e.namespace != ""])
    }
  }
}

resource "aws_bedrockagentcore_memory_strategy" "this" {
  for_each = local.memory_strategy_map

  name      = each.value.name
  memory_id = var.memory_id
  type      = each.value.api_type

  namespaces = each.value.namespaces
}
