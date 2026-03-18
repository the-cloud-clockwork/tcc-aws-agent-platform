# QITP_Doc9 — Pre-Production Forensic Audit

> Pre-deployment security, compliance, consistency, and reliability audit. All findings must be resolved before live trading.
>
> **Audit Date**: 2026-03-16
> **Scope**: All 25 implementation plans (P01–P25), 8 design documents, CLAUDE.md architecture spec
> **Methodology**: 6 parallel forensic audits covering financial/regulatory, security/IAM, cross-plan consistency, AWS cost/operations, failure modes/edge cases, and Strands SDK/AgentCore correctness
> **Classification**: CRITICAL = go-live blocker | HIGH = must fix before paper trading | MEDIUM = fix before production hardening

---

## Executive Summary

**Total findings: ~150 gaps across 6 dimensions.**

| Dimension | Findings | CRITICAL | HIGH | MEDIUM |
|---|:---:|:---:|:---:|:---:|
| Financial & Regulatory | 38 | 5 | 19 | 14 |
| Security & IAM | 27 | 5 | 10 | 12 |
| Cross-Plan Consistency | 20 | 2 | 7 | 11 |
| AWS Cost & Operations | ~25 | 6 | 8 | 11 |
| Failure Modes & Edge Cases | 18 | 3 | 8 | 7 |
| Strands SDK & AgentCore | 19 | 0 | 7 | 12 |
| **TOTAL** | **~150** | **21** | **59** | **67** |

The platform architecture is sound. The Russian Doll layering, blueprint-driven design, and execution mode separation are well-conceived. However, **21 CRITICAL findings** must be resolved before any live trading occurs. The majority cluster around three themes:

1. **Regulatory gaps** — Missing ESMA/CNMV reporting mechanisms and Spanish tax computation rules
2. **Race conditions and bypass paths** — 2FA, Risk Engine, and idempotency gaps that could result in unauthorized or duplicate orders
3. **Operational readiness** — No disaster recovery, no log archival for MiFID II, no on-call rotation

---

## Go-Live Blockers (CRITICAL — Must Fix Before Live Trading)

### Financial & Regulatory CRITICAL

| # | Finding | Impact | Affected Plans |
|---|---|---|---|
| F-01 | RTS 25 post-trade transaction reporting not implemented | ESMA violation — Spain/CNMV can levy fines; no mechanism to report to Approved Reporting Mechanism (ARM) | P14 |
| F-02 | CNMV short-sell ban list is not dynamically synced | Trading banned securities — must be refreshed daily from CNMV; no EventBridge schedule defined | P16 |
| F-03 | Corporate action handling missing | Stock splits break trailing stops; dividends corrupt P&L calculations; no monitoring Lambda | P14 |
| F-04 | Survivorship bias in historical backtest data not addressed | Backtest results artificially inflated; delisted symbols not filtered from S3 parquet files | P03 |
| F-05 | Spanish IRPF 2-month homogeneous securities aggregation rule not implemented | Tax liability miscalculated; repurchase within 2 months of loss disallows loss deduction | P25 |

### Security CRITICAL

| # | Finding | Impact | Affected Plans |
|---|---|---|---|
| S-01 | No Cedar policy framework in Phase 1 | Any agent can invoke any MCP tool — gap_detection could call place_order; no tool-level access control | P02 |
| S-02 | IBKR credential rotation not scheduled | Secrets Manager not configured; static credentials risk compromise; no rotation Lambda | P14, P17 |
| S-03 | No SCA/dependency vulnerability scanning in CI/CD pipeline | Supply chain attack vector; no pip-audit, Dependabot, or OWASP checks on 17 repos | P01 |
| S-04 | No input validation/sanitization on MCP tool parameters | Injection risk; agent-generated parameters passed directly to IBKR/Polygon APIs | All MCPs |
| S-05 | No approval workflow for sensitive MCPs | artifacts-mcp can read/write strategy code; no gating mechanism for sensitive operations | P06 |

### Cross-Plan CRITICAL

| # | Finding | Impact | Affected Plans |
|---|---|---|---|
| C-01 | DynamoDB session table naming conflict | P17 creates `qitp_{env}_ibkr_sessions`, P19 references `qitp_run_history` via SESSION_TABLE env var — runtime KeyError | P17, P19 |
| C-02 | Missing DynamoDB tables for 2FA advanced features | P23 needs `qitp_2fa_credentials` and `qitp_2fa_yubikeys` tables not defined in P11 CDK stack | P11, P23 |

### AWS Operations CRITICAL

| # | Finding | Impact | Affected Plans |
|---|---|---|---|
| O-01 | No disaster recovery plan | Single region eu-west-1; no failover; total platform loss on regional outage during market hours | P17 |
| O-02 | No CloudWatch log export automation | MiFID II requires 5-year retention; CloudWatch default 90-day; logs silently expire | P18 |
| O-03 | No PITR restore procedure documented | DynamoDB PITR enabled (35-day window) but no runbook; untested restore = no restore | P17 |
| O-04 | No on-call rotation or escalation policy defined | Circuit breaker fires at 08:30 CET Monday; nobody responds; trading halted indefinitely | P18 |

### Failure Modes CRITICAL

| # | Finding | Impact | Affected Plans |
|---|---|---|---|
| FM-01 | 2FA race condition: user approves after 5-min timeout | No atomic CAS on DynamoDB; auto-reject + late approval = order placed after rejection | P15 |
| FM-02 | Risk Engine can be bypassed via agent retry loops | No SFN state isolation; agent Lambda retries skip risk check on subsequent attempts | P16, P12 |
| FM-03 | Idempotency key strategy undefined across all write operations | No idempotency store; agent retries can generate duplicate orders, duplicate artifacts, duplicate audit entries | P10, P14, P16 |

---

## Section 1: Financial & Regulatory Compliance

### 1.1 ESMA / MiFID II

| # | Severity | Finding | Detail |
|---|---|---|---|
| F-01 | CRITICAL | RTS 25 transaction reporting | No mechanism to report trades to ESMA Approved Reporting Mechanism (ARM). Required for all MiFID II investment firms. Must implement post-trade Lambda that formats and submits to ARM provider (e.g., Unavista, TRAX). |
| F-06 | HIGH | ISIN lookup service missing for US symbols | S&P500 watchlist uses ticker symbols; MiFID II requires ISIN in all transaction reports. No Polygon ISIN reference data pipeline. |
| F-07 | HIGH | Venue routing defaults to "SMART" | IBKR SMART routing used without documented best execution rationale. MiFID II Article 27 requires periodic analysis of execution quality across venues. |
| F-08 | HIGH | MiFID II Best Execution policy document not written | Required document for MiFID II compliance. Must detail venue selection criteria, order type rationale, execution quality monitoring. |

### 1.2 CNMV (Spain National Securities Market Commission)

| # | Severity | Finding | Detail |
|---|---|---|---|
| F-02 | CRITICAL | Short-sell ban list not dynamically synced | CNMV publishes emergency short-sell bans (COVID precedent: March 2020). No daily refresh from CNMV website. No EventBridge schedule. No `qitp_cnmv_ban_list` DynamoDB table provisioned. |
| F-09 | HIGH | SSHORT position notification thresholds not implemented | CNMV requires notification at 0.2% (private), 0.5% (public), 1%, and 5% of issued share capital. No position-to-shares-outstanding ratio calculation. |
| F-10 | MEDIUM | Professional vs retail client classification impact undefined | ESMA leverage limits differ by classification. CNMV retail investor protections (risk warnings, loss limits) not documented. Impact on CFD trading undefined. |

### 1.3 Spanish IRPF Tax

| # | Severity | Finding | Detail |
|---|---|---|---|
| F-05 | CRITICAL | 2-month homogeneous securities aggregation rule | Spanish tax law (Ley 35/2006, Art. 33.5.f): if identical securities repurchased within 2 months of a loss sale, the loss cannot be deducted until final disposal. Not implemented. Requires position history tracking with 60-day lookback. |
| F-11 | HIGH | Cost basis method not specified | FIFO vs weighted average — Spanish IRPF uses FIFO by default for securities. Not configured in any plan. |
| F-12 | HIGH | Dividend withholding tax tracking missing | US stocks: 15% treaty rate withheld by IRS. Must be tracked per dividend event for Modelo 100 declaration and foreign tax credit. |
| F-13 | HIGH | FX conversion rate selection undefined | ECB daily reference rate? Spot rate at execution? Historical rate at acquisition? Spanish IRPF requires consistent methodology. |
| F-14 | MEDIUM | Modelo 720 foreign assets declaration not automated | Assets >50,000 EUR outside Spain require annual declaration. IBKR accounts are foreign assets. No automated report generation. |
| F-15 | MEDIUM | Commission attribution to tax lots for partial exits undefined | Partial position closure: how are commissions allocated across remaining lots? FIFO implies specific lot identification. |

