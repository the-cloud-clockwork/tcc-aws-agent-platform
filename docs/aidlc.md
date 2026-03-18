QUANTITATIVE INTELLIGENCE TRADING PLATFORM
QITP
Document 8: AI-DLC Integration & Engineering Lifecycle
Adapting QITP to AWS AI-Driven Development Life Cycle — By Design


# 1. What is AI-DLC?
AI-Driven Development Life Cycle (AI-DLC) is a methodology introduced by AWS in July 2025 that repositions AI as a central collaborator in the software development process — not a passive code completion assistant, and not a fully autonomous agent. It sits precisely in the productive space between those extremes.


## 1.1 The Problem AI-DLC Solves
AWS identified three recurring failure modes in how organizations use AI for software development:


## 1.2 The Three Phases of AI-DLC

## 1.3 New Terminology
AI-DLC replaces traditional Agile terms to reflect its AI-driven, high-velocity nature:

## 1.4 The Open-Source Implementation
AWS open-sourced the AI-DLC workflow implementation in November 2025 at github.com/awslabs/aidlc-workflows (MIT-0 license). Current version: v0.1.6 (March 2026). 618 stars, 132 forks. The implementation consists of workflow scaffolds — Rules or Steering customizations — for AI coding agents. Supported platforms: Kiro, Amazon Q Developer, Cursor IDE, Cline, Claude Code CLI, GitHub Copilot.
Core rule file: core-workflow.md (placed as CLAUDE.md for Claude Code)
Detail rules: .aidlc-rule-details/ directory with common/, inception/, construction/, operations/ subdirectories
Extension system: add custom rules (security, compliance, org-specific) under extensions/ directory
Usage trigger: start any chat with 'Using AI-DLC, ...' — workflow activates automatically
All artifacts generated in aidlc-docs/ directory within the project repo


# 2. Why AI-DLC is the Right Foundation for QITP
QITP is not a typical software project. It is an evolving, AI-native platform that will be continuously modified — new strategies added, prompts iterated, agents upgraded, MCP skills extended. This is exactly the use case AI-DLC was designed for.


## 2.1 QITP-to-AI-DLC Principle Mapping

## 2.2 QITP Development Phases as AI-DLC Phases
The QITP development process maps directly onto the three AI-DLC phases. This is not a coincidence — it is a design decision. Every time a new feature, strategy, or agent is developed for QITP, the AI-DLC process governs how it is built.



# 3. QITP Repository Structure with AI-DLC
The QITP GitHub repository is structured to accommodate AI-DLC workflow scaffolds alongside the platform code. AI-DLC rules live in the repo and are version-controlled alongside the code they govern.

## 3.1 Claude Code Integration (Primary Agent)
QITP uses Claude Code CLI as the primary coding agent (already installed in the dev environment at ~/.local/bin/claude). AI-DLC integrates via CLAUDE.md at the project root.

qitp/
├── CLAUDE.md                          # AI-DLC core-workflow.md (copied here)
│                                      # Activates AI-DLC in Claude Code CLI
├── .aidlc-rule-details/               # AI-DLC detail rules
│   ├── common/                        # Cross-phase rules
│   ├── inception/                     # Requirements, stories, units of work
│   ├── construction/                  # Architecture, code, tests
│   ├── operations/                    # IaC, deployment, monitoring
│   └── extensions/                    # Custom QITP extensions (see below)
│       ├── financial/                 # QITP-specific financial domain rules
│       ├── security/                  # Security baseline (from aidlc-workflows)
│       └── compliance/                # CNMV, MiFID II, regulatory rules
│
├── aidlc-docs/                        # AI-DLC generated artifacts (auto-created)
│   ├── inception/                     # Requirements, stories, risk assessments
│   ├── construction/                  # Architecture decisions, design docs
│   └── operations/                    # Deployment plans, runbooks
│
├── blueprints/                        # QITP platform blueprints
│   ├── agents/
│   ├── workflows/
│   └── strategies/
├── prompts/                           # Prompt Registry source files
├── infra/                             # CDK Python stacks
├── agents/                            # Strands agent implementations
├── mcps/                              # MCP server implementations
└── tests/

