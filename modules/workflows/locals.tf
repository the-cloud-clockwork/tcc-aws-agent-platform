data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_region.current.name
  name_prefix = "${var.resource_prefix}-${var.environment}"

  workflow_files = fileset(var.workflow_dir, "*.yaml")

  workflows = {
    for f in local.workflow_files :
    yamldecode(file("${var.workflow_dir}/${f}")).id => yamldecode(file("${var.workflow_dir}/${f}"))
  }

  # --- Per-workflow: agent refs (for IAM scoping) ---
  workflow_agent_refs = {
    for wf_id, wf in local.workflows :
    wf_id => distinct(flatten([
      for s in try(wf.states, []) : concat(
        # Direct agent ref on state
        try(s.agent_ref, try(s.agent, null)) != null ? [coalesce(try(s.agent_ref, null), try(s.agent, null))] : [],
        # Agents inside parallel branches
        flatten([
          for b in try(s.parallel, try(s.branches, [])) : concat(
            # Simple branch format: { agent: X }
            try(b.agent_ref, try(b.agent, null)) != null ? [coalesce(try(b.agent_ref, null), try(b.agent, null))] : [],
            # Rich branch format: { states: [{ agent_ref: X }] }
            flatten([
              for bs in try(b.states, []) :
              try(bs.agent_ref, try(bs.agent, null)) != null ? [coalesce(try(bs.agent_ref, null), try(bs.agent, null))] : []
            ])
          )
        ])
      )
    ]))
  }

  # --- Per-workflow: lambda refs (for IAM scoping) ---
  workflow_lambda_refs = {
    for wf_id, wf in local.workflows :
    wf_id => distinct(flatten([
      for s in try(wf.states, []) : concat(
        # Direct lambda_ref on state (task or wait_for_token)
        try(s.lambda_ref, null) != null ? [s.lambda_ref] : [],
        # Lambdas inside parallel branches
        flatten([
          for b in try(s.parallel, try(s.branches, [])) :
          flatten([
            for bs in try(b.states, []) :
            try(bs.lambda_ref, null) != null ? [bs.lambda_ref] : []
          ])
        ])
      )
    ]))
  }

  # --- Trigger categorization ---
  workflows_with_schedule_triggers = {
    for k, wf in local.workflows :
    k => wf if try(wf.trigger.type, "") == "schedule"
  }

  workflows_with_event_triggers = {
    for k, wf in local.workflows :
    k => wf if try(wf.trigger.type, "") == "event"
  }

  workflows_with_triggers = merge(
    local.workflows_with_schedule_triggers,
    local.workflows_with_event_triggers
  )

  tags = merge(var.tags, {
    Module = "workflows"
  })
}