### 1.4 Risk Engine Gaps

| # | Severity | Finding | Detail |
|---|---|---|---|
| F-03 | CRITICAL | Corporate action handling missing | Stock splits: trailing stop at $150 becomes invalid after 3:1 split. Dividends: ex-date price drop triggers false trailing stop. No monitoring Lambda, no adjustment logic. |
| F-16 | HIGH | Overnight gap risk not modeled | Platform specializes in gap trading but doesn't model the risk of gaps moving against open positions. No overnight VaR calculation. |
| F-17 | HIGH | Sector correlation risk not accounted for | 5 tech stocks treated as independent positions. Correlated drawdown could exceed -3% daily loss limit before circuit breaker activates. |
| F-18 | HIGH | Liquidity risk check missing | Position size not compared against average daily volume. Illiquid small-caps could cause significant slippage on exit. |
| F-19 | HIGH | IBKR connection failure during market hours — no failover | Single IBKR gateway session. Connection drop = no trailing stop management = unlimited loss exposure. |
| F-20 | MEDIUM | Stock split / dividend adjustment to trailing stops not handled | Trailing stop prices become stale after corporate actions. No EventBridge listener for IBKR corporate action notifications. |

### 1.5 Backtest Validity

| # | Severity | Finding | Detail |
|---|---|---|---|
| F-04 | CRITICAL | Survivorship bias | Historical S3 parquet data includes only currently-listed symbols. Delisted/acquired/bankrupt symbols excluded. Backtest results artificially inflated by ~2-4% annually (academic consensus). |
| F-21 | HIGH | Dividend-adjusted vs unadjusted close prices not documented | Gap calculations require split-adjusted but NOT dividend-adjusted prices. Using fully-adjusted prices inflates gap magnitudes around ex-dates. |
| F-22 | HIGH | Gap-specific slippage model needed | Gaps execute at market open — known price. Standard slippage models (random walk) are incorrect. Need gap-specific model: slippage = f(gap_size, volume, spread). |
| F-23 | MEDIUM | IBKR EU tiered commission model not fully specified | Commission tiers vary by exchange (Xetra vs Euronext vs LSE). Backtest uses flat rate assumption. |

### 1.6 Order Execution Edge Cases

| # | Severity | Finding | Detail |
|---|---|---|---|
| F-24 | HIGH | Partial fill handling undefined | Market order for 1000 shares, 600 filled: no logic for residual order management, position sizing recalculation, or trailing stop adjustment. |
| F-25 | HIGH | Order rejection recovery logic missing | IBKR rejects order (insufficient margin, symbol halted): no agent recovery path, no user notification, SFN state undefined. |
| F-26 | MEDIUM | Market halt / exchange circuit breaker handling absent | NYSE/NASDAQ LULD halts: pending orders queued. No detection, no agent awareness, no SFN timeout adjustment. |
| F-27 | MEDIUM | Pre-market / after-hours session routing not specified | Gap trades may benefit from pre-market entry. No session type configuration in IBKR order parameters. |

### 1.7 Multi-Currency

| # | Severity | Finding | Detail |
|---|---|---|---|
| F-28 | HIGH | EUR/USD FX rate selection for P&L reporting undefined | EUR-denominated portfolio holding USD assets. Daily P&L requires consistent FX methodology. |
| F-29 | MEDIUM | Unrealized FX gains for Modelo 720 not computed | Foreign asset declaration requires EUR valuation. No FX conversion at declaration date. |
| F-30 | MEDIUM | FX hedging suggestions not offered | USD exposure unhedged. No risk quantification of FX impact on portfolio returns. |

### 1.8 Remediation Approach

All financial/regulatory fixes follow the **configuration-driven** principle:

| Configuration | Storage | Refresh | Purpose |
|---|---|---|---|
| CNMV ban list | DynamoDB `qitp_cnmv_ban_list` | Daily (EventBridge Lambda) | Banned ISINs for IBEX35 short selling |
| Tax configuration | DynamoDB `qitp_tax_config` | Manual | cost_basis=FIFO, aggregation_window=60d, withholding rates |
| ISIN reference | S3 `qitp-artifacts/isin-reference/latest.parquet` | Daily (Polygon API) | Symbol-to-ISIN mapping for RTS 25 |
| FX rates | S3 `qitp-artifacts/fx-rates/ecb-daily/` | Daily (ECB XML feed) | EUR/USD closing rates for P&L and tax |
| Market calendar | DynamoDB `qitp_market_calendar` | Quarterly | US/EU holidays, DST transitions, half-days |
| Commission schedule | DynamoDB `qitp_commission_config` | On change | IBKR tiered rates per exchange |

---

## Section 2: Security & IAM

### 2.1 IAM & Access Control

| # | Severity | Finding | Detail |
|---|---|---|---|
| S-01 | CRITICAL | No Cedar policy framework in Phase 1 | Deferred to Phase 2 (P19) but needed immediately. Without Cedar, any Strands agent can invoke any MCP tool. Gap detection agent could theoretically call `place_order`. |
| S-06 | HIGH | Lambda IAM roles likely over-permissive | Plans reference `s3:*` and `dynamodb:*` permissions. Least-privilege not enforced. Each Lambda should have scoped IAM role per table/bucket. |
| S-07 | HIGH | No cross-account isolation for dev/staging/prod | All environments in single account `123456789012`. Blast radius of IAM misconfiguration affects production. |

### 2.2 Secrets Management

| # | Severity | Finding | Detail |
|---|---|---|---|
| S-02 | CRITICAL | IBKR credential rotation not scheduled | No Secrets Manager integration in Phase 1. IBKR API credentials stored as Lambda env vars. No rotation Lambda. Credential compromise = unauthorized trading. |
| S-08 | HIGH | Secrets Manager VPC endpoint missing | Phase 1 Lambda functions in VPC cannot reach Secrets Manager without endpoint or NAT. Adds latency and cost if using NAT. |
| S-09 | MEDIUM | No field-level encryption for sensitive DynamoDB attributes | `qitp_2fa_events` stores approval tokens. `qitp_audit_log` stores order details. No attribute-level encryption beyond table-level default. |

### 2.3 Network Security

| # | Severity | Finding | Detail |
|---|---|---|---|
| S-10 | HIGH | MCP servers have no mTLS or request signing | Any service in the VPC can invoke MCP tools. No authentication between agent Lambdas and MCP Fargate tasks. Lateral movement risk. |
| S-11 | HIGH | No DDoS protection strategy | No AWS Shield Advanced. No rate limiting on 2FA Telegram gateway. Attacker could flood 2FA endpoint to block legitimate approvals. |
| S-12 | MEDIUM | Artifact S3 bucket lacks explicit public access block | `qitp-artifacts` bucket policy not explicitly denying public access. S3 Block Public Access not confirmed in CDK stack. |

### 2.4 Data Encryption

| # | Severity | Finding | Detail |
|---|---|---|---|
| S-13 | MEDIUM | No explicit KMS key rotation policy | AWS default: 1-year rotation for AWS-managed keys. Financial data should use 90-day rotation with customer-managed CMK. |
| S-14 | MEDIUM | S3 uses SSE-S3 instead of KMS CMK | SSE-S3 (AES-256) provides encryption but no key usage auditing via CloudTrail. CMK enables key policy control and usage logging. |
| S-15 | MEDIUM | DynamoDB uses default encryption | Default AWS-owned key. No customer-managed KMS key. No key usage visibility in CloudTrail. |

### 2.5 Authentication & Authorization

| # | Severity | Finding | Detail |
|---|---|---|---|
| S-16 | HIGH | No service-to-service authentication | Agent-to-MCP communication uses plain HTTP within VPC. No HMAC signing, no SigV4, no mutual TLS. Any compromised container can impersonate any agent. |
| S-17 | MEDIUM | No MFA for non-financial MCP invocations | Financial MCPs (ibkr-mcp) have 2FA. Non-financial MCPs (artifacts-mcp, market-data-mcp) have no access control beyond VPC boundary. |
| S-18 | MEDIUM | No RBAC for audit log readers | `qitp_audit_log` contains sensitive financial decisions. No IAM policy restricting read access to authorized principals only. |