## 3.2 Setup Commands for QITP Repo
Run once after cloning the QITP repository:

# Download latest AI-DLC release
curl -L https://github.com/awslabs/aidlc-workflows/releases/latest/download/aidlc-rules.zip -o /tmp/aidlc.zip
unzip /tmp/aidlc.zip -d /tmp/aidlc

# Install AI-DLC for Claude Code
cp /tmp/aidlc/aidlc-rules/aws-aidlc-rules/core-workflow.md ./CLAUDE.md
mkdir -p .aidlc-rule-details
cp -R /tmp/aidlc/aidlc-rules/aws-aidlc-rule-details/* .aidlc-rule-details/

# Verify: ask Claude Code
claude "What AI-DLC instructions are currently active in this project?"


# 4. QITP-Specific AI-DLC Extensions
AI-DLC's extension system allows custom rule files to be layered on top of the core workflow. QITP requires three custom extension categories that enforce domain-specific constraints not covered by the baseline security extension.

## 4.1 Extension: Financial Domain Rules
File: .aidlc-rule-details/extensions/financial/qitp-financial.md


### Financial Domain Rules (All Blocking)

## 4.2 Extension: Compliance Rules (CNMV / MiFID II)
File: .aidlc-rule-details/extensions/compliance/eu-financial.md


## 4.3 Extension: Security Baseline
File: .aidlc-rule-details/extensions/security/baseline/security-baseline.md
Use the baseline security extension from the official aidlc-workflows repo. Key rules relevant to QITP:
No hardcoded credentials — all secrets via AWS Secrets Manager or GitHub Actions OIDC
Least-privilege IAM — each Lambda/ECS task has minimal required permissions
Input validation — all MCP tool inputs validated with Pydantic before processing
mTLS between agent Lambda and MCP containers
API Gateway authentication on any public-facing endpoints (e.g. 2FA approval webhook)


# 5. QITP Development Workflow: Bolts and Units of Work
QITP development uses AI-DLC's 'bolt' concept as the primary delivery rhythm. A bolt is a short, intense work cycle (hours to 1-2 days) that delivers a complete, tested, deployed unit of work. This replaces traditional 2-week sprints.

## 5.1 QITP Bolt Types

## 5.2 Standard Bolt Workflow for QITP
Every bolt follows this AI-DLC sequence. Trigger phrase: 'Using AI-DLC, add [feature] to QITP'

### Phase 1: INCEPTION (Mob Elaboration)
Claude Code reads CLAUDE.md (AI-DLC rules) and activates workflow
AI asks structured clarifying questions: Which blueprint type? Which execution modes affected? Which MCP skills required? Risk implications?
Human provides answers (written in aidlc-docs/inception/questions-{bolt}.md)
AI proposes YAML blueprint schema changes or new YAML file
Human validates: does the blueprint correctly capture the intent?
AI generates Units of Work (parallel implementable tasks)
Human approves decomposition before construction begins

### Phase 2: CONSTRUCTION (Mob Construction)
AI generates implementation: Python agent/MCP code, CDK constructs, test files
AI proposes architecture decisions: which Strands pattern? Lambda or AgentCore? Which MCP transports?
Human provides technical clarification in real time
AI applies all applicable extensions: FIN-001 through FIN-008, COMP-001 through COMP-005, security baseline
AI generates comprehensive test suite: unit tests (mocked), integration test specs
Human reviews code artifacts in aidlc-docs/construction/
Human approves construction artifacts before Operations phase

### Phase 3: OPERATIONS (Deployment Validation)
AI generates CDK deployment plan with cdk diff output
AI proposes Langfuse trace tags, CloudWatch alarms, Grafana widget configs
Human reviews and approves deployment plan
AI executes: cdk deploy, prompt push, strategy promote as appropriate
Human verifies: backtest run for new strategies, smoke test for infrastructure changes
AI generates post-deployment verification checklist
Human signs off: bolt complete


# 6. AI-DLC Applied to QITP Lifecycle Scenarios
Concrete examples of how AI-DLC governs specific QITP development scenarios.

## 6.1 Scenario: Adding a New Trading Strategy

### AI-DLC Inception Output
Questions generated: What trailing stop type? ATR or percentage? What max holding period? Should sentiment score gate the entry?
Blueprint proposal: strategy YAML with id=mean_reversion_large_gap, version=1.0.0, entry conditions, exit conditions, position_sizing
Risk flag raised by AI: 'Large gap strategies have high failure rate after earnings announcements — recommend adding explicit earnings blackout period'
Units of Work decomposed: [UoW-1] YAML blueprint, [UoW-2] backtest validation, [UoW-3] CDK strategy registry update, [UoW-4] Prompt Registry update for Portfolio Recommender

### AI-DLC Construction Output
strategy YAML blueprint file generated in /blueprints/strategies/
backtest_config.json generated for validation run parameters
Portfolio Recommender prompt updated to include new strategy scoring logic
Unit test generated: validates strategy schema against Pydantic model
FIN-004 check passed: backtest_run_id field included in strategy_registry entry template

### AI-DLC Operations Output
backtest run executed: gap_momentum_large_gap vs 2022-2024 historical data
Results: Sharpe 0.71, win rate 52%, max drawdown 8.2% — PASS (all above thresholds)
qitp strategy promote mean_reversion_large_gap 1.0.0 executed
Strategy live in next Monday pipeline run

## 6.2 Scenario: Iterating on a Prompt

### AI-DLC Workflow (Construction Phase Only — No Inception)
AI-DLC adaptive workflow correctly identifies this as a Construction-only bolt. No elaborate requirements phase needed.
AI reads current prompt from Prompt Registry (gap_detector_v2.1.0)
AI proposes updated prompt with explicit gap classification instructions and output schema changes
Human reviews: does new prompt correctly handle edge cases (small gaps, holiday Mondays, ETF vs stock behavior)?
AI generates backtest validation test: run Gap Detection Agent with new prompt on 20 known historical gaps, compare classification accuracy
If accuracy improves: qitp prompt push -> qitp prompt promote
Langfuse A/B test configured: 10% traffic to new prompt version for 2 weeks before full rollout

## 6.3 Scenario: New MCP Server from Scratch

### Full Three-Phase Bolt
INCEPTION: AI reads Doc 6 spec, generates clarifying questions — chart library choice (Recharts confirmed), artifact delivery mechanism (artifacts-mcp confirmed), transport (Streamable HTTP confirmed)
CONSTRUCTION: AI generates Python MCP server skeleton, all 7 tool implementations, Recharts JSX templates, Dockerfile, unit tests with mocked data, integration test spec
Extension enforcement: security baseline applied (mTLS config, input validation), FIN-005 verified (no prompts in MCP code)
OPERATIONS: CDK ECS Fargate construct generated, Service Discovery config, health check endpoint, CloudWatch log group, Grafana panel for charting-mcp latency
Human verifies: generate_candlestick test chart renders in Claude UI


# 7. Version Control and Iteration Governance
AI-DLC produces artifacts that must be version-controlled alongside code. QITP has specific conventions for managing the AI-DLC document trail.

## 7.1 What Gets Committed to Git

## 7.2 AI-DLC Document Naming Convention
All AI-DLC generated artifacts in aidlc-docs/ follow this naming pattern:
aidlc-docs/
{phase}/
{bolt-id}_{bolt-name}_{date}/
questions.md          # AI clarifying questions + human answers
plan.md               # AI proposed plan (before approval)
approved-plan.md      # Human-approved plan
artifacts/            # Generated code/config (links or copies)
verification.md       # Human sign-off after execution

Example:
aidlc-docs/
construction/
B023_charting_mcp_2025-03-17/
questions.md
plan.md
approved-plan.md
artifacts/ -> symlinks to mcps/charting-mcp/
verification.md

## 7.3 Bolt Tracking in Plane
Every bolt maps to a Plane ticket in the ROOT project. The bolt ID in aidlc-docs/ references the ROOT ticket number. This creates a traceable link from Plane ticket -> AI-DLC bolt docs -> committed code.
Ticket ROOT-65 (charting-mcp) -> Bolt ID B065 -> aidlc-docs/construction/B065_charting_mcp_*/
Ticket description includes the trigger phrase used with Claude Code
Completion checklist in ticket matches AI-DLC Operations verification checklist
Plane ticket moves to Done only after aidlc-docs/*/verification.md is committed


# 8. QITP AI-DLC Adoption Roadmap

## 8.1 Phase 0: Foundation (Before First Code)
Complete before writing any QITP platform code. These are prerequisites.
Clone aidlc-workflows repo, read core-workflow.md in full
Set up CLAUDE.md + .aidlc-rule-details/ in QITP repo (ROOT-66)
Author three custom extension files: qitp-financial.md, eu-financial.md, extend security-baseline.md
Validate extension loading: start Claude Code, confirm all rules active
Run a dry-run bolt: 'Using AI-DLC, create the initial project README for QITP' — validate the three-phase flow works end-to-end

## 8.2 Phase 1: POC with AI-DLC (Weeks 1-3)
All POC development (ROOT-63) conducted using AI-DLC bolts. Each ROOT ticket = one bolt.

## 8.3 Phase 2: Full Platform Build with AI-DLC (Months 2-4)
All remaining QITP tickets (ROOT-50 through ROOT-66) executed as AI-DLC bolts. By this point the pattern is established and the custom extensions are battle-tested.
Each new MCP server: one bolt, full three-phase AI-DLC process
Each new agent: one bolt, with INCEPTION phase producing the agent YAML blueprint
Each CDK stack: one bolt, OPERATIONS phase produces deployment plan and approval
Every prompt iteration: lightweight Construction-only bolt (no Inception needed)
Every strategy addition: full three-phase bolt with mandatory backtest in OPERATIONS

## 8.4 Continuous Evolution
AI-DLC is not a one-time setup. It is the permanent operating model for QITP development. Every change, no matter how small, starts with a Claude Code session and 'Using AI-DLC, ...'.
Update aidlc-workflows rules when new versions release — commit updated CLAUDE.md
Evolve custom extensions as new compliance requirements emerge (e.g. new ESMA regulations)
Contribute QITP financial domain extension back to awslabs/aidlc-workflows as an example for financial services teams


# 9. Concrete Benefits of AI-DLC for QITP

## 9.1 Velocity
New strategy from idea to live: target 1-2 days (vs weeks in traditional SDLC)
Prompt iteration cycle: 2-4 hours (vs days of manual testing)
New MCP tool: 4-8 hours (vs multi-day implementation + review cycles)
AI generates boilerplate: Pydantic schemas, CDK constructs, test stubs — human focuses on business logic

## 9.2 Quality
Extension enforcement: no code passes Construction without satisfying FIN-001 through FIN-008
Backtest-before-deploy: every strategy mathematically validated before touching live money
Comprehensive test generation: AI produces unit + integration tests, not just implementation
Architecture consistency: all agents follow same blueprint pattern because AI reads the same rules

## 9.3 Safety
Compliance rules as blocking constraints: COMP-001 through COMP-005 cannot be skipped
Human approval at every gate: 2FA for orders, bolt approval for deployments
Full audit trail: every AI-DLC bolt documents the reasoning behind every architectural decision
Rollback capability: every change is a bolt — revert by reverting the bolt's commits

## 9.4 Maintainability
aidlc-docs/ directory is a living engineering journal — 6 months later, understand why any decision was made
New team member onboarding: read CLAUDE.md + aidlc-docs/ to understand the entire platform evolution
Prompt experiments traceable: every prompt version change has a bolt document explaining the hypothesis and validation result

# 10. Quick Reference

## 10.1 Key Commands

## 10.2 AI-DLC Extension Rule File Template
# Extension: [Extension Name]

## Question: [Extension Category] Extensions
Should [category] rules be enforced for this task?

A) Yes - enforce all [CATEGORY] rules as blocking constraints
B) No - skip (reason: [describe when to skip])
X) Other (please describe)

[Answer]:

---

## Rule [CATEGORY]-001: [Rule Name]

### Rule
[Description of what must be true]

### Verification
- [ ] [Concrete check 1]
- [ ] [Concrete check 2]
- [ ] [Concrete check 3]

---

## 10.3 Resources


END OF DOCUMENT 8 — QITP AI-DLC Integration & Engineering Lifecycle

COMPLETE QITP DOCUMENT SET: Documents 1-8 | March 2026

| Version: 1.0 — March 2026 | Author: Nestor Colt | Status: DRAFT |
| --- | --- |
| Source: awslabs/aidlc-workflows (v0.1.6) | Reference: AWS DevOps Blog, July + Nov 2025 |


| Core Mental Model
AI creates a plan. AI seeks clarification. Humans validate the plan. AI executes. Humans verify the outcome. This loop repeats rapidly for every SDLC activity. AI accelerates; humans remain the compass. |
| --- |


| Problem | Symptom | AI-DLC Solution |
| --- | --- | --- |
| One-size-fits-all workflows | Simple bug fixes forced through same 12-step process as new system design | Principle 10: AI recommends the pathway, not the tool. Workflow adapts to intent. |
| Lack of flexible depth | Over-engineered artifacts for simple tasks; under-engineered for complex ones | AI modulates both breadth (stages selected) and depth (rigor per stage) to match complexity |
| Tools that reduce human oversight | Developers become passive — AI decides everything, humans rubber-stamp | Mob Elaboration and Mob Construction rituals. Human approvals at every decision gate. Auditability built-in. |


| Phase | Focus | Key Activities | Human Role |
| --- | --- | --- | --- |
| INCEPTION | WHAT to build, WHY | Requirements analysis, user stories, units of work, risk assessment, complexity evaluation | Mob Elaboration: validate AI's questions and proposals in real time |
| CONSTRUCTION | HOW to build it | Architecture proposals, domain models, code generation, test strategies, quality assurance | Mob Construction: clarify technical decisions and architectural choices |
| OPERATIONS | Deploy and run it | Infrastructure as code, deployment automation, monitoring, production readiness | Review and approve deployment plans and observability configuration |


| Traditional Term | AI-DLC Term | Key Difference |
| --- | --- | --- |
| Sprint (2 weeks) | Bolt (hours to days) | Far shorter cycles — AI accelerates to day-level delivery |
| Epic | Unit of Work | AI-decomposed, parallelizable delivery unit |
| Sprint Planning | Mob Elaboration | Whole team validates AI's questions and plans in real time |
| Development | Mob Construction | Team provides real-time clarification on technical choices |
| User Story | Intent Statement | Natural language intent that kicks off an AI-DLC workflow |
| Definition of Done | Verification Gate | Human verifies AI execution at each phase boundary |


| The Core Fit
QITP embeds AI-DLC by design — not as a retrofit. The blueprint-driven architecture, prompt registry, versioned strategy library, and simulation-before-deployment validation loop are all expressions of AI-DLC principles applied to an AI-native trading platform. |
| --- |


| AI-DLC Principle | QITP Manifestation | Where Implemented |
| --- | --- | --- |
| AI Powered Execution with Human Oversight | 2FA gate on every live order. Risk Engine is human-configured. No order executes without approval. | Step Functions waitForTaskToken (ROOT-51), Risk Engine (ROOT-60) |
| No Hard-Wired SDLC Workflows (Principle 10) | Blueprint Engine generates workflows from YAML config. Agents have no hardcoded pipeline logic. | Blueprint Engine (ROOT-47), YAML workflow blueprints |
| Adaptive Workflow Depth | Execution mode switching: backtest (lightweight) vs live (full compliance path) | EXECUTION_MODE env var (ROOT-49) |
| Human in the Loop at Decision Gates | 2FA gate, Risk Engine check, circuit breakers — all require human configuration or approval | ROOT-51, ROOT-60, ROOT-16 |
| End-to-End Traceability | Audit log captures every decision, every prompt version, every tool call, every order outcome | qitp_audit_log DynamoDB (ROOT-62) |
| Context Persists Across Phases | AgentCore Memory stores cross-session shared state. Prompt Registry persists reasoning context. | AgentCore Memory (ROOT-15), Prompt Registry (ROOT-48) |
| AI Creates Plan, Humans Approve | Strategy backtests run before any strategy goes live. Simulation validates agent reasoning. | Simulation Engine (ROOT-57), backtest-before-paper rule |
| Reproducible Outcomes | Same YAML blueprint + same prompt version + same data = same agent behavior | Blueprint Engine + Prompt Registry versioning |


| AI-DLC Phase | QITP Inception Activities | QITP Construction Activities |
| --- | --- | --- |
| INCEPTION | Define strategy intent in natural language. AI decomposes into YAML blueprint fields. Mob Elaboration validates entry/exit conditions, risk params, required agents. | N/A (Inception only) |
| CONSTRUCTION | N/A (Inception only) | AI generates Strands agent code, MCP tool implementations, CDK constructs, Step Functions states. Mob Construction validates architecture decisions. |
| OPERATIONS | N/A | AI generates CDK deployment, Langfuse instrumentation, CloudWatch alarms, Grafana dashboards. Human reviews and approves production readiness checklist. |


| Applicability Question (embedded in extension)
Should Financial Domain rules be enforced for this task?
A) Yes — enforce all FINANCIAL rules as blocking constraints
B) No — skip (only for non-financial utility tasks, tests, or infrastructure changes)
X) Other (please describe)

[Answer]: |
| --- |


| Rule ID | Rule Name | Requirement + Verification |
| --- | --- | --- |
| FIN-001 | Execution Mode Gating | Any code that submits orders to IBKR MUST check EXECUTION_MODE. Verification: grep for place_order() calls not preceded by execution_mode check. |
| FIN-002 | 2FA Gate Mandatory | No order submission code may bypass the 2FA gate in live mode. Verification: all place_order() calls must trace through waitForTaskToken state. |
| FIN-003 | Idempotency Keys | All place_order() calls must include an idempotency_key parameter. Verification: grep for place_order without idempotency_key. |
| FIN-004 | Backtest First | No strategy YAML may be added to active registry without a corresponding backtest run. Verification: strategy_registry entry requires backtest_run_id field populated. |
| FIN-005 | Prompt Version Logging | All agent invocations must log prompt_id and prompt_version to structured logs. Verification: all Strands agent instantiations use registry-loaded prompts. |
| FIN-006 | Audit Log Coverage | Every financial event type listed in Document 7 Section 2.2 must have a corresponding audit log write. Verification: all 15 event types have DynamoDB write calls. |
| FIN-007 | Risk Engine Pre-Order | CheckRiskLimits Lambda must be called before any order state in Step Functions. Verification: CDK definition shows risk check state precedes order submission state. |
| FIN-008 | No Hardcoded Prompts | No prompt text may appear in Python agent files. Verification: grep for system_prompt= with inline text (not registry ID) returns empty. |


| Rule ID | Rule Name | Requirement + Verification |
| --- | --- | --- |
| COMP-001 | MiFID II Order Logging | Every order must log: timestamp (ms), symbol, ISIN, venue, price, quantity, order type, rationale. Verification: OrderSubmitted audit event has all 8 fields. |
| COMP-002 | ESMA Leverage Check | Any CFD order must pass ESMALeverageLimitCheck before submission. Verification: ibkr-mcp place_order() includes leverage validation for CFD instruments. |
| COMP-003 | CNMV Short Restriction | Short orders on IBEX35 symbols must check CNMV restriction list. Verification: place_order with action=SSHORT on Spanish symbol calls check_cnmv_restrictions(). |
| COMP-004 | 5-Year Retention | Audit log DynamoDB table TTL must be set to minimum 5 years (157,680,000 seconds). Verification: CDK stack shows TTL attribute set. |
| COMP-005 | Tax Event Logging | All closed positions must be logged with IRPF-required fields for Spanish capital gains reporting. Verification: POSITION_CLOSED audit event has acquisition_date, disposal_date, pnl_eur, commissions. |


| Bolt Type | Duration | AI-DLC Phases | Example |
| --- | --- | --- | --- |
| New Strategy Bolt | 1-2 days | Inception + Construction + Operations | Add gap_momentum_down strategy: YAML blueprint -> backtest -> CDK deploy |
| Prompt Iteration Bolt | 2-4 hours | Construction only | Improve Gap Detection Agent prompt: edit -> push to registry -> backtest validate -> promote |
| New MCP Tool Bolt | 4-8 hours | Construction + Operations | Add get_volume_profile() to market-data-mcp: implement -> unit test -> integration test -> deploy |
| New Agent Bolt | 1-3 days | All three phases | Add Technical Analysis Agent: requirements -> design -> implement -> deploy to AgentCore |
| Infrastructure Bolt | 4-8 hours | Operations only | Add new CloudWatch dashboard widget: CDK change -> plan -> deploy -> verify |
| Bug Fix Bolt | 1-4 hours | Construction only (no Inception needed) | Fix ibkr-mcp reconnection bug: diagnose -> fix -> test -> deploy |


| Trigger Phrase
'Using AI-DLC, add a new mean reversion strategy for stocks that gap up more than 8% with no earnings in the prior 14 days' |
| --- |


| Trigger Phrase
'Using AI-DLC, improve the Gap Detection Agent prompt to better classify gap types (breakaway vs exhaustion vs common)' |
| --- |


| Trigger Phrase
'Using AI-DLC, build the charting-mcp server as specified in Document 6 Section 7' |
| --- |


| Item | Committed? | Notes |
| --- | --- | --- |
| CLAUDE.md (AI-DLC core rules) | Yes | Version controlled — update when aidlc-workflows releases new version |
| .aidlc-rule-details/ (all rule files) | Yes | Including custom QITP extensions |
| aidlc-docs/ (generated artifacts) | Yes | Inception, construction, and operations docs per bolt |
| blueprints/ (YAML blueprints) | Yes | Source of truth for agents, workflows, strategies |
| prompts/ (prompt source files) | Yes | Pushed to Prompt Registry via CI — never hardcoded in code |
| .claude/settings.local.json | No (.gitignore) | Local developer settings only |


| Bolt | Ticket | AI-DLC Trigger Phrase |
| --- | --- | --- |
| B047 | ROOT-47 | 'Using AI-DLC, implement the Blueprint Engine YAML schema with Pydantic validation for agent, workflow, and strategy blueprint types' |
| B049 | ROOT-49 | 'Using AI-DLC, implement the execution mode system — a single EXECUTION_MODE env var that switches all system behavior between backtest, paper, and live without code changes' |
| B048 | ROOT-48 | 'Using AI-DLC, build the Prompt Registry with S3/DynamoDB backend and a CLI for push, get, list, rollback operations' |
| B052 | ROOT-52 | 'Using AI-DLC, build market-data-mcp as specified in Document 6 Section 3, with get_gap and get_watchlist_gaps as the primary tools' |
| B054 | ROOT-54 | 'Using AI-DLC, build the Gap Detection Agent as specified in Document 5 Section — Strands agent, registry-loaded prompt, AgentCore deployment' |


| Action | Command |
| --- | --- |
| Start a new bolt | 'Using AI-DLC, [intent description]' in Claude Code CLI |
| Check active rules | claude '/config' or ask 'What AI-DLC instructions are active?' |
| Update AI-DLC rules | Download new release, cp core-workflow.md ./CLAUDE.md, commit |
| Add new extension rule | Create .aidlc-rule-details/extensions/{category}/{rule}.md, follow extension format |
| View bolt history | ls aidlc-docs/ or git log --all -- aidlc-docs/ |
| Validate CLAUDE.md syntax | Open in Claude Code, ask 'List all active AI-DLC rules' |


| Resource | URL |
| --- | --- |
| AI-DLC Method Definition Paper | https://prod.d13rzhkk8cj2z0.amplifyapp.com/ |
| AWS Blog: AI-DLC Introduction | https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle/ |
| AWS Blog: Open-Sourcing AI-DLC Workflows | https://aws.amazon.com/blogs/devops/open-sourcing-adaptive-workflows-for-ai-driven-development-life-cycle-ai-dlc/ |
| GitHub: awslabs/aidlc-workflows | https://github.com/awslabs/aidlc-workflows |
| Claude Code CLI | https://github.com/anthropics/claude-code |
| Kiro IDE | https://kiro.dev/ |
