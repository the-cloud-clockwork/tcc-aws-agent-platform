# ──────────────────────────────────────────────────────────────────────────────
# Agents Module — Memory Strategies
#
# Creates AgentCore memory strategies extracted from agent blueprints.
# Each strategy defines how long-term memories are processed:
#   - SUMMARIZATION: produces session summaries (blueprint alias: SUMMARY)
#   - SEMANTIC: extracts factual knowledge
#   - USER_PREFERENCE: learns user preferences from conversations
#   - EPISODIC: captures meaningful interaction slices for contextual recall
#   - CUSTOM: user-defined strategy logic
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Map keyed for for_each from the flattened list
  memory_strategy_map = {
    for s in local.agent_memory_strategies :
    s.key => s
  }

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
}

resource "aws_bedrockagentcore_memory_strategy" "this" {
  for_each = local.memory_strategy_map

  name      = each.value.name
  memory_id = var.memory_id
  type      = lookup(local.strategy_type_map, each.value.type, each.value.type)

  namespaces = each.value.namespace != "" ? [each.value.namespace] : []

}