### 2.6 Supply Chain Security

| # | Severity | Finding | Detail |
|---|---|---|---|
| S-03 | CRITICAL | No SCA or dependency vulnerability scanning | 17 repos with Python dependencies. No pip-audit in CI/CD. No Dependabot configured. No OWASP dependency-check. Supply chain attack (e.g., compromised PyPI package) undetected. |
| S-19 | HIGH | No Docker image signing | MCP containers built without Sigstore/Cosign signatures. Image tampering undetectable. No image provenance verification in ECS task definitions. |
| S-20 | MEDIUM | No dependency lock files or hash pinning | `requirements.txt` without hashes. `pip install` resolves latest compatible version. Reproducible builds not guaranteed. |

### 2.7 Compliance & Privacy

| # | Severity | Finding | Detail |
|---|---|---|---|
| S-21 | MEDIUM | GDPR data minimization strategy not defined | Agent reasoning chains may contain personal data. No policy on what data agents can store vs must discard. |
| S-22 | MEDIUM | No GDPR DSR handling mechanism | No process for data subject access requests, right to erasure, or data portability. DynamoDB/S3 data spread across 8+ tables/buckets. |
| S-23 | MEDIUM | No audit retention SOP or archival strategy | MiFID II 5-year retention acknowledged but no Standard Operating Procedure for archival, retrieval, or destruction. |
| S-24 | MEDIUM | MiFID II Best Execution policy document not written | Required compliance document. Must be reviewed annually. No template or owner assigned. |

### 2.8 Attack Surface

| # | Severity | Finding | Detail |
|---|---|---|---|
| S-04 | CRITICAL | No input validation/sanitization on MCP tool parameters | Agent-generated parameters (symbol names, quantities, prices) passed directly to downstream APIs. SQL injection unlikely but API parameter manipulation possible. |
| S-05 | CRITICAL | No approval workflow for sensitive MCPs | artifacts-mcp can read/write strategy YAML and prompt templates. Compromised agent could modify strategy parameters or inject malicious prompts. No human-in-the-loop for sensitive artifact operations. |
| S-25 | HIGH | No per-agent rate limits or invocation quotas | Runaway agent loop could exhaust Bedrock token budget ($14K/mo paper mode) in hours. No DynamoDB-backed quota table. |
| S-26 | MEDIUM | No timeout/circuit breaker for hung agent processes | Lambda 15-min timeout is the only safeguard. No application-level circuit breaker for agents stuck in reasoning loops. |
| S-27 | MEDIUM | No prompt injection detection or reasoning chain logging | Adversarial market data (crafted news headlines) could influence agent reasoning. No detection layer. No reasoning chain audit for post-incident analysis. |

---

## Section 3: Cross-Plan Consistency

### 3.1 CRITICAL Issues

| # | Finding | Plans | Impact |
|---|---|---|---|
| C-01 | **Session table naming conflict**: P17 creates `qitp_{env}_ibkr_sessions`, P19 references `qitp_run_history` via `SESSION_TABLE` env var. Different tables, different schemas, same logical concept. | P17, P19 | Runtime KeyError when AgentCore migration attempts to read session data from wrong table. |
| C-02 | **Missing 2FA infrastructure tables**: P23 (Advanced 2FA) needs `qitp_2fa_credentials` and `qitp_2fa_yubikeys` DynamoDB tables. These are not defined in P11 (CDK stacks) or any earlier plan. | P11, P23 | P23 deployment fails; CDK stack update required mid-phase. |

### 3.2 HIGH Issues

| # | Finding | Plans | Impact |
|---|---|---|---|
| C-03 | MacroSentiment schema duplicated in P02 (blueprint models) and P07 (sentiment-mcp). Both define the same Pydantic model with slightly different field names. | P02, P07 | Import conflict at runtime. `from qitp_core.models import MacroSentiment` vs `from sentiment_mcp.schemas import MacroSentiment`. |
| C-04 | `SESSION_TABLE` env var default value doesn't match P17 table name. Default: `qitp_run_history`. P17 creates: `qitp_{env}_ibkr_sessions`. | P17 | Silent failure — writes to non-existent table, DynamoDB auto-creates with wrong schema (on-demand mode). |
| C-05 | Tool definition mismatch: P08 (Gap Detection Agent) uses `content=` parameter when calling artifacts-mcp, but P06 signature expects `data=`. | P06, P08 | Agent tool call fails with parameter validation error. |
| C-06 | S3 bucket naming inconsistency: CLAUDE.md uses `qitp-artifacts`, P11 uses `qitp-{env}-artifacts` (parameterized by environment). | CLAUDE.md, P11 | Dev/staging/prod bucket collision if CLAUDE.md convention followed literally. |
| C-07 | Agent blueprint tool validation missing: no validation that tool names in blueprint YAML match actual MCP tool definitions. | P02 | Silent failure — agent loads blueprint, connects to MCP, tool name not found. No error until runtime invocation. |
| C-08 | Artifact type `technical_analysis` introduced in P22 but not in P06 artifact type enumeration. | P06, P22 | artifacts-mcp rejects `technical_analysis` artifact type with validation error. |
| C-09 | Tool name mismatch between P05 (market-data-mcp) and P10 (simulation engine): some agents reference tools not exposed by the MCP they connect to. | P05, P10 | Agent tool invocation fails silently or raises ToolNotFoundError. |

### 3.3 MEDIUM Issues

| # | Finding | Plans | Impact |
|---|---|---|---|
| C-10 | Technical analysis MCP port 8009 not documented in CLAUDE.md MCP table. Only ports 8001–8008 listed. | CLAUDE.md, P22 | Developer confusion. Docker Compose port conflicts possible. |
| C-11 | P07 schema import inconsistency: relative import `from .schemas import ...` after local class definition in same file. | P07 | ImportError in certain module loading orders. |
| C-12 | Execution mode routing logic scattered across P15, P14, P02 with no single source of truth. | P02, P14, P15 | Mode routing inconsistency between components. Paper mode might route differently than expected. |
| C-13 | Risk Engine config table (`qitp_risk_config`) referenced in plans but not provisioned in P11 CDK stack. | P11, P16 | Risk Engine falls back to hardcoded defaults, violating no-hardcoding principle. |
| C-14 | Prompt version resolution strategy undefined: latest vs prod vs pinned. | P04 | Prompt Registry returns "latest" by default. No mechanism to pin production prompts while iterating on dev. |
| C-15 | Cedar policy tool versioning unclear: policies reference tool names but tools may be renamed across MCP versions. | P19 | Cedar policy becomes stale after MCP tool rename. Silent security gap. |
| C-16 | CDK environment variable name inconsistency: `env_name` vs `environment` vs `ENVIRONMENT` across different stacks. | P11, P17 | Stack deployment fails or uses wrong environment isolation. |
| C-17 | Trailing stop enforcement consistency gap between paper and live modes. | P14, P16 | Paper mode may not enforce trailing stops identically to live, making paper results non-representative. |
| C-18 | P10 implicitly depends on P04 (Prompt Registry) but this dependency is not in TODO.md dependency graph. | P10, TODO.md | P10 execution fails if P04 not completed first. Batch scheduling incorrect. |
| C-19 | 2FA audit log field schema inconsistency between P15 (basic 2FA) and P23 (advanced 2FA). | P15, P23 | P23 audit entries incompatible with P15 audit log queries. Dashboard breaks. |
| C-20 | Artifact type enumeration gap: P22 introduces `technical_analysis` not in P06 enum. Duplicate of C-08 from different angle — P06 must be updated before P22 can deploy. | P06, P22 | Deployment ordering constraint not documented. |

---

## Section 4: AWS Cost & Operations

### 4.1 Cost Estimates

| Environment | Monthly Estimate | Annual Estimate | Top 3 Cost Drivers |
|---|---:|---:|---|
| **Dev (backtest only)** | ~$2,345 | ~$28,140 | Bedrock tokens ($2,970), Fargate MCPs ($1,314), DynamoDB ($180) |
| **Paper (live data)** | ~$19,500 | ~$234,000 | Bedrock tokens ($14,857), Fargate ($1,314), Polygon API ($199) |
| **Live (real trading)** | ~$11,878 | ~$142,536 | Bedrock ($6,276), Fargate ($3,808), NAT Gateway ($128) |

