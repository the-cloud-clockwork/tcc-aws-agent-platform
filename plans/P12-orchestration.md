# P12 — Step Functions Orchestration

## Objective
Build the Weekly Analysis Pipeline as a Step Functions Standard Workflow: EventBridge trigger → validate calendar → gap detection → parallel analysis (sentiment + technical) → strategy evaluation (Map state) → portfolio recommendation → mode routing → store results. Plus error handling, claim-check pattern, and CDK OrchestrationStack.

## Plane Tickets
ROOT-58

## Target Repo
`~/dev/tccw-agent-infra` (same as P11 — adds orchestration_stack.py content)

## Dependencies
P10 (agents deployed), P11 (infra stacks exist)

## Key Files to Create/Modify
```
tccw-agent-infra/
├── stacks/
│   └── orchestration_stack.py  # Full Step Functions + EventBridge
└── constructs/
    └── sfn_workflow.py         # May need updates from P11 skeleton
```

---

## Weekly Analysis Pipeline States

From Doc 1 Section 5.1 and Doc 2:

```
ValidateMarketCalendar (Lambda Task)
  → CheckTradingDay (Choice: is_trading_day? → NoOpComplete or continue)
    → FetchWatchlistGaps (Agent Task: gap_detector)
      → CheckGapCount (Choice: significant_gaps == 0? → NoOpComplete or continue)
        → ParallelAnalysis (Parallel: [SentimentAnalysis, TechnicalIndicators])
          → EvaluateStrategies (Map: iterate ranked_gaps, max_concurrency=10)
            → SynthesizeRecommendations (Agent Task: portfolio_recommender)
              → RouteByMode (Choice: EXECUTION_MODE==backtest? → StoreResults, else → OrderDecision)
                → OrderDecision (Choice: action==none? → StoreResults, else → CheckRiskLimits)
                  → CheckRiskLimits (Lambda Task: risk_engine)
                    → RouteByRisk (Choice: PASS → TwoFactorGate, FAIL → RiskViolationAlert)
                      → TwoFactorGate (Wait: waitForTaskToken, 5min heartbeat)
                        → SubmitOrder (Agent Task: execution_agent)
                          → SetTrailingStop (Lambda Task)
                            → StoreResults → Complete
```

For POC (backtest only), the workflow stops at RouteByMode → StoreResults. The order/risk/2FA path exists in the definition but is never reached in backtest mode.

---

## EventBridge Scheduler

- Rule: Monday 08:30 CET (Europe/Madrid)
- Target: Step Functions StartExecution
- Input: `{"execution_mode": "backtest", "date": "today"}`

---

## Claim-Check Pattern

- Every agent task stores output in S3 via artifacts-mcp
- Only `{artifact_id, s3_key, success}` passes through Step Functions state
- ResultSelector extracts these fields from Lambda response
- ResultPath appends to state without losing prior data

---

## Standard Retry/Catch on Every Agent Task

```python
task.add_retry(
    errors=["Lambda.ServiceException", "Lambda.TooManyRequestsException", "Bedrock.ThrottlingException"],
    interval=Duration.seconds(3),
    max_attempts=4,
    backoff_rate=2.0,
    jitter_strategy=sfn.JitterType.FULL,
)
task.add_catch(
    handler=notify_error_state,
    errors=["States.ALL"],
    result_path="$.error",
)
```

---

## CDK Implementation Notes

Use StrandsAgentTask construct from P11 for each agent invocation.
Use sfn.Choice for all routing decisions.
Use sfn.Parallel for ParallelAnalysis.
Use sfn.Map for EvaluateStrategies (max_concurrency=10).
Use sfn.Wait with IntegrationPattern.WAIT_FOR_TASK_TOKEN for 2FA gate.

---

## Full CDK Code: `stacks/orchestration_stack.py`

