"""SfnWorkflow -- reusable CDK construct: Blueprint YAML to Step Functions state machine."""
from __future__ import annotations

import aws_cdk as cdk
import yaml
from aws_cdk import (
    Duration,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_stepfunctions as sfn,
)
from aws_cdk import (
    aws_stepfunctions_tasks as sfn_tasks,
)
from constructs import Construct

from constructs_.strands_agent import StrandsAgentTask


class SfnWorkflow(Construct):
    """Generates a Step Functions state machine from a YAML blueprint.

    The YAML format:
    ```yaml
    name: my-workflow
    steps:
      - agent: research
        next: strategy
      - agent: strategy
        next: risk
      - parallel:
          - agent: execution
          - agent: compliance
        next: recommender
      - agent: recommender
    ```

    Each step becomes a StrandsAgentTask. Parallel blocks become
    sfn.Parallel states.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        blueprint_yaml: str,
        agent_functions: dict[str, lambda_.IFunction],
        output_bucket_name: str,
        env_name: str,
        resource_prefix: str = "platform",
        manifest_lambda: lambda_.IFunction | None = None,
    ) -> None:
        super().__init__(scope, construct_id)

        prefix = resource_prefix
        blueprint = yaml.safe_load(blueprint_yaml)
        workflow_name = blueprint["name"]
        steps = blueprint["steps"]

        # Build chain of states
        chain_steps: list[sfn.IChainable] = []

        for step_def in steps:
            if "agent" in step_def:
                agent_name = step_def["agent"]
                params = step_def.get("input_mapping")
                task = StrandsAgentTask(
                    self,
                    f"Task-{agent_name}",
                    agent_function=agent_functions[agent_name],
                    agent_name=agent_name,
                    output_bucket_name=output_bucket_name,
                    env_name=env_name,
                    parameters=params,
                )
                chain_steps.append(task.task)

            elif "parallel" in step_def:
                branches = []
                for branch_def in step_def["parallel"]:
                    agent_name = branch_def["agent"]
                    params = branch_def.get("input_mapping")
                    task = StrandsAgentTask(
                        self,
                        f"Task-{agent_name}",
                        agent_function=agent_functions[agent_name],
                        agent_name=agent_name,
                        output_bucket_name=output_bucket_name,
                        env_name=env_name,
                        parameters=params,
                    )
                    branches.append(task.task)

                parallel = sfn.Parallel(
                    self,
                    f"Parallel-{'-'.join(b['agent'] for b in step_def['parallel'])}",
                    result_path="$.parallel_output",
                )
                for branch in branches:
                    parallel.branch(branch)
                chain_steps.append(parallel)

        # Chain all steps together
        definition = chain_steps[0]
        for step in chain_steps[1:]:
            definition = definition.next(step)

        # Append StoreManifest step if manifest Lambda is provided
        if manifest_lambda is not None:
            manifest_task = sfn_tasks.LambdaInvoke(
                self, "StoreManifest",
                lambda_function=manifest_lambda,
                payload=sfn.TaskInput.from_object({
                    "execution_id": sfn.JsonPath.string_at("$$.Execution.Name"),
                    "pipeline": sfn.JsonPath.string_at("$$.StateMachine.Name"),
                    "date": sfn.JsonPath.string_at("$.date"),
                    "results": sfn.JsonPath.string_at("$.results"),
                    "started_at": sfn.JsonPath.string_at("$.started_at"),
                }),
                result_selector={
                    "artifact_id": sfn.JsonPath.string_at("$.Payload.artifact_id"),
                    "s3_key": sfn.JsonPath.string_at("$.Payload.s3_key"),
                    "success": sfn.JsonPath.string_at("$.Payload.success"),
                },
                result_path="$.results._manifest",
            )
            definition = definition.next(manifest_task)

        # Log group for state machine
        log_group = logs.LogGroup(
            self,
            "SfnLogGroup",
            log_group_name=f"/aws/stepfunctions/{prefix}-{env_name}-{workflow_name}",
            retention=logs.RetentionDays.TWO_WEEKS
            if env_name == "dev"
            else logs.RetentionDays.THREE_MONTHS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        self.state_machine = sfn.StateMachine(
            self,
            "StateMachine",
            state_machine_name=f"{prefix}-{env_name}-{workflow_name}",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(1),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True,
            ),
        )
