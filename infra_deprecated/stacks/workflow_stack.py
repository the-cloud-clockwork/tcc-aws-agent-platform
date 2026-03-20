"""Workflow stack: Step Functions state machines from YAML blueprints."""
from __future__ import annotations

from aws_cdk import (
    Stack,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from constructs import Construct

from constructs_.sfn_workflow import SfnWorkflow
from stacks.data_stack import DataStack


# Simplified workflow matching the SfnWorkflow construct format.
# Choice states, fail states, and wait states require a construct
# upgrade — tracked for Phase 2.
EXAMPLE_WORKFLOW_YAML = """\
name: example-workflow
steps:
  - agent: example-agent
    next: parallel-analysis
  - parallel:
      - agent: example-analyzer-a
      - agent: example-analyzer-b
    next: example-processor
  - agent: example-processor
    next: example-summarizer
  - agent: example-summarizer
"""


class WorkflowStack(Stack):
    """Provisions Step Functions state machines from workflow blueprints."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: dict,
        agent_functions: dict[str, lambda_.IFunction],
        data_stack: DataStack,
        manifest_lambda: lambda_.IFunction | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        prefix = config.get("resource_prefix", "platform")

        # Resolve output bucket for claim-check pattern
        artifacts_bucket = data_stack.buckets.get("artifacts")
        output_bucket_name = artifacts_bucket.bucket_name if artifacts_bucket else ""

        self.example_workflow = SfnWorkflow(
            self,
            "ExampleWorkflow",
            blueprint_yaml=EXAMPLE_WORKFLOW_YAML,
            agent_functions=agent_functions,
            output_bucket_name=output_bucket_name,
            env_name=env_name,
            resource_prefix=prefix,
            manifest_lambda=manifest_lambda,
        )
