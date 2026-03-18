QUANTITATIVE INTELLIGENCE TRADING PLATFORM
Document 7: Operations & Observability Runbook
2FA Gate • Circuit Breakers • Audit Log • Alerting • Langfuse • CNMV Compliance • Incident Playbooks


# 1. Observability Stack
QITP operates a multi-layer observability stack. Every agent invocation, tool call, order attempt, risk decision, prompt version, and state transition must be traceable end-to-end. This is non-negotiable for a system managing real money.

## 1.1 Observability Layers

## 1.2 Langfuse Integration
Every Strands agent invocation is instrumented with Langfuse for prompt tracking and cost monitoring. Langfuse is already running on Anton. QITP will use a dedicated Langfuse project.
Langfuse SDK injected via Strands hook: AfterModelInvocationEvent -> log_to_langfuse()
Each trace tagged: agent_id, prompt_id, prompt_version, execution_mode, symbol, strategy_id
Token cost computed per invocation using Bedrock pricing for the active model
Weekly cost report: total tokens spent by agent, by strategy, by execution mode
Prompt A/B testing: Langfuse supports multiple prompt versions in parallel — used for prompt iteration validation

## 1.3 Structured Log Schema
Every Lambda and AgentCore execution emits a structured JSON log entry with these mandatory fields:
{
"timestamp": "2025-03-10T08:45:23.123Z",
"trace_id": "1-abc123",            // X-Ray trace ID
"execution_id": "sfn-exec-xyz",    // Step Functions execution ID
"agent_id": "gap_detection_agent",
"agent_version": "1.2.0",
"prompt_id": "gap_detector_v2",
"prompt_version": "2.1.0",
"execution_mode": "paper",
"symbol": "NVDA",                  // null if not symbol-specific
"strategy_id": null,               // if applicable
"action": "agent_invocation",
"duration_ms": 12430,
"input_tokens": 2847,
"output_tokens": 312,
"tool_calls": ["get_watchlist_gaps", "create_artifact"],
"success": true,
"error_code": null,
"artifact_id": "art-uuid-123"      // if artifact produced
}


# 2. Financial Audit Log
The audit log is the permanent, immutable record of every financial decision made by QITP. DynamoDB with point-in-time recovery enabled. Never deleted. Critical for compliance, debugging, and post-trade analysis.

## 2.1 Audit Log Schema (DynamoDB)
Table: qitp_audit_log
PK: audit_id (UUID)
SK: timestamp (ISO 8601)
GSI1: execution_mode + date  (query all events for a given date in a mode)
GSI2: symbol + date          (query all events for a given symbol)

## 2.2 Event Types Logged


# 3. Alerting System
All alerts route through CloudWatch Alarms -> SNS Topic -> Telegram Bot. The operator receives all alerts on their phone. Alerts are classified by severity: INFO (weekly reports), WARN (anomalies), CRITICAL (halt conditions).

## 3.1 Alert Definitions


# 4. Circuit Breaker Playbook


## 4.1 Daily Loss Circuit Breaker (-3%)
### Trigger Condition
Portfolio NAV drops more than 3% below the day's opening NAV at any point during market hours.
### Automated Response
Risk Engine detects daily_pnl_pct < -3.0
circuit_breaker_active = TRUE written to DynamoDB risk_state table
All subsequent place_order calls return CircuitBreakerActiveError
CRITICAL alert sent via Telegram
Audit log event: CIRCUIT_BREAKER_TRIGGERED
Trailing Stop Manager continues running — existing stops can still execute
### Recovery Procedure
Review Telegram alert and audit log for root cause
Next trading day 08:00 CET: circuit_breaker_active auto-resets for daily breaker
If desired, run backtest retrospective to understand what caused the loss
Optionally tighten risk parameters before re-enabling

## 4.2 Drawdown Circuit Breaker (-10%)
### Trigger Condition
Portfolio NAV drops more than 10% below the peak NAV recorded since system inception (or last manual reset).
### Automated Response
Same as daily breaker but permanent_halt = TRUE
Does NOT auto-reset — requires manual operator intervention
CRITICAL alert sent every 24 hours until manually cleared
### Recovery Procedure (Manual)
Conduct full strategy review — why did drawdown exceed 10%?
Run backtests with current strategy parameters to understand failure mode
Adjust strategy parameters or disable failing strategies
Manually set permanent_halt = FALSE via CLI command: qitp risk reset-drawdown-breaker --confirm
Run one full backtest cycle to verify changes before re-enabling paper/live mode


# 5. Incident Playbooks

## 5.1 Playbook: IBKR Connection Lost During Trading Hours

