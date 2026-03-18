"""CDK tests for ObservabilityStack."""
from __future__ import annotations

import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from stacks.observability_stack import ObservabilityStack


def _default_config():
    return {
        "resource_prefix": "platform",
        "ssm_root_path": "/platform/dev",
        "service_discovery_namespace": "platform.local",
    }


@pytest.fixture
def app():
    return cdk.App()


@pytest.fixture
def env():
    return cdk.Environment(account="835618032093", region="eu-west-1")


class TestObservabilityStack:
    def test_creates_sns_topic(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs", env=env, env_name="dev", config=_default_config(),
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SNS::Topic",
            {"TopicName": "platform-dev-alerts"},
        )

    def test_creates_dashboard(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs2", env=env, env_name="dev", config=_default_config(),
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::CloudWatch::Dashboard",
            {"DashboardName": "platform-dev-overview"},
        )

    def test_creates_xray_group(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs3", env=env, env_name="dev", config=_default_config(),
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::XRay::Group",
            {"GroupName": "platform-dev"},
        )

    def test_creates_pipeline_log_group(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs4", env=env, env_name="dev", config=_default_config(),
        )
        template = assertions.Template.from_stack(stack)
        # 1 pipeline log group only (no hardcoded agent/MCP log groups)
        template.resource_count_is("AWS::Logs::LogGroup", 1)

    def test_ssm_parameter_for_topic_arn(self, app, env) -> None:
        stack = ObservabilityStack(
            app, "TestObs5", env=env, env_name="dev", config=_default_config(),
        )
        template = assertions.Template.from_stack(stack)
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Name": "/platform/dev/alert-topic-arn"},
        )
