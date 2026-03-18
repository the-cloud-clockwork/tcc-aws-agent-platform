"""Auto-scaling construct for Fargate services and Lambda provisioned concurrency."""
from __future__ import annotations

from constructs import Construct
from aws_cdk import (
    Duration,
    aws_ecs as ecs,
    aws_lambda as lambda_,
)


class FargateAutoScaling(Construct):
    """Configures auto-scaling for an ECS Fargate service.

    Scales based on:
    - CPU utilization (primary)
    - Memory utilization (secondary, scale-out only)

    Scale-in cooldown is longer than scale-out to prevent flapping.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        service: ecs.FargateService,
        min_tasks: int = 1,
        max_tasks: int = 5,
        target_cpu_percent: int = 70,
    ) -> None:
        super().__init__(scope, construct_id)

        self.scalable_target = service.auto_scale_task_count(
            min_capacity=min_tasks,
            max_capacity=max_tasks,
        )

        # Scale on CPU utilization
        self.scalable_target.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=target_cpu_percent,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2),
        )

        # Scale on memory utilization (higher threshold — memory is less volatile)
        self.scalable_target.scale_on_memory_utilization(
            "MemoryScaling",
            target_utilization_percent=80,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2),
        )


class LambdaProvisionedConcurrency(Construct):
    """Configures provisioned concurrency for a Lambda function.

    Creates an alias with provisioned concurrency.
    Use this for hot-path agents that need sub-second cold starts:
    - gap_detector (runs on schedule, latency-sensitive)
    - portfolio_recommender (extended thinking, expensive cold start)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        function: lambda_.Function,
        provisioned_concurrent_executions: int,
        alias_name: str = "active",
    ) -> None:
        super().__init__(scope, construct_id)

        if provisioned_concurrent_executions <= 0:
            # No-op: skip provisioned concurrency (dev env)
            self.alias = None
            return

        # Create a version from the current function code
        self.version = function.current_version

        # Create alias with provisioned concurrency
        self.alias = lambda_.Alias(
            self,
            "Alias",
            alias_name=alias_name,
            version=self.version,
            provisioned_concurrent_executions=provisioned_concurrent_executions,
        )