### Detection
ibkr-mcp health check fails 3 consecutive times (1-minute intervals)
CloudWatch alarm triggers -> SNS -> Telegram: 'WARN: IBKR Gateway connection lost'
### Automated Response
ibkr-mcp attempts auto-reconnect every 30 seconds
All new order requests queued (not dropped) — processed when connection restored
Trailing Stop Manager skips iteration if IBKR unavailable — does not error
### Manual Response if Auto-Reconnect Fails After 15 Minutes
Check IBKR status page: https://www.interactivebrokers.com/en/trading/status.php
Restart IBKR Gateway container: aws ecs update-service --cluster qitp-{env} --service ibkr-gateway --force-new-deployment
If IBKR scheduled maintenance: no action needed, wait for window to pass
If connectivity issue: check VPC NAT gateway, security groups, IBKR IP allowlists
After reconnect: verify all open positions match IBKR account positions (reconciliation check)

## 5.2 Playbook: Agent Loop Infinite Iteration

### Detection
Langfuse trace shows >8 tool calls for a single agent invocation
Lambda duration approaching 15-minute timeout
CloudWatch alarm: agent_execution_duration_seconds > 300
### Automated Response
max_iterations hard limit terminates the agent at configured limit (5-8 depending on agent)
max_execution_time terminates agent regardless of iteration count
Step Functions catches Lambda timeout -> retry with exponential backoff (max 3 attempts)
### Investigation
Check Langfuse trace: which tools were being called repeatedly?
Review agent prompt: is there ambiguity causing the model to loop?
Check tool responses: was a tool returning errors causing retry behavior?
Update prompt in Prompt Registry if reasoning is clearly incorrect
Validate fix in backtest before deploying to paper/live

## 5.3 Playbook: Unexpected Order Submitted

### First Response
Immediately check IBKR account — is there an unexpected open position?
If position exists and is unwanted: manually close via IBKR client portal (not via QITP)
Set circuit_breaker_active = TRUE manually: qitp risk set-circuit-breaker --reason 'investigation'
### Investigation
Query audit log for ORDER_SUBMITTED events without preceding 2FA_APPROVED event
Check execution mode — was system accidentally set to paper but connected to live account?
Review Step Functions execution history for the affected execution
Check 2fa-mcp logs — was request_approval() called?
File incident report with full timeline


# 6. Performance Monitoring Dashboard

## 6.1 CloudWatch Dashboard: QITP-{env}-Overview
Main operational dashboard. 8 widgets. Visible from single screen.

## 6.2 Key Performance Indicators (Weekly Review)
Reviewed every Friday after P&L report. Manual review process:
Compare this week's realized P&L vs backtest prediction for same period
Check win rate vs strategy historical win rate — significant deviation triggers investigation
Review Langfuse for any prompts with high token usage — optimize if >50% above baseline
Review Risk Engine FAIL events — are any portfolio constraints being repeatedly hit?
Check all closed positions for slippage above 0.3% — systematic high slippage = execution problem
Review any WARN alerts from the week — any patterns emerging?


# 7. Regulatory Compliance (Spain / CNMV)

## 7.1 MiFID II Best Execution Logging
All orders executed by QITP must satisfy MiFID II best execution requirements. IBKR handles venue routing; QITP is responsible for logging.
Every order logged with: timestamp (milliseconds), symbol, ISIN, venue/exchange, price, quantity, order type, execution time
Rationale logged: which signals drove the order (gap score, sentiment score, strategy, composite score)
All audit log entries retained for 5 years minimum (DynamoDB TTL set to 5 years)
Annual review: verify IBKR execution quality report matches QITP execution records

## 7.2 Spanish IRPF Capital Gains Reporting
QITP must support generation of Spanish tax reporting data for IRPF (Impuesto sobre la Renta de las Personas Fisicas) capital gains declarations.
All closed positions logged with: acquisition date, acquisition price, disposal date, disposal price, net P&L in EUR, commissions
Annual tax report generated in December: list all closed positions with IRPF-required fields
Tax rates (2025): up to EUR 6,000 = 19%; EUR 6,001-50,000 = 21%; EUR 50,001-200,000 = 23%; over EUR 200,000 = 26%
Report exported as CSV compatible with Spanish tax declaration software (Renta Web)

## 7.3 CNMV Short Selling Restrictions
CNMV has authority to impose emergency short-sell restrictions on specific Spanish stocks during periods of market stress. QITP Risk Engine must check before approving any short order on IBEX35 symbols.
Before any SSHORT order on a Spanish stock: call CNMV emergency measures endpoint (or cached daily update)
If symbol is on active short-sell restriction list: reject with CNMVShortSellRestriction error
Cache refreshed daily at 08:00 CET — forced refresh on any CNMV restriction announcement
Restriction list stored in DynamoDB: symbol, restriction_start, restriction_end, authority

## 7.4 ESMA CFD Leverage Limits
European Securities and Markets Authority (ESMA) imposes leverage limits on CFD trading for retail clients.

