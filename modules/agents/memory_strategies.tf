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

  # Canonical name per strategy type. The API only allows ONE strategy per type
  # on a memory resource, so the name is irrelevant for routing — it's just a
  # label. Using a fixed canonical name avoids provider drift when multiple
  # agents declare the same type with different names.
  _canonical_strategy_names = {
    "SEMANTIC"        = "semantic_knowledge"
    "SUMMARIZATION"   = "session_summaries"
    "USER_PREFERENCE" = "user_preferences"
  }

  # Deduplicated map: one entry per API type, canonical name, first namespace wins.
  # API constraint: namespaces list length <= 1.
  memory_strategy_map = {
    for api_type, entries in local._strategies_by_type :
    api_type => {
      name       = lookup(local._canonical_strategy_names, api_type, entries[0].name)
      api_type   = api_type
      namespaces = entries[0].namespace != "" ? [entries[0].namespace] : []
    }
  }
}

resource "aws_bedrockagentcore_memory_strategy" "this" {
  for_each = local.memory_strategy_map

  name      = each.value.name
  memory_id = var.memory_id
  type      = each.value.api_type

  namespaces = each.value.namespaces

  # WORKAROUND: AWS provider bug — the API returns a different strategy name
  # on read-back when multiple agents share one memory resource with the same
  # strategy type. The provider sees this as drift and errors with
  # "Provider produced inconsistent result after apply". Ignoring name changes
  # prevents this false-positive from blocking all other resource operations.
  # Tracked: https://github.com/hashicorp/terraform-provider-aws/issues/45290
  lifecycle {
    ignore_changes = [name]
  }
}