```python
"""
OrchestrationStack — Step Functions Weekly Analysis Pipeline.

Defines the complete state machine for the weekly analysis workflow:
EventBridge → ValidateCalendar → GapDetection → ParallelAnalysis
→ StrategyEvaluation → PortfolioRecommendation → ModeRouting → StoreResults.

Includes the full live-trading path (risk checks, 2FA gate, order submission)
which is present but unreachable in backtest mode.
"""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct


class OrchestrationStack(Stack):
    """Step Functions orchestration for the Weekly Analysis Pipeline."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str = "dev",
        agent_lambdas: dict[str, lambda_.IFunction],
        utility_lambdas: dict[str, lambda_.IFunction],
        artifacts_bucket: s3.IBucket,
        alert_topic: sns.ITopic,
        **kwargs,
    ) -> None:
        """
        Parameters
        ----------
        env_name : str
            Environment name (dev, staging, prod).
        agent_lambdas : dict
            Map of agent name → Lambda function. Expected keys:
            gap_detector, sentiment_analyst, technical_analyst,
            strategy_evaluator, portfolio_recommender, execution_agent.
        utility_lambdas : dict
            Map of utility name → Lambda function. Expected keys:
            validate_calendar, risk_engine, set_trailing_stop, store_results.
        artifacts_bucket : s3.IBucket
            S3 bucket for claim-check artifact storage.
        alert_topic : sns.ITopic
            SNS topic for error/risk-violation alerts.
        """
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.agent_lambdas = agent_lambdas
        self.utility_lambdas = utility_lambdas
        self.artifacts_bucket = artifacts_bucket
        self.alert_topic = alert_topic

        # -----------------------------------------------------------
        # Log group for Step Functions execution logs
        # -----------------------------------------------------------
        self.log_group = logs.LogGroup(
            self,
            "SfnLogGroup",
            log_group_name=f"/aws/vendedlogs/states/qitp-weekly-analysis-{env_name}",
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # -----------------------------------------------------------
        # Build all states
        # -----------------------------------------------------------
        definition = self._build_definition()

        # -----------------------------------------------------------
        # State Machine
        # -----------------------------------------------------------
        self.state_machine = sfn.StateMachine(
            self,
            "WeeklyAnalysisPipeline",
            state_machine_name=f"qitp-weekly-analysis-{env_name}",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            state_machine_type=sfn.StateMachineType.STANDARD,
            timeout=Duration.hours(2),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=self.log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True,
            ),
        )

        # Grant the state machine permission to invoke all Lambdas
        for fn in list(agent_lambdas.values()) + list(utility_lambdas.values()):
            fn.grant_invoke(self.state_machine)

        # Grant S3 read for claim-check references
        artifacts_bucket.grant_read(self.state_machine)

        # -----------------------------------------------------------
        # EventBridge Scheduler — Monday 08:30 CET
        # -----------------------------------------------------------
        self._create_eventbridge_rule()

    # ===============================================================
    # State Machine Definition
    # ===============================================================

    def _build_definition(self) -> sfn.IChainable:
        """Build the full state machine definition chain."""

        # --- Terminal / Shared States ---
        store_results = self._store_results_state()
        no_op_complete = sfn.Succeed(self, "NoOpComplete", comment="No action needed today")
        pipeline_complete = sfn.Succeed(self, "PipelineComplete", comment="Weekly analysis complete")
        notify_error = self._notify_error_state()
        risk_violation_alert = self._risk_violation_alert_state()

        # --- 1. ValidateMarketCalendar ---
        validate_calendar = self._lambda_task(
            "ValidateMarketCalendar",
            self.utility_lambdas["validate_calendar"],
            comment="Check if today is a trading day",
            payload={
                "date.$": "$.date",
            },
            result_selector={
                "is_trading_day.$": "$.Payload.is_trading_day",
                "market.$": "$.Payload.market",
                "next_trading_day.$": "$.Payload.next_trading_day",
            },
            result_path="$.calendar",
        )
        self._add_standard_retry_catch(validate_calendar, notify_error)

        # --- 2. CheckTradingDay ---
        check_trading_day = sfn.Choice(self, "CheckTradingDay", comment="Is today a trading day?")
        check_trading_day.when(
            sfn.Condition.boolean_equals("$.calendar.is_trading_day", False),
            no_op_complete,
        )

        # --- 3. FetchWatchlistGaps ---
        fetch_gaps = self._agent_task(
            "FetchWatchlistGaps",
            self.agent_lambdas["gap_detector"],
            comment="Detect gaps in watchlist using gap_detector agent",
            payload={
                "agent": "gap_detector",
                "date.$": "$.date",
                "execution_mode.$": "$.execution_mode",
            },
            result_selector={
                "artifact_id.$": "$.Payload.artifact_id",
                "s3_key.$": "$.Payload.s3_key",
                "success.$": "$.Payload.success",
                "significant_gaps.$": "$.Payload.significant_gaps",
                "ranked_gaps.$": "$.Payload.ranked_gaps",
            },
            result_path="$.gap_detection",
        )
        self._add_standard_retry_catch(fetch_gaps, notify_error)

        # --- 4. CheckGapCount ---
        check_gap_count = sfn.Choice(self, "CheckGapCount", comment="Any significant gaps found?")
        check_gap_count.when(
            sfn.Condition.number_equals("$.gap_detection.significant_gaps", 0),
            no_op_complete,
        )

        # --- 5. ParallelAnalysis (Sentiment + Technical) ---
        parallel_analysis = sfn.Parallel(
            self,
            "ParallelAnalysis",
            comment="Run sentiment and technical analysis in parallel",
            result_path="$.parallel_results",
        )

        sentiment_branch = self._agent_task(
            "SentimentAnalysis",
            self.agent_lambdas["sentiment_analyst"],
            comment="Sentiment analysis via sentiment_analyst agent",
            payload={
                "agent": "sentiment_analyst",
                "gap_artifact_id.$": "$.gap_detection.artifact_id",
                "gap_s3_key.$": "$.gap_detection.s3_key",
                "date.$": "$.date",
            },
            result_selector={
                "artifact_id.$": "$.Payload.artifact_id",
                "s3_key.$": "$.Payload.s3_key",
                "success.$": "$.Payload.success",
            },
            result_path="$.sentiment",
        )
        self._add_standard_retry_catch(sentiment_branch, notify_error)

        technical_branch = self._agent_task(
            "TechnicalIndicators",
            self.agent_lambdas["technical_analyst"],
            comment="Technical indicator analysis via technical_analyst agent",
            payload={
                "agent": "technical_analyst",
                "gap_artifact_id.$": "$.gap_detection.artifact_id",
                "gap_s3_key.$": "$.gap_detection.s3_key",
                "date.$": "$.date",
            },
            result_selector={
                "artifact_id.$": "$.Payload.artifact_id",
                "s3_key.$": "$.Payload.s3_key",
                "success.$": "$.Payload.success",
            },
            result_path="$.technical",
        )
        self._add_standard_retry_catch(technical_branch, notify_error)

        parallel_analysis.branch(sentiment_branch)
        parallel_analysis.branch(technical_branch)
        parallel_analysis.add_catch(notify_error, errors=["States.ALL"], result_path="$.error")

        # --- 6. EvaluateStrategies (Map over ranked_gaps) ---
        evaluate_strategies = sfn.Map(
            self,
            "EvaluateStrategies",
            comment="Evaluate strategy for each ranked gap (max 10 concurrent)",
            max_concurrency=10,
            items_path="$.gap_detection.ranked_gaps",
            parameters={
                "gap.$": "$$.Map.Item.Value",
                "index.$": "$$.Map.Item.Index",
                "parallel_results.$": "$.parallel_results",
                "date.$": "$.date",
                "execution_mode.$": "$.execution_mode",
            },
            result_path="$.strategy_results",
        )

        evaluate_single = self._agent_task(
            "EvaluateSingleStrategy",
            self.agent_lambdas["strategy_evaluator"],
            comment="Evaluate strategy for a single gap via strategy_evaluator agent",
            payload={
                "agent": "strategy_evaluator",
                "gap.$": "$.gap",
                "parallel_results.$": "$.parallel_results",
                "date.$": "$.date",
            },
            result_selector={
                "artifact_id.$": "$.Payload.artifact_id",
                "s3_key.$": "$.Payload.s3_key",
                "success.$": "$.Payload.success",
            },
        )
        self._add_standard_retry_catch(evaluate_single, notify_error)
        evaluate_strategies.iterator(evaluate_single)
        evaluate_strategies.add_catch(notify_error, errors=["States.ALL"], result_path="$.error")

        # --- 7. SynthesizeRecommendations ---
        synthesize = self._agent_task(
            "SynthesizeRecommendations",
            self.agent_lambdas["portfolio_recommender"],
            comment="Synthesize portfolio recommendations via portfolio_recommender agent",
            payload={
                "agent": "portfolio_recommender",
                "strategy_results.$": "$.strategy_results",
                "gap_detection.$": "$.gap_detection",
                "date.$": "$.date",
                "execution_mode.$": "$.execution_mode",
            },
            result_selector={
                "artifact_id.$": "$.Payload.artifact_id",
                "s3_key.$": "$.Payload.s3_key",
                "success.$": "$.Payload.success",
                "action.$": "$.Payload.action",
            },
            result_path="$.recommendation",
        )
        self._add_standard_retry_catch(synthesize, notify_error)

        # --- 8. RouteByMode ---
        route_by_mode = sfn.Choice(self, "RouteByMode", comment="Backtest or live execution?")
        route_by_mode.when(
            sfn.Condition.string_equals("$.execution_mode", "backtest"),
            store_results,
        )

        # --- 9. OrderDecision ---
        order_decision = sfn.Choice(self, "OrderDecision", comment="Does recommendation require an order?")
        order_decision.when(
            sfn.Condition.string_equals("$.recommendation.action", "none"),
            store_results,
        )

        # --- 10. CheckRiskLimits ---
        check_risk = self._lambda_task(
            "CheckRiskLimits",
            self.utility_lambdas["risk_engine"],
            comment="Validate order against risk limits",
            payload={
                "recommendation_artifact_id.$": "$.recommendation.artifact_id",
                "recommendation_s3_key.$": "$.recommendation.s3_key",
                "execution_mode.$": "$.execution_mode",
            },
            result_selector={
                "risk_status.$": "$.Payload.risk_status",
                "violations.$": "$.Payload.violations",
                "artifact_id.$": "$.Payload.artifact_id",
                "s3_key.$": "$.Payload.s3_key",
            },
            result_path="$.risk_check",
        )
        self._add_standard_retry_catch(check_risk, notify_error)

        # --- 11. RouteByRisk ---
        route_by_risk = sfn.Choice(self, "RouteByRisk", comment="Did risk check pass?")
        route_by_risk.when(
            sfn.Condition.string_equals("$.risk_check.risk_status", "FAIL"),
            risk_violation_alert,
        )

        # --- 12. TwoFactorGate (waitForTaskToken) ---
        two_factor_gate = tasks.LambdaInvoke(
            self,
            "TwoFactorGate",
            lambda_function=self.utility_lambdas["risk_engine"],
            comment="Wait for 2FA approval via task token callback (5min heartbeat)",
            integration_pattern=sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
            payload=sfn.TaskInput.from_object(
                {
                    "task_token": sfn.JsonPath.task_token,
                    "action": "request_2fa_approval",
                    "recommendation_artifact_id.$": "$.recommendation.artifact_id",
                    "recommendation_s3_key.$": "$.recommendation.s3_key",
                    "risk_check.$": "$.risk_check",
                }
            ),
            heartbeat=Duration.minutes(5),
            timeout=Duration.minutes(30),
            result_selector={
                "approved.$": "$.approved",
                "approver.$": "$.approver",
                "timestamp.$": "$.timestamp",
            },
            result_path="$.two_factor",
        )
        self._add_standard_retry_catch(two_factor_gate, notify_error)

        # --- 13. SubmitOrder ---
        submit_order = self._agent_task(
            "SubmitOrder",
            self.agent_lambdas["execution_agent"],
            comment="Submit order via execution_agent",
            payload={
                "agent": "execution_agent",
                "recommendation_artifact_id.$": "$.recommendation.artifact_id",
                "recommendation_s3_key.$": "$.recommendation.s3_key",
                "two_factor.$": "$.two_factor",
            },
            result_selector={
                "artifact_id.$": "$.Payload.artifact_id",
                "s3_key.$": "$.Payload.s3_key",
                "success.$": "$.Payload.success",
                "order_id.$": "$.Payload.order_id",
            },
            result_path="$.order",
        )
        self._add_standard_retry_catch(submit_order, notify_error)

        # --- 14. SetTrailingStop ---
        set_trailing_stop = self._lambda_task(
            "SetTrailingStop",
            self.utility_lambdas["set_trailing_stop"],
            comment="Configure trailing stop for submitted order",
            payload={
                "order_id.$": "$.order.order_id",
                "order_artifact_id.$": "$.order.artifact_id",
                "order_s3_key.$": "$.order.s3_key",
            },
            result_selector={
                "trailing_stop_id.$": "$.Payload.trailing_stop_id",
                "artifact_id.$": "$.Payload.artifact_id",
                "s3_key.$": "$.Payload.s3_key",
                "success.$": "$.Payload.success",
            },
            result_path="$.trailing_stop",
        )
        self._add_standard_retry_catch(set_trailing_stop, notify_error)

        # -----------------------------------------------------------
        # Wire the chain
        # -----------------------------------------------------------

        # StoreResults → PipelineComplete
        store_results.next(pipeline_complete)

        # RiskViolationAlert is terminal (Fail-like, but we use store + alert)
        # Already terminal via its own chain ending in Fail state

        # Live-trading path:
        # RouteByRisk (PASS) → TwoFactorGate → SubmitOrder → SetTrailingStop → StoreResults
        route_by_risk.when(
            sfn.Condition.string_equals("$.risk_check.risk_status", "PASS"),
            two_factor_gate,
        )
        route_by_risk.otherwise(notify_error)

        two_factor_gate.next(submit_order)
        submit_order.next(set_trailing_stop)
        set_trailing_stop.next(store_results)

        # OrderDecision (action != none) → CheckRiskLimits → RouteByRisk
        order_decision.otherwise(check_risk)
        check_risk.next(route_by_risk)

        # RouteByMode (not backtest) → OrderDecision
        route_by_mode.otherwise(order_decision)

        # Main chain
        validate_calendar.next(check_trading_day)
        check_trading_day.otherwise(fetch_gaps)
        fetch_gaps.next(check_gap_count)
        check_gap_count.otherwise(parallel_analysis)
        parallel_analysis.next(evaluate_strategies)
        evaluate_strategies.next(synthesize)
        synthesize.next(route_by_mode)

        return validate_calendar

    # ===============================================================
    # Helper: Lambda Task (utility lambdas)
    # ===============================================================

    def _lambda_task(
        self,
        id: str,
        fn: lambda_.IFunction,
        *,
        comment: str = "",
        payload: dict | None = None,
        result_selector: dict | None = None,
        result_path: str = "$",
    ) -> tasks.LambdaInvoke:
        """Create a LambdaInvoke task with claim-check result selection."""
        task_kwargs: dict = {
            "lambda_function": fn,
            "comment": comment,
            "retry_on_service_exceptions": False,  # We add our own retries
        }
        if payload:
            task_kwargs["payload"] = sfn.TaskInput.from_object(payload)
        if result_selector:
            task_kwargs["result_selector"] = result_selector
        if result_path != "$":
            task_kwargs["result_path"] = result_path

        return tasks.LambdaInvoke(self, id, **task_kwargs)

    # ===============================================================
    # Helper: Agent Task (agent lambdas — same pattern, named differently)
    # ===============================================================

    def _agent_task(
        self,
        id: str,
        fn: lambda_.IFunction,
        *,
        comment: str = "",
        payload: dict | None = None,
        result_selector: dict | None = None,
        result_path: str = "$",
    ) -> tasks.LambdaInvoke:
        """
        Create a LambdaInvoke task for a Strands agent.

        Uses the same underlying LambdaInvoke but with longer timeout
        (agents may take longer due to Bedrock inference).
        """
        task_kwargs: dict = {
            "lambda_function": fn,
            "comment": comment,
            "timeout": Duration.minutes(10),
            "retry_on_service_exceptions": False,
        }
        if payload:
            task_kwargs["payload"] = sfn.TaskInput.from_object(payload)
        if result_selector:
            task_kwargs["result_selector"] = result_selector
        if result_path != "$":
            task_kwargs["result_path"] = result_path

        return tasks.LambdaInvoke(self, id, **task_kwargs)

    # ===============================================================
    # Helper: Standard Retry + Catch
    # ===============================================================

    def _add_standard_retry_catch(
        self,
        task: tasks.LambdaInvoke,
        error_handler: sfn.IChainable,
    ) -> None:
        """Add standard retry and catch to a task state."""
        task.add_retry(
            errors=[
                "Lambda.ServiceException",
                "Lambda.TooManyRequestsException",
                "Bedrock.ThrottlingException",
            ],
            interval=Duration.seconds(3),
            max_attempts=4,
            backoff_rate=2.0,
            jitter_strategy=sfn.JitterType.FULL,
        )
        task.add_catch(
            handler=error_handler,
            errors=["States.ALL"],
            result_path="$.error",
        )

    # ===============================================================
    # Helper: StoreResults state
    # ===============================================================

    def _store_results_state(self) -> tasks.LambdaInvoke:
        """Create the StoreResults Lambda task."""
        store = self._lambda_task(
            "StoreResults",
            self.utility_lambdas["store_results"],
            comment="Persist final results to S3 and DynamoDB",
            payload={
                "pipeline_state.$": "$",
            },
            result_selector={
                "artifact_id.$": "$.Payload.artifact_id",
                "s3_key.$": "$.Payload.s3_key",
                "success.$": "$.Payload.success",
            },
            result_path="$.final_results",
        )
        # StoreResults gets its own retry/catch pointing to notify
        notify_error = self._notify_error_state()
        self._add_standard_retry_catch(store, notify_error)
        return store

    # ===============================================================
    # Helper: Error notification states
    # ===============================================================

    def _notify_error_state(self) -> sfn.Chain:
        """Create an SNS publish → Fail chain for error notification."""
        publish = tasks.SnsPublish(
            self,
            "NotifyError",
            topic=self.alert_topic,
            message=sfn.TaskInput.from_json_path_at("$.error"),
            subject=f"QITP Pipeline Error [{self.env_name}]",
            result_path=sfn.JsonPath.DISCARD,
        )
        fail = sfn.Fail(
            self,
            "PipelineFailed",
            cause="Pipeline encountered an unrecoverable error",
            error="PipelineError",
        )
        return publish.next(fail)

    def _risk_violation_alert_state(self) -> sfn.Chain:
        """Create an SNS publish → Fail chain for risk violations."""
        publish = tasks.SnsPublish(
            self,
            "RiskViolationAlert",
            topic=self.alert_topic,
            message=sfn.TaskInput.from_object(
                {
                    "alert": "RISK_VIOLATION",
                    "violations.$": "$.risk_check.violations",
                    "recommendation_artifact_id.$": "$.recommendation.artifact_id",
                }
            ),
            subject=f"QITP Risk Violation [{self.env_name}]",
            result_path=sfn.JsonPath.DISCARD,
        )
        fail = sfn.Fail(
            self,
            "RiskViolationFailed",
            cause="Order rejected due to risk limit violation",
            error="RiskViolation",
        )
        return publish.next(fail)

    # ===============================================================
    # EventBridge Rule
    # ===============================================================

    def _create_eventbridge_rule(self) -> events.Rule:
        """Create the Monday 08:30 CET EventBridge rule."""
        rule = events.Rule(
            self,
            "WeeklyAnalysisSchedule",
            rule_name=f"qitp-weekly-analysis-{self.env_name}",
            description="Trigger weekly analysis pipeline every Monday at 08:30 CET",
            # cron: 07:30 UTC = 08:30 CET (UTC+1) / 08:30 CEST is 06:30 UTC
            # Using 07:30 UTC as CET (winter). For year-round accuracy,
            # consider using EventBridge Scheduler with timezone support.
            schedule=events.Schedule.cron(
                minute="30",
                hour="7",
                week_day="MON",
            ),
            enabled=self.env_name == "prod",  # Only enabled in prod
        )

        rule.add_target(
            targets.SfnStateMachine(
                self.state_machine,
                input=events.RuleTargetInput.from_object(
                    {
                        "execution_mode": "backtest",
                        "date": events.EventField.time,
                    }
                ),
            )
        )

        return rule
```

