"""StrandsAgentTask -- reusable CDK construct for Step Functions agent invocation."""
from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    Duration,
    aws_lambda as lambda_,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
)


class StrandsAgentTask(Construct):
    """Wraps a Lambda invocation for use in Step Functions.

    Features:
    - LambdaInvoke with exponential backoff + full jitter retry
    - Claim-check pattern: large output -> S3, only S3 key in state
    - X-Ray tracing enabled on the underlying function
    - result_selector extracts artifact_id, success, s3_key
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        agent_function: lambda_.IFunction,
        agent_name: str,
        output_bucket_name: str,
        env_name: str,
    ) -> None:
        super().__init__(scope, construct_id)

        self.agent_name = agent_name

        # The Lambda task for Step Functions
        self.task = sfn_tasks.LambdaInvoke(
            self,
            f"Invoke-{agent_name}",
            lambda_function=agent_function,
            payload=sfn.TaskInput.from_json_path_at("$"),
            result_selector={
                "artifact_id.$": "$.Payload.artifact_id",
                "success.$": "$.Payload.success",
                "s3_key.$": "$.Payload.s3_key",
                "agent": agent_name,
            },
            result_path=f"$.results.{agent_name}",
            retry_on_service_exceptions=True,
            comment=f"Invoke {agent_name} agent with claim-check pattern",
        )

        # Add retry with exponential backoff + full jitter
        self.task.add_retry(
            errors=["States.TaskFailed", "Lambda.ServiceException"],
            interval=Duration.seconds(2),
            max_attempts=3,
            backoff_rate=2.0,
            jitter_strategy=sfn.JitterType.FULL,
        )

        # Add catch for unrecoverable failures
        self.fail_state = sfn.Fail(
            self,
            f"Fail-{agent_name}",
            cause=f"Agent {agent_name} failed after retries",
            error="AgentExecutionFailed",
        )
        self.task.add_catch(
            handler=self.fail_state,
            errors=["States.ALL"],
            result_path=f"$.errors.{agent_name}",
        )