**Key observations:**
- Bedrock token cost dominates all environments (60-76% of total)
- Paper mode is the most expensive due to continuous market data + frequent agent invocations
- Live mode is cheaper than paper because trading occurs only on Monday mornings (weekly gap strategy)
- Prompt caching could save ~$800/mo across all environments

### 4.2 Disaster Recovery

| # | Severity | Finding | Detail |
|---|---|---|---|
| O-01 | CRITICAL | Single region deployment | All infrastructure in eu-west-1. No failover region. Regional outage during market hours = complete trading halt + potential orphaned orders on IBKR. |
| O-05 | HIGH | No DynamoDB Global Tables for risk_state | `qitp_risk_state` is the most critical table (circuit breaker state). Single-region. Loss = risk engine blind. |
| O-06 | HIGH | No cross-region S3 replication | Artifacts, historical data, prompts — all single-region. No replication to eu-central-1. |

**Recommendation**: RTO 30 minutes, RPO 5 minutes with eu-central-1 warm standby.

| Component | DR Strategy | RTO | RPO |
|---|---|---|---|
| DynamoDB risk_state | Global Tables (active-active) | 0 min | 0 min |
| DynamoDB other tables | PITR + cross-region backup | 30 min | 5 min |
| S3 buckets | Cross-Region Replication | 15 min | 15 min |
| Lambda functions | Multi-region deploy via CDK | 15 min | 0 min |
| ECS Fargate (MCPs) | Standby cluster in eu-central-1 | 10 min | 0 min |
| Step Functions | Re-deploy state machines | 5 min | 0 min |

### 4.3 Backup & Retention

| # | Severity | Finding | Detail |
|---|---|---|---|
| O-02 | CRITICAL | No CloudWatch log export automation | MiFID II requires 5-year retention. CloudWatch default: configurable but set to 90 days in plans. No automated export to S3. Logs silently expire. |
| O-03 | CRITICAL | No PITR restore procedure documented | DynamoDB PITR enabled (35-day window) but no runbook. No tested restore. No validation that restored data matches expectations. |
| O-07 | HIGH | S3 versioning enabled but no lifecycle rules | No transition to Glacier after 90 days. No expiration policy. Storage costs grow unbounded. |
| O-08 | MEDIUM | No automated archive to S3 Glacier before TTL expiry | DynamoDB TTL deletes audit records. No pre-deletion export to cold storage. MiFID II evidence lost. |

**Required log archival pipeline:**

```
CloudWatch Logs → Kinesis Firehose → S3 (Standard, 90 days)
                                      → S3 Glacier (90 days – 5 years)
                                      → Delete (after 5 years)
```

### 4.4 Scaling Bottlenecks

| # | Severity | Finding | Detail |
|---|---|---|---|
| O-09 | CRITICAL | Backtest timeout risk | 5,000 simulations in P10. Lambda 15-min limit. Walk-forward validation with 52 windows x 100 symbols = 5,200 iterations. Must use Step Functions Map state or SQS fan-out. |
| O-10 | HIGH | market-data-mcp concurrency spike | Monday 08:30 CET: 100 symbols x 5 requests = 500 requests in ~30 seconds (16.7 req/sec sustained). Single Fargate task may throttle. |
| O-11 | MEDIUM | No Lambda provisioned concurrency for hot agents | Cold start latency (3-5 seconds) on gap_detection and portfolio_recommender. Monday morning spike hits cold Lambdas. |
| O-12 | MEDIUM | Step Functions Map state concurrency=10 may be insufficient | Sentiment analysis swarm: 100 symbols x 3 sources = 300 parallel tasks. Map state default concurrency limit = 40. Need explicit configuration. |

### 4.5 Operational Readiness

| # | Severity | Finding | Detail |
|---|---|---|---|
| O-04 | CRITICAL | No on-call rotation defined | Circuit breaker fires, 2FA gateway down, IBKR disconnects — no person to respond. No PagerDuty/Opsgenie integration. |
| O-13 | HIGH | No SLOs defined | No target for: pipeline completion time, agent latency P99, risk engine decision time, 2FA response time, data freshness. |
| O-14 | HIGH | Missing runbooks | No documented procedures for: circuit breaker recovery, PITR restore, regional failover, prompt corruption rollback, IBKR session recovery. |
| O-15 | HIGH | Missing alerts | No CloudWatch alarms for: data feed loss (Polygon), IBKR connection drops, Bedrock rate limiting (429), DynamoDB throttling, SFN execution failures. |

### 4.6 Deployment Pipeline

| # | Severity | Finding | Detail |
|---|---|---|---|
| O-16 | HIGH | No CI/CD pipeline fully defined for 17 repos | Each repo needs: lint, test, build, deploy. No GitHub Actions workflows. No deployment orchestration across repos. |
| O-17 | HIGH | No documented deployment order | 17 repos with interdependencies. Deploying tccw-qitp-agents before tccw-qitp-core breaks imports. No dependency graph for deployment. |
| O-18 | MEDIUM | No rollback strategy documented | CDK deploy fails mid-stack: manual rollback? CloudFormation automatic? No documented procedure. |
| O-19 | MEDIUM | No canary/blue-green deployment for live mode | Live trading deployment: all-at-once. No gradual rollout. Bad deploy = immediate production impact. |

### 4.7 Cost Optimization Opportunities

| Optimization | Monthly Savings | Risk | Priority |
|---|---:|---|---|
| Prompt caching (Bedrock) | ~$800 | None — transparent to agents | HIGH |
| S3 lifecycle + Glacier archive | ~$120 | None — cold data only | HIGH |
| Fargate Spot for non-critical MCPs | ~$400 | Spot interruption during analysis (non-financial) | MEDIUM |
| Haiku model for gap detection | ~$400 | Accuracy degradation — requires A/B validation | LOW |
| Bedrock Batch API for backtests | ~$1,000 | Latency increase (minutes vs seconds) | MEDIUM |
| Reserved Fargate capacity | ~$200 | 1-year commitment | LOW |
| **Total potential savings** | **~$2,920/mo** | | |

---

## Section 5: Failure Modes & Edge Cases

### 5.1 IBKR Connection Failures

| # | Severity | Failure Mode | Impact | Mitigation |
|---|---|---|---|---|
| FM-04 | HIGH | Session expiry mid-order | Order submission fails after risk check passed. No pre-order session validation. | Add `validate_session()` before every `place_order` call. |
| FM-05 | HIGH | Gateway restart / competing session | IBKR allows only 1 API session. Second connection kills first. Trailing stop monitoring lost. | Session lock in DynamoDB. Health check before connect. |
| FM-06 | HIGH | HTTP 500 but order placed ("Scarlet Scenario") | IBKR returns 500 but order was received. Agent retries. Duplicate order placed. | Idempotency key on IBKR client order ID. Post-500 position check before retry. |
| FM-07 | MEDIUM | Weekend maintenance windows | SFN triggers on Sunday for Monday prep. IBKR gateway down for maintenance. No market calendar check. | Add market calendar pre-check in SFN first state. |

### 5.2 Step Functions Failures

| # | Severity | Failure Mode | Impact | Mitigation |
|---|---|---|---|---|
| FM-08 | HIGH | Agent Lambda timeout at 14:59 | SFN receives timeout error. Default retry policy = infinite. Agent re-invoked endlessly. | Set `MaxAttempts: 2` on all Task retries. Add SFN alarm on execution duration. |
| FM-09 | HIGH | SFN execution throttled | Concurrent execution limit (1M standard, but account-level). Monday spike: multiple workflows launched simultaneously. | Pre-check execution count. Queue excess workflows. |
| FM-10 | MEDIUM | Claim-check S3 read fails | Agent output stored in S3 (claim-check pattern). S3 returns 503. Next state receives empty input. | Add S3 read retry with exponential backoff. Validate payload before state transition. |
| FM-11 | MEDIUM | State machine input exceeds 256KB | Claim-check not applied consistently. Some agent outputs passed inline. Large outputs cause SFN InputSizeLimitExceeded. | Add payload size check in every agent handler's output path. |
| FM-12 | MEDIUM | SFN retry causes double-risk-check | Idempotency broken on risk check. Retry path re-evaluates risk with stale data. Could produce different result. | Risk check result cached by execution_id + step_name. |