> **Note on timezone**: The cron expression uses `07:30 UTC` which equals `08:30 CET` during standard time. For year-round correctness (handling CET/CEST transitions), migrate to **EventBridge Scheduler** which supports the `Europe/Madrid` timezone natively. This is a known follow-up item.

---

## CDK App Integration

In the CDK app entry point (e.g., `app.py`), instantiate the stack:

```python
from stacks.orchestration_stack import OrchestrationStack

# ... after P11 stacks are created ...

orchestration = OrchestrationStack(
    app,
    f"Orchestration-{env_name}",
    env_name=env_name,
    agent_lambdas={
        "gap_detector": agents_stack.gap_detector_fn,
        "sentiment_analyst": agents_stack.sentiment_analyst_fn,
        "technical_analyst": agents_stack.technical_analyst_fn,
        "strategy_evaluator": agents_stack.strategy_evaluator_fn,
        "portfolio_recommender": agents_stack.portfolio_recommender_fn,
        "execution_agent": agents_stack.execution_agent_fn,
    },
    utility_lambdas={
        "validate_calendar": infra_stack.validate_calendar_fn,
        "risk_engine": infra_stack.risk_engine_fn,
        "set_trailing_stop": infra_stack.set_trailing_stop_fn,
        "store_results": infra_stack.store_results_fn,
    },
    artifacts_bucket=infra_stack.artifacts_bucket,
    alert_topic=infra_stack.alert_topic,
    env=cdk_env,
)
```

