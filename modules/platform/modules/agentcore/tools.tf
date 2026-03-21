# ──────────────────────────────────────────────────────────────────────────────
# AgentCore Sub-Module — Builtin Tools
#
# Conditionally creates AgentCore managed tools: Code Interpreter and Browser.
# These are shared platform resources available to all agents via the Gateway.
# ──────────────────────────────────────────────────────────────────────────────

# ── Code Interpreter ─────────────────────────────────────────────────────────

resource "aws_bedrockagentcore_code_interpreter" "this" {
  count = var.code_interpreter_enabled ? 1 : 0

  name = "${local.prefix}-${local.env}-code-interpreter"

  network_configuration {
    network_mode = "PUBLIC"
  }

  tags = merge(var.tags, {
    Name      = "${local.prefix}-${local.env}-code-interpreter"
    Module    = "agentcore"
    Component = "code-interpreter"
  })
}

# ── Browser ──────────────────────────────────────────────────────────────────

resource "aws_bedrockagentcore_browser" "this" {
  count = var.browser_enabled ? 1 : 0

  name = "${local.prefix}-${local.env}-browser"

  network_configuration {
    network_mode = "PUBLIC"
  }

  tags = merge(var.tags, {
    Name      = "${local.prefix}-${local.env}-browser"
    Module    = "agentcore"
    Component = "browser"
  })
}