### 5.3 2FA Race Conditions (CRITICAL)

| # | Severity | Failure Mode | Impact | Mitigation |
|---|---|---|---|---|
| FM-01 | CRITICAL | User approves after timeout + auto-reject | DynamoDB item updated to REJECTED (TTL). User taps APPROVE on Telegram. No atomic CAS — approval overwrites rejection. SFN `sendTaskSuccess` called after `sendTaskFailure`. | DynamoDB conditional write: `ConditionExpression: status = PENDING`. Reject any non-PENDING transitions. |
| FM-13 | HIGH | Duplicate approval from double-tap | User taps APPROVE twice in quick succession. Two Lambda invocations both call `sendTaskSuccess`. Second call fails but no error handling. | Idempotency on `taskToken`. DynamoDB conditional write on approval count. |
| FM-14 | HIGH | Telegram service down | SFN `waitForTaskToken` has no timeout configured. Waits indefinitely. Order never placed, never rejected. Pipeline stuck. | Add `HeartbeatSeconds: 300` and `TimeoutSeconds: 600` on waitForTaskToken state. |

### 5.4 Risk Engine Bypass Scenarios (CRITICAL)

| # | Severity | Failure Mode | Impact | Mitigation |
|---|---|---|---|---|
| FM-02 | CRITICAL | Risk Engine Lambda fails → SFN continues | No `Catch` block on CheckRiskLimits state. Lambda error = SFN default behavior (retry then fail workflow). But if retry succeeds with stale data, order proceeds. | Explicit `Catch` on ALL errors → route to HALT state. No fallthrough to order submission. |
| FM-15 | HIGH | DynamoDB position cache stale | Risk Engine reads `qitp_risk_state` which may not reflect latest IBKR positions. 30-second cache TTL but no freshness validation. | Add `last_synced_at` field. Reject if stale > 60 seconds. Force sync before risk check. |
| FM-16 | HIGH | Concentration check uses stale NAV | Net Asset Value from last IBKR sync (could be hours old). New position sizing based on old NAV. Actual concentration exceeds limit. | Real-time NAV query from IBKR before concentration calculation. |

### 5.5 Data Consistency

| # | Severity | Failure Mode | Impact | Mitigation |
|---|---|---|---|---|
| FM-17 | HIGH | S3 write succeeds, DynamoDB catalog write fails | Artifact stored in S3 but not registered in `qitp_artifacts` table. Orphaned artifact. Unretrievable via artifacts-mcp. | Two-phase: write S3 → write DynamoDB → confirm. On DynamoDB failure, delete S3 object. Or: use DynamoDB Streams to trigger S3 write. |
| FM-18 | MEDIUM | Multiple SFN executions modify risk_state simultaneously | Two workflows update `qitp_risk_state` concurrently. Last-write-wins. Position count incorrect. | DynamoDB optimistic locking with version attribute. Conditional writes on all risk_state mutations. |

### 5.6 Agent Hallucination Risks

| # | Severity | Failure Mode | Impact | Mitigation |
|---|---|---|---|---|
| FM-19 | HIGH | LLM generates invalid JSON order parameters | Agent outputs `{"symbol": "AAPL", "quantity": "one hundred"}` instead of integer. No Pydantic validation on agent output before MCP tool call. | Pydantic structured output validation. `response_model` on all agent `.invoke()` calls. |
| FM-20 | MEDIUM | Agent recommends delisted stock | Agent hallucinates a ticker from training data. No watchlist enforcement. Order submitted for non-existent symbol. | Validate all symbols against `qitp_watchlist` before order submission. |
| FM-21 | MEDIUM | Agent hallucinates confidence=1.0 for fake news | No source quality weighting. Agent treats all sentiment sources equally. Fabricated news article given maximum confidence. | Source credibility scoring. Minimum source count threshold for high-confidence signals. |

### 5.7 Cascading Failures

| # | Severity | Failure Mode | Impact | Mitigation |
|---|---|---|---|---|
| FM-22 | HIGH | MCP crash → agent retry → timeout storm | MCP Fargate task OOM. Agent retries 3x. Each retry starts new MCP connection. 100 agents retry simultaneously. ECS task launch rate exceeded. | Circuit breaker pattern on MCP client. After 2 failures, fast-fail for 60 seconds. |
| FM-23 | MEDIUM | DynamoDB throttling cascade | audit_log table overwhelmed by concurrent writes from 100 sentiment analysis tasks. Throttling cascades to risk_state reads. | Separate DynamoDB tables on independent partitions. Write-behind buffer for audit_log (SQS queue). |

### 5.8 Clock Skew & Timezone

| # | Severity | Failure Mode | Impact | Mitigation |
|---|---|---|---|---|
| FM-24 | MEDIUM | Lambda UTC vs IBKR exchange time vs Spain CET | Gap calculation uses UTC timestamps. IBKR returns exchange-local time. Market open comparison fails across DST boundaries. | Normalize all timestamps to UTC at ingestion. Use `pytz` with explicit timezone on all datetime operations. |
| FM-25 | MEDIUM | DST transitions (Spain October/March) | EventBridge schedule `cron(30 8 ? * MON *)` fires at 08:30 UTC year-round. But Madrid is UTC+1 (winter) or UTC+2 (summer). Monday analysis starts at wrong local time. | Use `at` expression with timezone: `at(timezone=Europe/Madrid)`. Or: adjust cron seasonally via Lambda. |

### 5.9 Concurrency

| # | Severity | Failure Mode | Impact | Mitigation |
|---|---|---|---|---|
| FM-26 | HIGH | Two SFN executions place order for same symbol | Concurrent workflows (manual trigger + scheduled). Both pass risk check. Both place order. Double position size. | Symbol-level lock in DynamoDB. Conditional write: `attribute_not_exists(symbol_lock)` with TTL. |
| FM-27 | MEDIUM | Watchlist modified during analysis | User adds/removes symbols via CLI while SFN pipeline running. Gap detection uses stale watchlist. | Snapshot watchlist at SFN start. Pass as state input. Ignore live modifications until next run. |

### 5.10 Idempotency (CRITICAL)

