"""Observability stack: CloudWatch dashboards, X-Ray, SNS alerts, log groups.

Generic agent platform observability. Domain-specific metrics and widgets
should be added by the downstream project, not here.

Includes:
- CloudWatch dashboard with generic agent/MCP/pipeline widgets
- SNS topic for alerts
- X-Ray tracing group
- Metric alarms for agents and MCPs
"""
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_cloudwatch as cw,
)
from aws_cdk import (
    aws_cloudwatch_actions as cw_actions,
)
from aws_cdk import (
    aws_ecs as ecs,
)
from aws_cdk import (
    aws_kms as kms,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_sns as sns,
)
from aws_cdk import (
    aws_ssm as ssm,
)
from aws_cdk import (
    aws_xray as xray,
)
from constructs import Construct


class ObservabilityStack(Stack):
    """Generic observability stack for the agent platform.

    Creates:
    1. CloudWatch log groups for pipeline
    2. SNS topic for alerts
    3. X-Ray tracing group
    4. CloudWatch dashboard with generic widgets
    5. Metric alarms for error rates, latency, CPU
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        config: dict | None = None,
        agent_functions: dict[str, lambda_.Function] | None = None,
        mcp_services: dict[str, ecs.FargateService] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        config = config or {}
        agent_functions = agent_functions or {}
        mcp_services = mcp_services or {}
        prefix = config.get("resource_prefix", "platform")
        ssm_root = config.get("ssm_root_path", f"/{prefix}/{env_name}")
        metric_namespace = f"{prefix.upper()}/{env_name}"

        # -- Log Groups (config-driven) ------------------------------------

        self.log_groups: dict[str, logs.LogGroup] = {}

        # Pipeline log group
        self.pipeline_log_group = logs.LogGroup(
            self,
            "LogGroup-pipeline",
            log_group_name=f"/{prefix}/{env_name}/pipeline",
            retention=logs.RetentionDays.ONE_YEAR,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # -- SNS Alert Topic -----------------------------------------------

        alert_key = kms.Key(
            self,
            "AlertTopicKey",
            alias=f"alias/{prefix}-{env_name}-alert-topic",
            description="KMS key for SNS alert topic encryption",
            enable_key_rotation=True,
        )

        self.alert_topic = sns.Topic(
            self,
            "AlertTopic",
            topic_name=f"{prefix}-{env_name}-alerts",
            display_name=f"{prefix} {env_name} Alerts",
            master_key=alert_key,
        )

        # Export topic ARN to SSM for other stacks
        ssm.StringParameter(
            self,
            "AlertTopicArnParam",
            parameter_name=f"{ssm_root}/alert-topic-arn",
            string_value=self.alert_topic.topic_arn,
        )

        # -- X-Ray Tracing Group -------------------------------------------

        self.xray_group = xray.CfnGroup(
            self,
            "XRayGroup",
            group_name=f"{prefix}-{env_name}",
            filter_expression=f'annotation.environment == "{env_name}"',
        )

        # -- Agent Lambda Alarms -------------------------------------------

        agent_widgets: list[cw.IWidget] = []

        for name, fn in agent_functions.items():
            error_alarm = cw.Alarm(
                self,
                f"ErrorAlarm-{name}",
                alarm_name=f"{prefix}-{env_name}-agent-{name}-errors",
                metric=fn.metric_errors(period=Duration.minutes(5)),
                threshold=3,
                evaluation_periods=2,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            )
            error_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

            duration_alarm = cw.Alarm(
                self,
                f"DurationAlarm-{name}",
                alarm_name=f"{prefix}-{env_name}-agent-{name}-duration",
                metric=fn.metric_duration(
                    period=Duration.minutes(5),
                    statistic="p99",
                ),
                threshold=600_000,  # 10 minutes in ms
                evaluation_periods=2,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            )
            duration_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

            agent_widgets.append(
                cw.GraphWidget(
                    title=f"Agent: {name}",
                    left=[
                        fn.metric_invocations(period=Duration.minutes(5)),
                        fn.metric_errors(period=Duration.minutes(5)),
                    ],
                    right=[
                        fn.metric_duration(period=Duration.minutes(5)),
                    ],
                    width=12,
                )
            )

        # -- MCP Service Alarms --------------------------------------------

        mcp_widgets: list[cw.IWidget] = []

        for name, service in mcp_services.items():
            cpu_alarm = cw.Alarm(
                self,
                f"CpuAlarm-{name}",
                alarm_name=f"{prefix}-{env_name}-mcp-{name}-cpu",
                metric=service.metric_cpu_utilization(
                    period=Duration.minutes(5),
                ),
                threshold=80,
                evaluation_periods=3,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            )
            cpu_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

            mcp_widgets.append(
                cw.GraphWidget(
                    title=f"MCP: {name}",
                    left=[
                        service.metric_cpu_utilization(period=Duration.minutes(5)),
                    ],
                    right=[
                        service.metric_memory_utilization(period=Duration.minutes(5)),
                    ],
                    width=12,
                )
            )

        # -- Custom Metrics (generic only) ---------------------------------

        token_cost_metric = cw.Metric(
            namespace=metric_namespace,
            metric_name="TokenCostUSD",
            dimensions_map={"Service": "agents"},
            period=Duration.hours(1),
            statistic="Sum",
        )

        pipeline_started_metric = cw.Metric(
            namespace=metric_namespace,
            metric_name="PipelineStarted",
            period=Duration.hours(1),
            statistic="Sum",
        )
        pipeline_completed_metric = cw.Metric(
            namespace=metric_namespace,
            metric_name="PipelineCompleted",
            period=Duration.hours(1),
            statistic="Sum",
        )
        pipeline_failed_metric = cw.Metric(
            namespace=metric_namespace,
            metric_name="PipelineFailed",
            period=Duration.hours(1),
            statistic="Sum",
        )

        # -- Dashboard (generic widgets) -----------------------------------

        self.dashboard = cw.Dashboard(
            self,
            "Dashboard",
            dashboard_name=f"{prefix}-{env_name}-overview",
            widgets=[
                # Row 1: Title
                [
                    cw.TextWidget(
                        markdown=f"# Agent Platform -- {env_name.upper()}",
                        width=24,
                        height=1,
                    )
                ],
                # Row 2: Pipeline Executions + Agent Latency
                [
                    cw.GraphWidget(
                        title="Pipeline Executions",
                        left=[
                            pipeline_started_metric,
                            pipeline_completed_metric,
                        ],
                        right=[pipeline_failed_metric],
                        width=12,
                        height=6,
                    ),
                    cw.GraphWidget(
                        title="Agent Latency (p50/p99)",
                        left=[
                            cw.Metric(
                                namespace=metric_namespace,
                                metric_name="AgentLatencyMs",
                                statistic="p50",
                                period=Duration.minutes(15),
                            ),
                            cw.Metric(
                                namespace=metric_namespace,
                                metric_name="AgentLatencyMs",
                                statistic="p99",
                                period=Duration.minutes(15),
                            ),
                        ],
                        width=12,
                        height=6,
                    ),
                ],
                # Row 3: Token Cost
                [
                    cw.GraphWidget(
                        title="Token Cost (USD/hour)",
                        left=[token_cost_metric],
                        width=24,
                        height=6,
                    ),
                ],
                # Row 4: Agent detail widgets
                [
                    cw.TextWidget(
                        markdown="## Agent Lambda Functions",
                        width=24,
                        height=1,
                    )
                ],
                agent_widgets if agent_widgets else [],
                # Row 5: MCP detail widgets
                [
                    cw.TextWidget(
                        markdown="## MCP Fargate Services",
                        width=24,
                        height=1,
                    )
                ],
                mcp_widgets if mcp_widgets else [],
            ],
        )