Note: QITP Phase 1 trades only standard equities and ETFs (not CFDs). The above is pre-implemented for when leveraged products are considered in future phases.


# 8. Deployment Operations

## 8.1 Environment Promotion Process

### dev -> paper
All CI checks pass (lint, type check, unit tests, blueprint validation)
Integration test suite passes against dev environment
Create GitHub release tag: v{major}.{minor}.{patch}
GitHub Actions CD pipeline builds Docker images -> pushes to ECR
CDK diff reviewed — no unexpected resource changes
cdk deploy --context env=paper
Paper smoke test: run full pipeline in paper mode against current date
Verify 2FA gate works: test order request arrives on Telegram, approve/reject both work

### live promotion (after minimum 4 weeks paper trading)
Review paper trading results: Sharpe > 0, no circuit breaker hits, win rate > 40%
Manual approval in GitHub Actions 'promote-to-live' workflow
IBKR: ensure live account has correct permissions and market data subscriptions
Set EXECUTION_MODE=live in live environment
First live trade: smallest allowed position size, manually monitored

## 8.2 Prompt Deployment
Prompts are deployed independently of infrastructure. No cdk deploy required.
Edit prompt file in /prompts/{prompt_id}/v{version}.txt
Validate: qitp prompt validate prompts/{prompt_id}/v{version}.txt
Push to registry: qitp prompt push prompts/{prompt_id}/v{version}.txt --id {prompt_id}
Test against specific agent: qitp agent test {agent_id} --prompt-version {version} --mode backtest
If test passes: promote as latest: qitp prompt promote {prompt_id} {version}
Rollback if needed: qitp prompt rollback {prompt_id} {previous_version}

## 8.3 Strategy Deployment
Strategy blueprints are deployed independently. Validated via backtest before promotion.
Edit or create strategy YAML in /blueprints/strategies/{strategy_id}.yaml
Validate schema: qitp strategy validate blueprints/strategies/{strategy_id}.yaml
Run backtest: qitp backtest run --strategy {strategy_id} --symbols watchlist --start 2023-01-01 --end 2024-12-31
Review backtest results: Sharpe > 0.5, max drawdown < 15%, win rate > 45% minimum
Promote to registry: qitp strategy promote {strategy_id} --version {version}
Strategy active in next Monday pipeline run automatically


END OF DOCUMENT 7 — QITP Operations & Observability Runbook

| Version: 1.0 — March 2026 | Author: Nestor Colt | Status: DRAFT |
| --- | --- |


| Layer | Technology | Captures |
| --- | --- | --- |
| Prompt Tracking | Langfuse (Anton instance) | Prompt version, token usage, latency, cost per agent invocation |
| Distributed Tracing | AWS X-Ray | Cross-service trace: EventBridge -> SFN -> Lambda -> AgentCore -> MCP |
| Infrastructure Metrics | CloudWatch + Grafana | Lambda duration, error rate, SFN execution count, ECS task health |
| Audit Log | DynamoDB qitp_audit_log | Every financial decision: order attempts, risk checks, 2FA events |
| Structured Logging | CloudWatch Logs (JSON) | Agent execution details, tool calls, execution mode, prompt version |
| Portfolio Metrics | DynamoDB + Grafana | NAV, daily P&L, position count, drawdown, per-strategy performance |
| Alerting | CloudWatch Alarms -> SNS -> Telegram | Circuit breakers, execution failures, anomalous behavior |


| Event Type | Severity | Fields |
| --- | --- | --- |
| ORDER_REQUESTED | INFO | symbol, action, qty, estimated_value, strategy, composite_score, agent_rationale |
| RISK_CHECK_PASS | INFO | symbol, order_details, rules_checked, portfolio_state_snapshot |
| RISK_CHECK_FAIL | WARN | symbol, order_details, violated_rule, violation_details |
| 2FA_APPROVAL_SENT | INFO | symbol, order_details, telegram_message_id, expiry |
| 2FA_APPROVED | INFO | symbol, approved_by, approval_timestamp, latency_seconds |
| 2FA_REJECTED | WARN | symbol, rejected_by, reason, order_abandoned |
| 2FA_EXPIRED | WARN | symbol, expiry_timestamp, order_abandoned |
| ORDER_SUBMITTED | INFO | symbol, ibkr_order_id, fill_price, qty, commission, exchange |
| ORDER_FILLED | INFO | symbol, fill_price, fill_qty, fill_timestamp, slippage_pct |
| ORDER_REJECTED | ERROR | symbol, ibkr_error_code, ibkr_error_message |
| CIRCUIT_BREAKER_TRIGGERED | CRITICAL | trigger_rule, portfolio_state, halt_duration_hours |
| TRAILING_STOP_UPDATED | INFO | symbol, old_stop_price, new_stop_price, trigger_reason |
| POSITION_CLOSED | INFO | symbol, entry_price, exit_price, pnl_eur, holding_days, exit_reason |
| PIPELINE_STARTED | INFO | execution_id, trigger_type, watchlist_size, execution_mode |
| PIPELINE_COMPLETED | INFO | execution_id, duration_ms, gaps_found, recommendations_count, orders_submitted |


