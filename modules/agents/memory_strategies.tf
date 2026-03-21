# ──────────────────────────────────────────────────────────────────────────────
# Agents Module — Memory Strategies
#
# Creates AgentCore memory strategies extracted from agent blueprints.
# Each strategy defines how long-term memories are processed:
#   - USER_PREFERENCE: learns user preferences from conversations
#   - SEMANTIC: extracts factual knowledge
#   - SUMMARIZATION: produces session summaries
#
# Blueprint type "SUMMARY" is mapped to the API type "SUMMARIZATION".
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Map keyed for for_each from the flattened list
  memory_strategy_map = {
    for s in local.agent_memory_strategies :
    s.key => s
  }

  # Type mapping: blueprint uses SUMMARY, API uses SUMMARIZATION
  strategy_type_map = {
    "SUMMARY"         = "SUMMARIZATION"
    "SUMMARIZATION"   = "SUMMARIZATION"
    "SEMANTIC"        = "SEMANTIC"
    "USER_PREFERENCE" = "USER_PREFERENCE"
  }
}

resource "aws_bedrockagentcore_memory_strategy" "this" {
  for_each = local.memory_strategy_map

  name      = each.value.name
  memory_id = var.memory_id
  type      = lookup(local.strategy_type_map, each.value.type, each.value.type)

  namespaces = each.value.namespace != "" ? [each.value.namespace] : []

}