---

## Acceptance Criteria

- [ ] `cdk synth` produces valid Step Functions ASL
- [ ] State machine has all states from the pipeline diagram
- [ ] Choice states route correctly (trading day, gap count, mode, risk)
- [ ] Parallel state runs sentiment + technical in parallel
- [ ] Map state iterates ranked_gaps with max_concurrency=10
- [ ] Every agent task has retry + catch
- [ ] EventBridge rule triggers on Monday 08:30 CET
- [ ] Claim-check pattern: only artifact_id/s3_key in state

---

## Test Plan

```bash
cd ~/dev/tccw-agent-infra
cdk synth Orchestration-dev
# Verify ASL JSON has all expected states

# Validate state names exist in synthesized output
python -c "
import json, sys
with open('cdk.out/Orchestration-dev.template.json') as f:
    t = json.load(f)
# Find the state machine definition in the template
for key, val in t['Resources'].items():
    if val['Type'] == 'AWS::StepFunctions::StateMachine':
        definition = json.loads(val['Properties']['DefinitionString']['Fn::Join'][1]
            if 'Fn::Join' in val['Properties'].get('DefinitionString', {})
            else '{}')
        states = definition.get('States', {})
        expected = [
            'ValidateMarketCalendar', 'CheckTradingDay', 'FetchWatchlistGaps',
            'CheckGapCount', 'ParallelAnalysis', 'EvaluateStrategies',
            'SynthesizeRecommendations', 'RouteByMode', 'OrderDecision',
            'CheckRiskLimits', 'RouteByRisk', 'TwoFactorGate',
            'SubmitOrder', 'SetTrailingStop', 'StoreResults',
        ]
        for s in expected:
            assert s in str(t), f'Missing state: {s}'
        print('All expected states found in template')
        break
"
```

