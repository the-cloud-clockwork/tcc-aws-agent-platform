"""Tests for CDK constructs: StrandsAgentTask, SfnWorkflow."""
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    assertions,
)

from constructs_.strands_agent import StrandsAgentTask
from constructs_.sfn_workflow import SfnWorkflow


class TestStrandsAgentTask:
    def test_creates_lambda_invoke_task(self):
        app = cdk.App()
        stack = Stack(app, "TestStack")

        fn = lambda_.Function(
            stack, "TestFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_inline("def handler(e,c): pass"),
        )

        construct = StrandsAgentTask(
            stack, "TestTask",
            agent_function=fn,
            agent_name="test-agent",
            output_bucket_name="test-bucket",
            env_name="dev",
        )

        assert construct.agent_name == "test-agent"
        assert construct.task is not None
        assert construct.fail_state is not None


class TestSfnWorkflow:
    def test_creates_state_machine_from_yaml(self):
        app = cdk.App()
        stack = Stack(app, "TestStack")

        fn_a = lambda_.Function(
            stack, "FnA",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_inline("def handler(e,c): pass"),
        )
        fn_b = lambda_.Function(
            stack, "FnB",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_inline("def handler(e,c): pass"),
        )

        blueprint_yaml = """
name: test-workflow
steps:
  - agent: agent_a
    next: agent_b
  - agent: agent_b
"""

        workflow = SfnWorkflow(
            stack, "TestWorkflow",
            blueprint_yaml=blueprint_yaml,
            agent_functions={"agent_a": fn_a, "agent_b": fn_b},
            output_bucket_name="test-bucket",
            env_name="dev",
        )

        assert workflow.state_machine is not None
        template = assertions.Template.from_stack(stack)
        template.resource_count_is("AWS::StepFunctions::StateMachine", 1)

    def test_creates_parallel_workflow(self):
        app = cdk.App()
        stack = Stack(app, "TestStack")

        fns = {}
        for name in ("agent_a", "agent_b", "agent_c"):
            fns[name] = lambda_.Function(
                stack, f"Fn-{name}",
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler="handler.handler",
                code=lambda_.Code.from_inline("def handler(e,c): pass"),
            )

        blueprint_yaml = """
name: parallel-workflow
steps:
  - parallel:
      - agent: agent_a
      - agent: agent_b
    next: agent_c
  - agent: agent_c
"""

        workflow = SfnWorkflow(
            stack, "TestWorkflow",
            blueprint_yaml=blueprint_yaml,
            agent_functions=fns,
            output_bucket_name="test-bucket",
            env_name="dev",
        )

        assert workflow.state_machine is not None
