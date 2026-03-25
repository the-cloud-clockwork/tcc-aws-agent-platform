---
title: Workflows Module
nav_order: 3
parent: Infrastructure
---

# Workflows Module

The workflows module (`modules/workflows/`) reads workflow blueprint YAML files and generates AWS Step Functions state machines. Like the agents module, it uses a `for_each` pattern — one state machine per blueprint file. Adding a workflow requires only a new YAML file.

---

## How Workflow Blueprints Become State Machines

The module scans `workflow_dir` for `*.yaml` files at plan time:

```hcl
# locals.tf
workflow_files = fileset(var.workflow_dir, "*.yaml")

workflows = {
  for f in local.workflow_files :
  yamldecode(file("${var.workflow_dir}/${f}")).id => yamldecode(file("${var.workflow_dir}/${f}"))
}
```

For each blueprint, the module generates an Amazon States Language (ASL) definition using Terraform's `jsonencode` function. Agent steps become SDK integration tasks that call `arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime`. Agent Runtime ARNs are resolved from `var.agent_runtime_arns`, which is passed directly from `module.agents.runtime_arns`.

---

## Resources Provisioned Per Workflow

| Resource | Count | Description |
|----------|-------|-------------|
| `aws_sfn_state_machine` | 1 per workflow | Step Functions state machine with full ASL definition |
| `aws_cloudwatch_log_group` | 1 per workflow | Log group at `/aws/stepfunctions/<prefix>-<id>` with configurable retention |
| `aws_iam_role` (sfn) | 1 per workflow | Execution role trusted by `states.amazonaws.com` |
| `aws_iam_role_policy` (sfn) | 1 per workflow | Inline policy: `bedrock-agentcore:InvokeAgentRuntime`, CloudWatch Logs, X-Ray |
| `aws_cloudwatch_event_rule` | 0 or 1 per workflow | EventBridge schedule rule (only when `trigger.type: schedule`) |
| `aws_cloudwatch_event_target` | 0 or 1 per workflow | Wires EventBridge rule to the state machine |
| `aws_iam_role` (events) | 0 or 1 per workflow | EventBridge execution role (only for scheduled workflows) |

---

## State Machine Features

### Sequential Steps

Each `agent:` state entry becomes a Step Functions `Task` state using the AWS SDK integration pattern:

```json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime",
  "Parameters": {
    "AgentRuntimeArn": "<resolved from var.agent_runtime_arns>",
    "Payload.$": "$.prompt"
  },
  "ResultPath": "$.results.<agent_id>",
  "Retry": [{ "ErrorEquals": ["States.ALL"], "MaxAttempts": 3, "BackoffRate": 2 }],
  "Catch": [{ "ErrorEquals": ["States.ALL"], "Next": "<State>_Failed" }]
}
```

### Parallel Branches

`parallel:` states become ASL `Parallel` states. All branches execute simultaneously; results are merged into `$.parallel_results`.

### Automatic Failure States

For every agent step, the module auto-generates a corresponding `<StateId>_Failed` Fail state. On final retry exhaustion, execution transitions to the failure state with a descriptive error cause.

### X-Ray Tracing

All state machines have `tracing_configuration { enabled = true }` — traces are sent to AWS X-Ray automatically.

### Full Execution Data Logging

All state machines log at level `ALL` with `include_execution_data = true` to the per-workflow CloudWatch log group.

---

## Input Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `environment` | `string` | — | Deployment environment |
| `resource_prefix` | `string` | — | Resource name prefix |
| `aws_region` | `string` | — | Primary AWS region |
| `ssm_root_path` | `string` | — | Root SSM path |
| `workflow_dir` | `string` | — | Path to directory containing workflow YAML blueprints |
| `agent_runtime_arns` | `map(string)` | `{}` | Map of `agent_id` → Runtime ARN (from agents module) |
| `lambda_arns` | `map(string)` | `{}` | Map of Lambda function name → ARN for `lambda_ref` task states |
| `log_retention_days` | `number` | `14` | CloudWatch log retention for SFN log groups |
| `tags` | `map(string)` | `{}` | Additional resource tags |

---

## Outputs

| Output | Type | Description |
|--------|------|-------------|
| `state_machine_arns` | `map(string)` | Map of `workflow_id` → State Machine ARN |
| `state_machine_names` | `map(string)` | Map of `workflow_id` → State Machine name |
| `workflow_ids` | `list(string)` | List of all workflow IDs parsed from YAML |

---

## IAM Permissions

The per-workflow IAM role is granted the minimum permissions needed:

```
bedrock-agentcore:InvokeAgentRuntime   # Scoped to the agent Runtime ARNs used in this workflow
bedrock-agentcore:StopRuntimeSession   # Same scope
logs:CreateLogDelivery                 # CloudWatch Logs integration
logs:CreateLogStream
logs:PutLogEvents
logs:PutResourcePolicy
logs:DescribeLogGroups
xray:PutTraceSegments                  # X-Ray tracing
xray:PutTelemetryRecords
xray:GetSamplingRules
xray:GetSamplingTargets
```

The `bedrock-agentcore:InvokeAgentRuntime` permission is scoped to the specific Runtime ARNs referenced in each workflow's states, not a wildcard.

---

## Usage Example

```hcl
module "workflows" {
  source = "git::https://github.com/your-org/aws-agent-platform.git//modules/workflows?ref=v1.0.0"

  environment     = var.environment
  resource_prefix = "myplatform"
  aws_region      = var.aws_region
  ssm_root_path   = "/myplatform/${var.environment}"

  # Blueprint source
  workflow_dir = "${path.module}/blueprints/workflows"

  # Agent Runtime ARN map from the agents module
  agent_runtime_arns = module.agents.runtime_arns

  log_retention_days = 30

  tags = {
    Project   = "my-agent-platform"
    ManagedBy = "Terraform"
  }
}
```

---

## Invoking a Workflow

Start a workflow execution via the AWS CLI or SDK:

```bash
aws stepfunctions start-execution \
  --state-machine-arn $(terraform output -raw state_machine_arns | jq -r '.["analysis-pipeline"]') \
  --input '{"input": {"query": "Summarise recent developments in quantum computing"}}'
```

Or use the platform's SDK:

```python
from agent_core.a2a import WorkflowClient

client = WorkflowClient(state_machine_arn=STATE_MACHINE_ARN)
result = await client.invoke({"query": "Summarise recent developments"})
```

---

## Adding a New Workflow

1. Create a YAML file in `workflow_dir` (e.g. `blueprints/workflows/reporting-pipeline.yaml`)
2. Set a unique `id` and reference existing agent IDs in `states:`
3. Run `terraform plan` to see the new state machine, log group, and IAM resources
4. Run `terraform apply`

The workflow is immediately invocable once the apply completes.
