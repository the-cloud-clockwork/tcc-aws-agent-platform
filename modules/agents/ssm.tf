# ──────────────────────────────────────────────────────────────────────────────
# Agents Module — SSM Parameters
#
# Publishes per-agent outputs to SSM Parameter Store so that other modules,
# domain repos, and operational tools can discover agent runtime ARNs
# without hard-wiring Terraform outputs.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_ssm_parameter" "agent_runtime_arn" {
  for_each = local.blueprints

  name  = "${var.ssm_root_path}/agents/${each.key}/runtime-arn"
  type  = "String"
  value = aws_bedrockagentcore_agent_runtime.agent[each.key].arn

  tags = merge(local.tags, {
    Name      = "${var.ssm_root_path}/agents/${each.key}/runtime-arn"
    Component = "ssm"
    AgentId   = each.key
  })
}
