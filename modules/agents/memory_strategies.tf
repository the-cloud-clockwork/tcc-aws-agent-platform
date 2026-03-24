# ──────────────────────────────────────────────────────────────────────────────
# Agents Module -- Memory Strategies
#
# Creates AgentCore memory strategies extracted from agent blueprints.
# Each strategy defines how long-term memories are processed:
#   - SUMMARIZATION: produces session summaries (blueprint alias: SUMMARY)
#   - SEMANTIC: extracts factual knowledge
#   - USER_PREFERENCE: learns user preferences from conversations
# NOTE: EPISODIC is documented but not yet supported by the AWS API
# NOTE: CUSTOM is documented but not yet supported by the AWS API
#
# The AgentCore Memory API allows only ONE strategy per type on a given
# memory resource. When multiple agents declare the same strategy type,
# we deduplicate by resolved API type — first declaration wins.
# Namespace isolation between agents is handled at the SDK level via
# {actorId}/{sessionId} templates, not at the strategy resource level.
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Type mapping: blueprint convenience names → API values
  # Supported API types: SEMANTIC, SUMMARIZATION, USER_PREFERENCE
  strategy_type_map = {
    "SUMMARY"         = "SUMMARIZATION"
    "SUMMARIZATION"   = "SUMMARIZATION"
    "SEMANTIC"        = "SEMANTIC"
    "USER_PREFERENCE" = "USER_PREFERENCE"
  }

  # Resolve each strategy's API type
  _strategies_with_api_type = [
    for s in local.agent_memory_strategies : {
      api_type  = lookup(local.strategy_type_map, s.type, s.type)
      name      = s.name
      namespace = s.namespace
    }
  ]

  # Group by API type
  _strategies_by_type = {
    for s in local._strategies_with_api_type :
    s.api_type => s...
  }

  # Sort entries by name within each type for deterministic "first wins" selection.
  # Without sorting, iteration order depends on blueprint filename ordering,
  # which causes the provider to see name changes on every apply.
  _sorted_strategies_by_type = {
    for api_type, entries in local._strategies_by_type :
    api_type => [
      for name in sort([for e in entries : e.name]) :
      [for e in entries : e if e.name == name][0]
    ]
  }

  # Deduplicated map: one entry per API type, alphabetically first name wins.
  # API constraint: namespaces list length <= 1.
  memory_strategy_map = {
    for api_type, sorted_entries in local._sorted_strategies_by_type :
    api_type => {
      name       = sorted_entries[0].name
      api_type   = api_type
      namespaces = sorted_entries[0].namespace != "" ? [sorted_entries[0].namespace] : []
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