---

## Agent Instructions

This is the deterministic backbone of the entire platform. Every state transition must be auditable. Use CDK's high-level Step Functions constructs (not raw ASL JSON). The claim-check pattern is critical — agent outputs MUST go to S3, never inline in state. The 2FA gate and risk engine states exist in the definition even for POC — they just won't be reached in backtest mode.

**Key implementation constraints:**

1. **Claim-check is non-negotiable.** Every `result_selector` must extract only `artifact_id`, `s3_key`, and `success`. No raw analysis data in state.
2. **ResultPath isolation.** Each state appends to `$` via a unique `result_path` (e.g., `$.gap_detection`, `$.recommendation`). Never overwrite the full state.
3. **Retry before catch.** Retries handle transient errors (Lambda throttle, Bedrock throttle). Catch handles everything else and routes to SNS + Fail.
4. **Map concurrency.** `max_concurrency=10` on EvaluateStrategies prevents Bedrock throttling while maintaining throughput.
5. **2FA timeout.** The TwoFactorGate has a 5-minute heartbeat and 30-minute total timeout. If no callback arrives, the execution fails gracefully.
6. **EventBridge timezone.** The CET schedule uses UTC offset. Migrate to EventBridge Scheduler with `Europe/Madrid` timezone for DST correctness as a follow-up.