| # | Severity | Finding | Detail |
|---|---|---|---|
| FM-03 | CRITICAL | Idempotency key format not defined | No convention for idempotency keys across any write operation. Each agent/MCP defines (or doesn't define) its own approach. |
| FM-28 | CRITICAL | No idempotency store | No `qitp_idempotency` DynamoDB table. No TTL-based deduplication. All agent handlers vulnerable to retry-induced duplicates. |
| FM-29 | HIGH | Check-cache-execute-cache pattern not implemented | All agent handlers must: (1) check idempotency cache, (2) if miss → execute, (3) store result in cache. Zero handlers implement this today. |

**Required idempotency key format:**

```
{agent_id}:{execution_id}:{operation}:{hash(parameters)}
```

**Required DynamoDB table:**

```yaml
TableName: qitp_idempotency
PartitionKey: idempotency_key (S)
Attributes:
  - result: S (JSON serialized)
  - created_at: N (epoch)
  - ttl: N (epoch + 86400)  # 24-hour TTL
```

### Go-Live Checklist (Failure Modes)

- [ ] 2FA atomic state transition with DynamoDB conditional writes
- [ ] 2FA timeout validation (`HeartbeatSeconds` + `TimeoutSeconds` on waitForTaskToken)
- [ ] Risk Engine explicit fail-safe in SFN (`Catch` on ALL errors → HALT state)
- [ ] Risk Engine position freshness check (reject if stale > 60s)
- [ ] Idempotency keys defined and implemented across all agents
- [ ] Idempotency DynamoDB table provisioned with TTL
- [ ] Scarlet recovery for `place_order` HTTP 500 (post-error position check)
- [ ] Concurrent execution prevention per symbol (DynamoDB lock)
- [ ] Pydantic structured output validation on all agent outputs
- [ ] SFN Retry policy limits (`MaxAttempts: 2` on all Task states)
- [ ] MCP circuit breaker (fast-fail after 2 consecutive failures)
- [ ] Watchlist snapshot at SFN execution start

---

## Section 6: Strands SDK & AgentCore Correctness

### 6.1 Strands SDK API Issues

| # | Severity | Finding | Detail |
|---|---|---|---|
| SDK-01 | HIGH | Hook event mutability not leveraged | `BeforeToolInvocation` hook can modify/block tool calls. Not used for constraint enforcement (e.g., preventing backtest agent from calling ibkr-mcp). This is the Phase 1 alternative to Cedar policies. |
| SDK-02 | HIGH | extended_thinking config missing from blueprint YAML schema | P02 blueprint schema does not include `extended_thinking` or `thinking_budget` parameters. Portfolio Recommender (P11) requires extended thinking but has no blueprint-level configuration. |
| SDK-03 | MEDIUM | Tool docstring format inconsistency | MCP tools use OpenAPI-style descriptions. `@tool` decorated functions use Python docstrings. Strands SDK parses both but formatting affects LLM tool selection quality. |

### 6.2 MCP Client Usage

| # | Severity | Finding | Detail |
|---|---|---|---|
| SDK-04 | HIGH | MCP connection lifecycle risk | Module-level `MCPClient()` caching leaks connections across Lambda warm invocations. Must use `with MCPClient() as client:` context manager per invocation. Plans mention this rule but code patterns in P02 examples show module-level initialization. |
| SDK-05 | HIGH | Tool discovery timing | Blueprints may attempt MCP connection during Lambda initialization (module import time). If MCP Fargate task not yet healthy, agent initialization fails. Need lazy connection with retry. |
| SDK-06 | MEDIUM | Streamable HTTP transport not configured for production | All development examples use `stdio` transport (subprocess). Production requires `streamable-http` transport. Blueprint YAML schema includes `transport` field but no validation that production uses HTTP. |

### 6.3 Multi-Agent Patterns

| # | Severity | Finding | Detail |
|---|---|---|---|
| SDK-07 | HIGH | Swarm: no per-task retry isolation | Sentiment Analysis Swarm (P09): one task timeout kills entire swarm. No individual task error isolation. Failed symbol should not block other symbols. |
| SDK-08 | MEDIUM | Graph: condition lambda edge cases | Strategy Evaluation Graph (P10): condition functions access `state["key"]`. If key missing (agent didn't produce expected output), `KeyError` crashes graph. No `.get()` with defaults. |
| SDK-09 | MEDIUM | Agents-as-Tools: no nested timeout enforcement | Agent A invokes Agent B as tool. Agent B invokes Agent C. No cumulative timeout. Lambda 15-min limit is only safeguard. |

### 6.4 AgentCore Migration Risks

| # | Severity | Finding | Detail |
|---|---|---|---|
| SDK-10 | HIGH | Dual-mode handler adapter edge cases | Lambda `event` (JSON dict) vs AgentCore `payload` (protobuf-like). Adapter must handle: missing fields, type coercion, nested objects, binary data. No test matrix defined. |
| SDK-11 | MEDIUM | Gateway tool namespace collision | Multiple MCPs may expose tools with same name (e.g., `get_status`). Gateway prefixes with MCP name but blueprint YAML references unprefixed names. Migration requires blueprint updates. |
| SDK-12 | MEDIUM | Cedar policy evaluation timing | Must be pre-execution (before tool invocation). If evaluated during or after, unauthorized action already occurred. Strands hook system supports `BeforeToolInvocation` but Cedar integration not implemented. |

### 6.5 Model Configuration

| # | Severity | Finding | Detail |
|---|---|---|---|
| SDK-13 | MEDIUM | Bedrock cross-region model ID format differs | eu-west-1: `eu.anthropic.claude-sonnet-4-6`. us-west-2: `us.anthropic.claude-sonnet-4-20250514-v1:0`. Blueprint YAML uses one format. Cross-region invocation fails silently. |
| SDK-14 | MEDIUM | extended_thinking `thinking_budget` parameter not in blueprint schema | `thinking_budget` controls max thinking tokens. Not configurable via blueprint YAML. Hardcoded in agent handler code violates no-hardcoding principle. |

### 6.6 Token & Context Limits

| # | Severity | Finding | Detail |
|---|---|---|---|
| SDK-15 | HIGH | Claim-check payload sizing | No automatic size validation before SFN state output. Agent produces 300KB output → SFN rejects → workflow fails. Need automatic claim-check trigger at threshold (e.g., 200KB). |
| SDK-16 | MEDIUM | Prompt overflow risk | Tool results (market data for 100 symbols) can exhaust context window. No token counting before agent invocation. No truncation strategy. |
| SDK-17 | MEDIUM | Blueprint env var templating not implemented | Blueprint YAML contains `{{EXECUTION_MODE}}` placeholders. No template engine resolves these. Values used literally as strings. |
| SDK-18 | MEDIUM | No model fallback configuration | Blueprint specifies single model. If Bedrock returns 429 (rate limit), no fallback to alternative model or region. |
| SDK-19 | MEDIUM | Agent memory/conversation history unbounded | Multi-turn agents accumulate context without pruning. Long-running analysis exceeds context window. No sliding window or summarization strategy. |

---

## Section 7: Remediation Roadmap

### Phase 0 — Immediate (Before ANY Deployment)

**Cross-plan fixes (configuration-only, no code changes):**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-01 | Fix DynamoDB session table naming — standardize to `qitp_{env}_sessions` | 1 hour | P17, P19 |
| R-02 | Add missing DynamoDB tables to P11 CDK: `qitp_2fa_credentials`, `qitp_2fa_yubikeys`, `qitp_risk_config` | 2 hours | P11 |
| R-03 | Standardize S3 bucket naming to `qitp-{env}-*` pattern across all plans | 1 hour | All |
| R-04 | Fix artifact parameter name mismatch: P06 `data=` vs P08 `content=` | 30 min | P06, P08 |
| R-05 | Add `technical_analysis` to P06 artifact type enumeration | 15 min | P06 |
| R-06 | Add P04 as explicit dependency for P10 in TODO.md | 5 min | TODO.md |
| R-07 | Add port 8009 (technical-mcp) to CLAUDE.md MCP table | 5 min | CLAUDE.md |

### Phase 1 — Before POC Validation (P13)

**Financial:**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-08 | Implement survivorship bias filter in historical data pipeline | 4 hours | P03 |
| R-09 | Add gap-specific slippage model to simulation engine | 8 hours | P03 |
| R-10 | Document IBKR EU tiered commission model in simulation config | 2 hours | P03 |

**Security:**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-11 | Add pip-audit + Dependabot to CI/CD pipeline | 4 hours | P01 |
| R-12 | Implement strict Pydantic input validation on all MCP tool parameters | 16 hours | All MCPs |
| R-13 | Add S3 Block Public Access to all bucket CDK constructs | 1 hour | P11 |
| R-14 | Implement per-agent rate limits via DynamoDB `qitp_agent_quotas` table | 8 hours | P02 |

**SDK:**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-15 | Fix MCP connection lifecycle — enforce `with MCPClient():` per invocation | 4 hours | P02 |
| R-16 | Add env var templating (`{{VAR}}`) to blueprint loader | 4 hours | P02 |
| R-17 | Add claim-check size validation (auto-redirect to S3 above 200KB) | 4 hours | P10 |

### Phase 2 — Before Paper Trading

**Financial:**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-18 | RTS 25 transaction reporting Lambda + ARM integration | 40 hours | P14 |
| R-19 | CNMV dynamic ban list sync (EventBridge daily + DynamoDB) | 8 hours | P16 |
| R-20 | ISIN lookup service (Polygon reference data) | 8 hours | P14 |
| R-21 | Corporate action monitoring Lambda (splits, dividends) | 16 hours | P14 |
| R-22 | IRPF tax lot tracking with 2-month aggregation rule | 24 hours | P25 |
| R-23 | Dividend withholding tax tracking (US 15% treaty rate) | 8 hours | P25 |
| R-24 | FX rate selection service (ECB daily XML feed) | 4 hours | P25 |

**Security:**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-25 | Migrate all secrets to Secrets Manager with rotation schedules | 16 hours | P17 |
| R-26 | Implement 5 core Cedar policies (see CLAUDE.md examples) | 16 hours | P19 |
| R-27 | Add mTLS between agent Lambdas and MCP Fargate tasks | 24 hours | P17 |
| R-28 | Docker image signing with Cosign in CI/CD | 8 hours | P01 |

**Operations:**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-29 | Define on-call rotation (PagerDuty/Opsgenie integration) | 8 hours | P18 |
| R-30 | Define SLOs for pipeline, agents, risk engine, 2FA | 4 hours | P18 |
| R-31 | Write runbooks: circuit breaker, PITR restore, failover, prompt corruption | 16 hours | P18 |
| R-32 | Implement CloudWatch log archival to S3 Glacier (Kinesis Firehose pipeline) | 16 hours | P18 |

**Failure Modes:**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-33 | 2FA atomic state transitions (DynamoDB conditional writes) | 8 hours | P15 |
| R-34 | Risk Engine fail-safe in SFN (explicit Catch → HALT on ALL errors) | 4 hours | P12, P16 |
| R-35 | Idempotency key system (`qitp_idempotency` DynamoDB table + handler pattern) | 16 hours | All agents |
| R-36 | Symbol-level order locks (DynamoDB conditional write with TTL) | 4 hours | P14 |
| R-37 | Pre-order IBKR session validation (`validate_session()` before `place_order`) | 4 hours | P14 |
| R-38 | Scarlet recovery for HTTP 500 orders (post-error position check before retry) | 8 hours | P14 |

### Phase 3 — Before Live Trading

**Financial:**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-39 | Overnight gap risk modeling (VaR for open positions) | 16 hours | P16 |
| R-40 | Correlation-adjusted sector concentration check | 8 hours | P16 |
| R-41 | Liquidity risk check (position size vs avg daily volume) | 4 hours | P16 |
| R-42 | Partial fill handling (residual order management) | 16 hours | P14 |
| R-43 | Order rejection recovery (retry logic + user notification) | 8 hours | P14 |
| R-44 | Market halt detection and SFN timeout adjustment | 8 hours | P14 |

**Security:**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-45 | Cross-account isolation (dev/staging/prod AWS accounts) | 40 hours | P17 |
| R-46 | Custom KMS CMK with 90-day rotation | 4 hours | P17 |
| R-47 | GDPR data minimization policy + implementation | 16 hours | P17 |
| R-48 | Prompt injection detection layer | 16 hours | P02 |

**Operations:**

| # | Fix | Effort | Plans |
|---|---|---|---|
| R-49 | Multi-region DR (eu-central-1 warm standby) | 40 hours | P17 |
| R-50 | DynamoDB Global Tables for `qitp_risk_state` | 4 hours | P17 |
| R-51 | Blue-green deployment pipeline for live mode | 24 hours | P17 |
| R-52 | Portfolio performance tracking dashboard | 16 hours | P24 |

---

## Section 8: Modularization — Configuration-Driven Architecture

All remediations follow the **configuration-over-code** principle (AIDLC). No thresholds, rules, or business logic hardcoded in application code. Agents read configuration at runtime and reason about config, not code.

| Configuration Layer | Storage | Refresh Mechanism | Examples |
|---|---|---|---|
| Risk rules & thresholds | DynamoDB `qitp_risk_config` | On-demand (CLI update) | `max_positions=5`, `daily_loss_limit=-3%`, `max_sector_concentration=40%` |
| CNMV ban list | DynamoDB `qitp_cnmv_ban_list` | Daily (EventBridge → Lambda) | Banned ISINs for IBEX35 short selling |
| Tax configuration | DynamoDB `qitp_tax_config` | Manual (annual review) | `cost_basis=FIFO`, `aggregation_window=60d`, `us_treaty_withholding=0.15` |
| ISIN reference | S3 `qitp-{env}-artifacts/isin-reference/latest.parquet` | Daily (Polygon API Lambda) | Symbol-to-ISIN mapping for RTS 25 |
| FX rates | S3 `qitp-{env}-artifacts/fx-rates/ecb-daily/` | Daily (ECB XML feed Lambda) | EUR/USD closing rates for P&L and tax reporting |
| Market calendar | DynamoDB `qitp_market_calendar` | Quarterly (manual + Lambda) | US/EU/Asia holidays, DST transition dates, half-days |
| Agent quotas | DynamoDB `qitp_agent_quotas` | Per-hour TTL | `max_invocations` per agent per tool per hour |
| Idempotency cache | DynamoDB `qitp_idempotency` | 24h TTL (auto-expire) | `{agent_id}:{execution_id}:{operation}:{param_hash}` |
| Circuit breaker state | DynamoDB `qitp_risk_state` | Real-time (conditional writes) | `CLOSED` / `OPEN` / `HALF_OPEN` per rule |
| Blueprint templates | S3 YAML | On deploy (CI/CD) | Agent configs with `{{EXECUTION_MODE}}` substitution |
| Commission schedule | DynamoDB `qitp_commission_config` | On change | IBKR tiered rates per exchange per instrument type |
| Prompt versions | DynamoDB `qitp_prompt_registry` + S3 | On publish (CLI) | Prompt text, version, model compatibility, A/B test weights |

**Total new DynamoDB tables required (not in current plans):**

| Table | Purpose | Provisioned In |
|---|---|---|
| `qitp_cnmv_ban_list` | CNMV short-sell bans | NEW — add to P11 |
| `qitp_tax_config` | Spanish IRPF parameters | NEW — add to P11 |
| `qitp_market_calendar` | Exchange holidays and DST | NEW — add to P11 |
| `qitp_agent_quotas` | Per-agent rate limits | NEW — add to P11 |
| `qitp_idempotency` | Deduplication cache | NEW — add to P11 |
| `qitp_commission_config` | Broker commission tiers | NEW — add to P11 |
| `qitp_risk_config` | Risk rule parameters | Referenced but not provisioned — add to P11 |
| `qitp_2fa_credentials` | Advanced 2FA credentials | P23 needs, not in P11 |
| `qitp_2fa_yubikeys` | YubiKey registrations | P23 needs, not in P11 |

---

## Section 9: Plan-to-Finding Mapping

### Finding Impact Matrix

| Finding | Severity | Affects Plans | Remediation Location | Phase |
|---|---|---|---|---|
| RTS 25 reporting (F-01) | CRITICAL | P14 | New Lambda + SFN post-order hook | 2 |
| CNMV ban list (F-02) | CRITICAL | P16 | New rule + EventBridge sync Lambda | 2 |
| Corporate actions (F-03) | CRITICAL | P14 | New monitoring Lambda | 2 |
| Survivorship bias (F-04) | CRITICAL | P03 | Data prep filter | 1 |
| IRPF 2-month rule (F-05) | CRITICAL | P25 | Tax reporter update | 2 |
| Cedar policies (S-01) | CRITICAL | P02 | BeforeToolInvocation hook (Phase 1), Cedar (Phase 2) | 1+2 |
| IBKR credential rotation (S-02) | CRITICAL | P14, P17 | Secrets Manager + rotation Lambda | 2 |
| SCA scanning (S-03) | CRITICAL | P01 | pip-audit + Dependabot in CI/CD | 1 |
| Input validation (S-04) | CRITICAL | All MCPs | Pydantic validators on all tool parameters | 1 |
| Sensitive MCP approval (S-05) | CRITICAL | P06 | Approval workflow for write operations | 1 |
| Session table naming (C-01) | CRITICAL | P17, P19 | CDK config fix | 0 |
| Missing 2FA tables (C-02) | CRITICAL | P11, P23 | CDK stack addition | 0 |
| Artifact param mismatch (C-05) | HIGH | P06, P08 | Schema alignment | 0 |
| 2FA race condition (FM-01) | CRITICAL | P15 | DynamoDB conditional writes | 2 |
| Risk Engine bypass (FM-02) | CRITICAL | P16, P12 | SFN Catch block | 2 |
| Idempotency keys (FM-03) | CRITICAL | P10, P14, P16 | New DynamoDB table + handler pattern | 2 |
| MCP connection leaks (SDK-04) | HIGH | P02, P10 | Context manager enforcement | 1 |
| Claim-check sizing (SDK-15) | HIGH | P10, P12 | Payload limiter utility | 1 |
| DR plan (O-01) | CRITICAL | P17 | Multi-region architecture | 3 |
| Log archival (O-02) | CRITICAL | P18 | Kinesis Firehose pipeline | 2 |
| PITR runbook (O-03) | CRITICAL | P17 | Documented + tested procedure | 2 |
| On-call rotation (O-04) | CRITICAL | P18 | PagerDuty integration | 2 |

### Plans Most Affected

| Plan | Finding Count | CRITICAL | HIGH | Action Required |
|---|:---:|:---:|:---:|---|
| P14 (ibkr-mcp) | 12 | 3 | 6 | Most impacted — broker integration touches financial, security, failure modes |
| P17 (Production Infra) | 9 | 4 | 3 | DR, secrets, networking, IAM — foundational gaps |
| P16 (Risk Engine) | 8 | 3 | 4 | Bypass scenarios, missing rules, configuration gaps |
| P11 (CDK Stacks) | 7 | 2 | 3 | Missing tables, naming conflicts, encryption |
| P02 (Blueprint Engine) | 6 | 1 | 4 | Schema gaps, MCP lifecycle, Cedar alternative |
| P18 (Observability) | 6 | 2 | 3 | Log archival, alerting, runbooks, on-call |
| P15 (2FA Gate) | 5 | 1 | 3 | Race conditions, timeout handling, audit schema |
| P12 (Weekly Workflow) | 4 | 1 | 2 | SFN Catch blocks, retry policies, claim-check |
| P01 (Repo Scaffold) | 3 | 1 | 1 | CI/CD security (SCA, image signing) |
| P25 (Platform Expansion) | 3 | 1 | 2 | Tax computation (IRPF, FX, dividends) |

---

## Section 10: Comprehensive Go-Live Checklist

### Pre-Deployment (Phase 0)

- [ ] DynamoDB session table naming standardized to `qitp_{env}_sessions`
- [ ] Missing DynamoDB tables added to P11 CDK stack (9 tables listed in Section 8)
- [ ] S3 bucket naming standardized to `qitp-{env}-*` across all plans
- [ ] Artifact parameter name mismatch fixed (P06 `data=` aligned with P08 `content=`)
- [ ] `technical_analysis` added to P06 artifact type enumeration
- [ ] P04 added as explicit dependency for P10 in TODO.md
- [ ] Port 8009 (technical-mcp) added to CLAUDE.md MCP table

### Pre-POC Validation (Phase 1)

**Financial:**
- [ ] Survivorship bias filter implemented in historical data pipeline
- [ ] Gap-specific slippage model added to simulation engine
- [ ] IBKR EU commission tiers documented in simulation config

**Security:**
- [ ] pip-audit + Dependabot enabled on all 17 repos
- [ ] Pydantic input validation on all MCP tool parameters
- [ ] S3 Block Public Access on all buckets
- [ ] Per-agent rate limits via `qitp_agent_quotas` table
- [ ] `BeforeToolInvocation` hook enforcing tool restrictions (Phase 1 Cedar alternative)

**SDK:**
- [ ] MCP `with MCPClient():` context manager enforced per Lambda invocation
- [ ] Blueprint `{{ENV_VAR}}` templating implemented
- [ ] Claim-check auto-redirect for payloads > 200KB

### Pre-Paper Trading (Phase 2)

**Financial:**
- [ ] RTS 25 transaction reporting Lambda operational
- [ ] CNMV ban list daily sync running (EventBridge + Lambda)
- [ ] ISIN lookup service deployed (Polygon reference data)
- [ ] Corporate action monitoring Lambda deployed
- [ ] IRPF tax lot tracking with 2-month aggregation rule
- [ ] Dividend withholding tax tracking (US 15% treaty rate)
- [ ] FX rate service deployed (ECB daily XML feed)

**Security:**
- [ ] All secrets in Secrets Manager with rotation schedules
- [ ] 5 core Cedar policies deployed and tested
- [ ] mTLS between agent Lambdas and MCP Fargate tasks
- [ ] Docker image signing with Cosign in CI/CD
- [ ] Input validation on all agent outputs (Pydantic structured output)

**Operations:**
- [ ] On-call rotation defined and tested (PagerDuty/Opsgenie)
- [ ] SLOs defined for pipeline, agents, risk engine, 2FA
- [ ] Runbooks written and tested: circuit breaker, PITR, failover, prompt corruption
- [ ] CloudWatch log archival to S3 Glacier operational (MiFID II compliance)
- [ ] CloudWatch alarms: data feed loss, IBKR disconnects, Bedrock 429, DynamoDB throttling

**Failure Mode Fixes:**
- [ ] 2FA atomic state transitions (DynamoDB conditional writes with `status = PENDING` check)
- [ ] 2FA timeout configured (`HeartbeatSeconds: 300`, `TimeoutSeconds: 600`)
- [ ] Risk Engine fail-safe (`Catch` on ALL errors → HALT state, no fallthrough)
- [ ] Risk Engine position freshness check (reject if `last_synced_at` > 60s stale)
- [ ] Idempotency table deployed (`qitp_idempotency` with 24h TTL)
- [ ] Idempotency check-cache-execute-cache pattern in all agent handlers
- [ ] Symbol-level order locks (DynamoDB conditional write with TTL)
- [ ] Pre-order IBKR session validation
- [ ] Scarlet recovery for HTTP 500 orders (post-error position check)
- [ ] SFN retry limits (`MaxAttempts: 2` on all Task states)
- [ ] MCP circuit breaker (fast-fail after 2 consecutive failures)
- [ ] Watchlist snapshot at SFN execution start

### Pre-Live Trading (Phase 3)

**Financial:**
- [ ] Overnight gap risk model (VaR for open positions)
- [ ] Correlation-adjusted sector concentration check
- [ ] Liquidity risk check (position size vs avg daily volume)
- [ ] Partial fill handling implemented and tested
- [ ] Order rejection recovery logic implemented
- [ ] Market halt detection and SFN timeout adjustment
- [ ] MiFID II Best Execution policy document written and reviewed

**Security:**
- [ ] Cross-account isolation (dev/staging/prod in separate AWS accounts)
- [ ] Customer-managed KMS CMK with 90-day rotation
- [ ] GDPR data minimization policy implemented
- [ ] Prompt injection detection layer active

**Operations:**
- [ ] Multi-region DR operational (eu-central-1 warm standby)
- [ ] DynamoDB Global Tables for `qitp_risk_state`
- [ ] Blue-green deployment pipeline for live mode
- [ ] CI/CD deployment order documented across 17 repos
- [ ] Rollback procedure documented and tested
- [ ] All alerts verified with synthetic failures

**Final Validation:**
- [ ] End-to-end paper trading for 4 consecutive weeks without manual intervention
- [ ] All circuit breakers tested with synthetic triggers
- [ ] 2FA approval/rejection/timeout paths tested end-to-end
- [ ] Risk Engine tested with all 8 rules triggering individually
- [ ] Disaster recovery drill completed (simulated eu-west-1 failure)
- [ ] Security penetration test on all MCP endpoints
- [ ] Regulatory review with CNMV compliance checklist

---

## Appendix A: Finding Severity Definitions

| Severity | Definition | SLA |
|---|---|---|
| **CRITICAL** | Go-live blocker. Risk of financial loss, regulatory violation, or security breach. | Must fix before deployment to affected environment. |
| **HIGH** | Significant risk. Could cause incorrect behavior, data loss, or compliance gap under specific conditions. | Must fix before paper trading. |
| **MEDIUM** | Moderate risk. Represents technical debt, missing hardening, or incomplete implementation. | Must fix before live trading. |

## Appendix B: Audit Methodology

Six parallel forensic audits were conducted against the complete QITP specification corpus:

1. **Financial & Regulatory Compliance** — ESMA/MiFID II requirements, CNMV regulations, Spanish IRPF tax law, risk modeling completeness, order execution edge cases
2. **Security & IAM** — AWS IAM least-privilege, secrets management, network security, encryption, supply chain, GDPR, attack surface analysis
3. **Cross-Plan Consistency** — Schema alignment across 25 plans, naming conventions, dependency graph completeness, configuration consistency
4. **AWS Cost & Operations** — Cost estimation per environment, disaster recovery, backup strategy, scaling analysis, operational readiness, deployment pipeline
5. **Failure Modes & Edge Cases** — IBKR connection failures, SFN failure paths, 2FA race conditions, Risk Engine bypass scenarios, data consistency, cascading failures, concurrency
6. **Strands SDK & AgentCore Correctness** — SDK API usage, MCP client lifecycle, multi-agent pattern correctness, AgentCore migration risks, model configuration, token/context limits

Each audit independently reviewed all 25 implementation plans (P01–P25), 8 design documents (QITP_Doc1–Doc8), and the CLAUDE.md architecture specification.

## Appendix C: Document Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-03-16 | Forensic Audit Team | Initial audit — 150 findings across 6 dimensions |