| Alert | Severity | Trigger | Message Format |
| --- | --- | --- | --- |
| Daily Circuit Breaker | CRITICAL | Portfolio down >3% in one day | HALT: Daily loss limit hit. NAV -3.2%. All trading suspended for 24h. |
| Drawdown Circuit Breaker | CRITICAL | NAV down >10% from peak | HALT: Drawdown limit hit. Peak NAV: EUR X, Current: EUR Y (-10.2%). Manual resume required. |
| Agent Execution Timeout | WARN | Agent runs >5 minutes | WARN: gap_detection_agent exceeded 5min timeout. Execution ID: xyz. Check X-Ray. |
| Step Functions Failure | WARN | SFN execution fails | WARN: Weekly workflow failed at state: SentimentAnalysis. Error: Lambda timeout. Execution: xyz |
| IBKR Connection Lost | WARN | ibkr-mcp health check fails | WARN: IBKR Gateway connection lost. Last successful ping: 14:32. Reconnect attempted. |
| Order Rejected by IBKR | WARN | place_order returns rejection | WARN: Order rejected by IBKR. Symbol: NVDA, Reason: Insufficient funds. Details in audit log. |
| Weekly P&L Report | INFO | Every Friday 18:00 CET | WEEKLY P&L: +EUR 340 (+1.7%). Best: NVDA +EUR 520. Worst: AAPL -EUR 180. Open positions: 3. |
| Monday Pipeline Start | INFO | Every Monday 08:30 CET | PIPELINE: Weekly scan started. Watchlist: 100 symbols. Mode: live. Threshold: 2.0%. |
| New Recommendation | INFO | Recommendation produced | RECOMMENDATION: 3 symbols shortlisted. Top: NVDA (score: 0.84). Review artifacts for details. |
| High Slippage Detected | WARN | Fill price > 0.5% from order price | WARN: High slippage on NVDA. Expected: $878.50, Filled: $882.90 (+0.5%). Review market conditions. |


| Circuit Breaker Rule
When a circuit breaker is triggered, ALL trading is halted immediately. No orders are accepted, no 2FA gates are opened. The circuit breaker state is stored in DynamoDB and checked by the Risk Engine on every order attempt. CANNOT be bypassed by agents. |
| --- |


| Severity
HIGH — Trailing stops may not update. New orders cannot be submitted. Existing IBKR stops still active on broker side. |
| --- |


| Severity
MEDIUM — Agent consuming excessive tokens and time. Will hit max_iterations or max_execution_time limit automatically. |
| --- |


| Severity
CRITICAL — If a live order was submitted without expected 2FA approval. Investigate immediately. |
| --- |


| Widget | Metric | Alarm Threshold |
| --- | --- | --- |
| Pipeline Executions | SFN weekly workflow success/failure count (7d) | Any failure -> WARN alert |
| Agent Latency | p50/p95/p99 agent execution time by agent_id | >300s p95 -> WARN |
| Token Cost | Daily token spend by agent (from Langfuse) | >$50/day -> WARN |
| Portfolio NAV | Current NAV vs peak NAV, daily change % | See circuit breaker rules |
| Open Positions | Count of open positions by strategy | >5 -> WARN (unexpected) |
| Risk Engine PASS/FAIL | Count of PASS vs FAIL checks (7d) | FAIL rate >20% -> WARN |
| 2FA Approval Rate | Approve vs Reject vs Timeout ratios | Timeout rate >10% -> INFO |
| IBKR Connection Health | ibkr-mcp health check success rate | <95% -> WARN |


| Instrument Class | Max Leverage | Risk Engine Enforcement |
| --- | --- | --- |
| Major forex pairs (EUR/USD, etc.) | 30:1 | CFD order margin check: min 3.33% margin required |
| Non-major forex + gold | 20:1 | CFD order: min 5% margin required |
| Major stock indices | 20:1 | CFD order: min 5% margin required |
| Other commodities + non-major indices | 10:1 | CFD order: min 10% margin required |
| Individual equities | 5:1 | CFD order: min 20% margin required |
| Crypto (if ever added) | 2:1 | CFD order: min 50% margin required |


| Rule
No code goes directly to paper or live. dev -> paper requires successful CI + integration test. paper -> live requires manual approval gate in GitHub Actions + minimum 4 weeks of successful paper trading. |
| --- |
