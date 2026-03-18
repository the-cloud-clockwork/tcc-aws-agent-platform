# Building a production POC with Strands, AgentCore, and Step Functions

**This AWS-native agentic stack is production-viable today but demands careful architectural choices around payload limits, execution timeouts, and the non-determinism boundary.** The combination of Step Functions (deterministic outer shell), Strands Agents SDK (model-driven reasoning), and Bedrock AgentCore (managed runtime) creates what practitioners call the "Russian Doll" pattern — nested layers of control with increasing autonomy toward the center. The stack is GA, used internally by Amazon Q Developer and AWS Glue, and backed by enterprise customers including Swisscom, Smartsheet, and Thomson Reuters. The primary gotchas are Step Functions' **256KB payload limit**, Lambda's **15-minute ceiling** for complex agent reasoning, and AgentCore's **~23-second cold start** on first session. Model inference (Bedrock tokens) will dominate your bill by 10x over infrastructure.

---

## Strands Agents SDK: the model-driven core

Strands (Apache 2.0, `pip install strands-agents`) reached **1.0 GA on July 15, 2025** and defaults to Claude Sonnet 4 on Bedrock. The fundamental design decision is a model-driven event loop: the LLM controls all routing. There is no hardcoded workflow DAG within a single agent — the model receives the prompt, conversation history, and serialized tool descriptions, then decides whether to respond, reason, or invoke tools. Tool results are injected back into context and the model is re-invoked. The loop terminates when the model returns text without requesting tool calls, or when `max_iterations`/`max_execution_time` limits hit.

Agent definition is deliberately minimal. Three lines get you a working agent:

```python
from strands import Agent
agent = Agent()  # Defaults to Claude Sonnet 4 on Bedrock us-west-2
agent("Analyze the Q3 revenue trends")
```

For production, you wire up explicit model configuration, tools, hooks, and session management:

```python
from strands import Agent, tool, ModelRetryStrategy
from strands.models import BedrockModel

@tool
def fetch_metrics(quarter: str, metric: str) -> dict:
    """Retrieve business metrics for a given quarter.
    
    Args:
        quarter: Fiscal quarter (e.g., "Q3-2025")
        metric: Metric name (e.g., "revenue", "churn")
    """
    # Your data layer here
    return {"quarter": quarter, "metric": metric, "value": 14.2}

model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
    region_name="us-west-2",
    temperature=0.3,
    max_tokens=4096,
    cache_prompt="default",   # System prompt caching
    cache_tools="default",    # Tool definition caching
)

agent = Agent(
    model=model,
    system_prompt="You are a financial analyst. Return structured JSON.",
    tools=[fetch_metrics],
    retry_strategy=ModelRetryStrategy(max_attempts=3, initial_delay=2, max_delay=60),
    max_iterations=10,
    max_execution_time=120,
)
```

The `@tool` decorator converts any typed Python function into an agent tool. The docstring becomes the tool description the LLM sees; type hints generate the parameter schema. Strands also supports Pydantic-based structured output via `agent.structured_output(prompt, output_model=MyModel)`.

### Multi-agent patterns ship four primitives

Strands 1.0 introduced four composable multi-agent patterns. **Agents-as-Tools** is hierarchical delegation — wrap a specialist agent as a `@tool` callable from an orchestrator. **Swarms** are self-organizing teams with shared memory, automatic handoffs, and fault tolerance (configurable via `execution_timeout`, `node_timeout`, and `max_handoffs`). **Graphs** provide deterministic inter-agent routing via `GraphBuilder` with Python condition functions on edges. **Handoffs** enable explicit control transfer between agents.

The Graph pattern directly answers the conditional branching question. Between agents, routing is **fully deterministic** via Python condition functions — no model involvement:

```python
from strands import Agent
from strands.multiagent import GraphBuilder

analyzer = Agent(name="analyzer", system_prompt="Categorize request severity")
normal_handler = Agent(name="normal", system_prompt="Handle routine requests")
critical_handler = Agent(name="critical", system_prompt="Handle urgent requests")

builder = GraphBuilder()
builder.add_node(analyzer, "analyze")
builder.add_node(normal_handler, "normal")
builder.add_node(critical_handler, "critical")

builder.add_edge("analyze", "normal", 
    condition=lambda state: state.get("severity") == "low")
builder.add_edge("analyze", "critical", 
    condition=lambda state: state.get("severity") == "high")
builder.set_entry_point("analyze")

graph = builder.build()
result = graph("Customer reports system outage")
```

**Critical distinction**: within a single agent's loop, routing is always model-driven (non-deterministic). Between agents in a Graph, routing can be fully deterministic. For workflows that need end-to-end determinism — "always A, then B, then C" — use Step Functions, not Strands.

### MCP integration is first-class

Strands supports stdio, Streamable HTTP, and SSE transports natively via `MCPClient`. MCP tools become indistinguishable from native `@tool` functions once loaded:

```python
from mcp import stdio_client, StdioServerParameters
from strands import Agent
from strands.tools.mcp import MCPClient

mcp = MCPClient(lambda: stdio_client(
    StdioServerParameters(command="uvx", 
        args=["awslabs.aws-documentation-mcp-server@latest"])
))

with mcp:
    agent = Agent(tools=mcp.list_tools_sync())
    agent("What are the Lambda concurrency limits?")
```

Multiple MCP servers combine trivially: `Agent(tools=server_a.list_tools_sync() + server_b.list_tools_sync())`. One gap: there is **no configurable retry strategy for MCP tool calls** (GitHub issue #675) — failures go back to the LLM rather than retrying at the transport level.

### Hooks provide lifecycle control

The hook system replaces the older `callback_handler` with strongly-typed events. Key writable events include `BeforeToolInvocationEvent` (swap the selected tool), `AfterToolInvocationEvent` (set `event.retry = True` to re-execute), and `AfterModelInvocationEvent` (set `event.retry_model = True` to discard and re-invoke). Implementation follows a `HookProvider` pattern:

```python
from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import BeforeToolInvocationEvent, AfterToolInvocationEvent

class GuardrailHooks(HookProvider):
    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(AfterToolInvocationEvent, self.check_tool_result)
    
    def check_tool_result(self, event: AfterToolInvocationEvent):
        if event.exception and self.is_transient(event.exception):
            event.retry = True  # SDK re-executes the tool

agent = Agent(hooks=[GuardrailHooks()])
```

Multi-agent-specific hooks (BeforeHandoffEvent, graph node events) are tracked in GitHub issue #791 but not yet shipped.

### A2A protocol support is native

Strands 1.0 supports Google's Agent-to-Agent protocol. `A2AServer` auto-generates an agent card and serves it at `/.well-known/agent.json`. Remote A2A agents from any framework can be consumed via the `a2a_client` tool provider and used inside any Strands multi-agent pattern.

### Session management persists across restarts

`SessionManager` abstracts conversation state persistence. Built-in backends include **file-based** and **S3**. For production, the AgentCore Memory integration (covered below) provides managed short-term, long-term, and episodic memory with semantic retrieval.

### Known limitations to design around

**No native branch cancellation** in Graph patterns — once a branch starts, there's no mechanism to cancel in-flight branches. **No checkpoint/resume** for long-running agents (GitHub issue #1369). **No intelligent retry on structured output validation failures** (issue #348). **Context window growth** is linear — you must implement summarization or session windowing for extended conversations. **Agent quality is model-dependent** — weaker models loop excessively or make poor tool selections.

---

## Amazon Bedrock AgentCore: the managed runtime layer

AgentCore is **not a single service but a suite of nine modular services** — Runtime, Memory, Gateway, Identity, Observability, Browser, Code Interpreter, Policy (preview), and Evaluations (preview). It went GA on **October 13, 2025** across 9 AWS regions. The critical distinction from regular Bedrock Agents: AgentCore is a **framework-agnostic infrastructure platform**. Bedrock Agents is a managed, configuration-based agent builder; AgentCore is the runtime and ops layer where you bring your own framework (Strands, LangGraph, CrewAI, or anything else) and model.

### Runtime uses Firecracker microVMs for session isolation

Each session gets a **dedicated Firecracker microVM** — the same technology powering Lambda and Fargate, but as a distinct managed service. Boot time is **under 125ms** at the VM level, with community-reported end-to-end cold starts of **~23 seconds** for first session and **~9 seconds** for warm sessions. After session completion, the entire microVM is terminated and memory sanitized. Sessions can persist for **up to 8 hours** of active runtime and survive 15 minutes of idle before termination. This is hardware-level isolation — even a compromised agent cannot escape its microVM boundary.

Deploying a Strands agent on AgentCore requires minimal code changes:

```python
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

agent = Agent(
    model=BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"),
    system_prompt="You are an analysis assistant.",
    tools=[fetch_metrics]
)

@app.entrypoint
def invoke(payload):
    result = agent(payload.get("prompt", ""))
    return result.message['content'][0]['text']

if __name__ == "__main__":
    app.run()
```

Deployment uses the Starter Toolkit CLI: `agentcore configure --entrypoint my_agent.py`, then `agentcore launch`. Supports both direct code upload (to S3) and container-based deployment (ECR). IaC via CloudFormation, CDK, and Terraform is fully supported at GA.

### Memory is three-tiered and managed

AgentCore Memory provides **short-term** (multi-turn conversation events), **long-term** (semantic facts, user preferences, session summaries), and **episodic** (structured action-outcome patterns with reflection). The Strands integration uses `AgentCoreMemorySessionManager` as a drop-in session manager:

```python
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager
)

config = AgentCoreMemoryConfig(
    memory_id="mem-12345",
    session_id="sfn-exec-abc123",  # Map to Step Functions execution ID
    actor_id="user-456",
    batch_size=10,
)

with AgentCoreMemorySessionManager(config, region_name='us-east-1') as mgr:
    agent = Agent(session_manager=mgr, ...)
    agent("Analyze this data")
    # All messages auto-flushed on context exit
```

Memory stores can be **shared across agents and sessions**, enabling multi-agent collaboration on shared context. Namespace-based storage provides data segmentation: `/preferences/{actorId}/`, `/facts/{actorId}/`, `/summaries/{actorId}/{sessionId}/`.

### Identity handles both directions

**Inbound**: IAM (SigV4) or OAuth 2.0 with Cognito, Okta, or Microsoft Entra ID. **Outbound**: agents access external services (Slack, GitHub, Salesforce, Google Workspace, Jira) via OAuth, API keys, or user-delegated mode. Secure vault storage handles refresh tokens.

### Pricing is consumption-based with a key advantage

Runtime costs **$0.0895/vCPU-hour** and **$0.00945/GB-hour**, billed per-second on active compute. The differentiator: **I/O wait time is free**. When your agent is waiting for an LLM response, an API call, or a database query — typically 30-70% of execution time — you're not charged if no background process is running. AWS estimates a 10M request/month customer support agent at **~$7,235/month** versus 3.3x more for pre-allocated compute.

---

## Step Functions as the deterministic outer orchestrator

Step Functions provides the auditable, deterministic workflow shell that wraps non-deterministic agent invocations. AWS explicitly positions this pattern — their Prescriptive Guidance series "Agentic AI patterns and workflows on AWS" dedicates Pattern 4 to multi-stage AI workflows with Step Functions as the backbone. In a community comparison building an identical HR evaluation system three ways (Step Functions, Bedrock Agents, Strands), **Step Functions had the lowest latency** (<1 minute versus 2-15 minutes for the others) with the best debugging experience.

### Wrapping a Strands agent in Lambda for Step Functions invocation

The official Strands documentation confirms this as a supported deployment pattern. Initialize the agent **outside** the handler for warm-start reuse:

```python
# lambda/agent_handler.py
import json
from strands import Agent
from strands.models import BedrockModel

model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0")
agent = Agent(
    model=model,
    system_prompt="Analyze documents. Return JSON with summary, sentiment, entities, confidence.",
    tools=[],
)

def handler(event, context):
    result = agent(f"Analyze: {event['document_text']}")
    
    # CRITICAL: marshal to JSON-serializable, enforce 256KB limit
    response = {
        "agent_output": str(result)[:200000],
        "task_type": event.get("task_type", "analyze"),
        "success": True,
    }
    return response
```

AWS provides an official Lambda Layer for Strands (`arn:aws:lambda:{region}:856699698935:layer:strands-agents-py312-arm64:{version}`) that eliminates dependency packaging headaches.

### Choice states provide deterministic routing on agent outputs

Step Functions Choice states evaluate JSON values — strings, numbers, booleans — with full logical operators (And, Or, Not). Agent outputs must be parsed into structured JSON before Choice can route:

```python
from aws_cdk import (
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    Duration,
)

# Invoke agent
invoke_agent = tasks.LambdaInvoke(
    self, "InvokeAnalysisAgent",
    lambda_function=agent_fn,
    payload=sfn.TaskInput.from_object({
        "document_text": sfn.JsonPath.string_at("$.document.content"),
    }),
    result_selector={
        "sentiment.$": "$.Payload.agent_output.sentiment",
        "confidence.$": "$.Payload.agent_output.confidence",
        "success.$": "$.Payload.success",
    },
    result_path="$.agentResult",
)

# Deterministic routing
route = sfn.Choice(self, "RouteByAnalysis")
is_negative = sfn.Condition.string_equals("$.agentResult.sentiment", "negative")
is_high_confidence = sfn.Condition.and_(
    sfn.Condition.number_greater_than_equals("$.agentResult.confidence", 0.9),
    sfn.Condition.boolean_equals("$.agentResult.success", True),
)

route.when(is_negative, escalate_to_human)
route.when(is_high_confidence, auto_approve)
route.otherwise(manual_review)
```

### Error handling uses declarative Retry and Catch blocks

Retry supports **exponential backoff with full jitter** (the `JitterStrategy.FULL` option), essential for Bedrock throttling. Custom error names from Lambda enable granular catch handling:

```python
invoke_agent.add_retry(
    errors=["Lambda.ServiceException", "Lambda.TooManyRequestsException",
            "Bedrock.ThrottlingException"],
    interval=Duration.seconds(2),
    max_attempts=5,
    backoff_rate=2.0,
    jitter_strategy=sfn.JitterType.FULL,
)
invoke_agent.add_catch(
    handler=fallback_state,
    errors=["States.ALL"],
    result_path="$.error",
)
```

### Standard Workflows are correct for agentic workloads

Express Workflows cap at **5 minutes** and lack exactly-once semantics, `.waitForTaskToken` (human-in-the-loop), and full execution history. Agent reasoning commonly takes 2-15 minutes. **Standard Workflows** provide up to 1-year execution, exactly-once semantics, and full visual debugging. The hybrid pattern — Standard parent with Express children inside Distributed Map — gives cost-effective parallelism for fan-out agent tasks while maintaining the outer deterministic guarantees.

### State flow uses a five-stage pipeline

`InputPath` → `Parameters` → [Task] → `ResultSelector` → `ResultPath` → `OutputPath`. The critical technique: `ResultPath: "$.agentResult"` **appends** the task output without losing the original input. `ResultSelector` extracts only relevant fields from Lambda's response envelope. `$$.Execution.Input` references the original execution input from any state. For payloads exceeding 256KB, implement the **claim-check pattern** — store in S3, pass only the key.

---

## The full architecture: Russian Doll integration

The three layers nest cleanly. Step Functions defines the deterministic workflow — validate input, invoke agent, check result, branch or retry, store output. Each agent invocation is a Task state targeting either a Lambda function (for quick agents) or an AgentCore Runtime endpoint (for production). Inside that compute boundary, a Strands agent runs its model-driven loop: reasoning about which tools to call, executing them, and synthesizing results. AgentCore provides the runtime isolation, memory persistence, identity management, and observability.

### End-to-end CDK stack

```python
from aws_cdk import (
    Stack, Duration,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct

class AgentPocStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Strands agent Lambda
        agent_fn = lambda_.Function(
            self, "StrandsAgent",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="agent_handler.handler",
            code=lambda_.Code.from_asset("lambda/"),
            timeout=Duration.minutes(15),
            memory_size=1024,
            architecture=lambda_.Architecture.ARM_64,
            layers=[lambda_.LayerVersion.from_layer_version_arn(
                self, "StrandsLayer",
                f"arn:aws:lambda:{self.region}:856699698935:layer:strands-agents-py312-arm64:1"
            )],
        )
        agent_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=["*"],
        ))

        # Lightweight validation Lambda
        validate_fn = lambda_.Function(
            self, "ValidateInput",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="validate.handler",
            code=lambda_.Code.from_asset("lambda/"),
            timeout=Duration.seconds(30),
        )

        # Step 1: Validate
        validate = tasks.LambdaInvoke(
            self, "Validate", lambda_function=validate_fn,
            output_path="$.Payload",
        )

        # Step 2: Agent analysis
        analyze = tasks.LambdaInvoke(
            self, "AnalyzeWithAgent", lambda_function=agent_fn,
            payload=sfn.TaskInput.from_object({
                "document_text": sfn.JsonPath.string_at("$.content"),
                "task_type": "full_analysis",
            }),
            result_selector={
                "sentiment.$": "$.Payload.sentiment",
                "confidence.$": "$.Payload.confidence",
                "summary.$": "$.Payload.summary",
            },
            result_path="$.analysis",
        )
        analyze.add_retry(
            errors=["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
            interval=Duration.seconds(3), max_attempts=4, backoff_rate=2.0,
        )
        analyze.add_catch(
            handler=sfn.Fail(self, "AnalysisFailed", cause="Agent error"),
            errors=["States.ALL"], result_path="$.error",
        )

        # Step 3: Deterministic routing
        route = sfn.Choice(self, "RouteOnSentiment")
        escalate = tasks.LambdaInvoke(self, "Escalate",
            lambda_function=agent_fn,
            payload=sfn.TaskInput.from_object({
                "task_type": "escalation_report",
                "context": sfn.JsonPath.string_at("$.analysis"),
            }),
            result_path="$.escalation",
        )
        approve = sfn.Succeed(self, "AutoApproved")
        review = tasks.LambdaInvoke(self, "ManualReview",
            lambda_function=agent_fn,
            payload=sfn.TaskInput.from_object({"task_type": "review_prep"}),
            result_path="$.review",
        )
        done = sfn.Succeed(self, "Complete")

        # Wire the chain
        definition = (
            validate
            .next(analyze)
            .next(route
                .when(sfn.Condition.string_equals("$.analysis.sentiment", "negative"),
                      escalate.next(done))
                .when(sfn.Condition.number_greater_than_equals("$.analysis.confidence", 0.9),
                      approve)
                .otherwise(review.next(done))
            )
        )

        log_group = logs.LogGroup(self, "SfnLogs",
            retention=logs.RetentionDays.ONE_MONTH)

        sfn.StateMachine(
            self, "AgentOrchestrator",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            state_machine_type=sfn.StateMachineType.STANDARD,
            timeout=Duration.hours(1),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True,
            ),
        )
```

### State flows through clear marshaling boundaries

```
Step Functions (JSON, ≤256KB)
  → LambdaInvoke / HTTP Task
    → Lambda handler (Python dict from event)
      → Strands Agent (internal message list + tool calls)
        → Tools (Python return values)
        → Model reasoning loop
      ← AgentResult (text + metadata)
    ← JSON response (serialized, truncated to ≤256KB)
  ← ResultSelector extracts relevant fields
→ Next state receives merged JSON
```

When using AgentCore Runtime instead of Lambda, Step Functions invokes via HTTP API (`boto3.client('bedrock-agentcore').invoke_agent_runtime(...)`) with **100MB payload** support and streaming. Map the Step Functions execution ID to the AgentCore `session_id` for cross-step session persistence and traceability.

### Choosing between Lambda, Fargate, and AgentCore Runtime

| Factor | Lambda | Fargate | AgentCore Runtime |
|--------|--------|---------|-------------------|
| Max execution | 15 min | Unlimited | 8 hours |
| Payload | 6MB sync | Unlimited | 100MB |
| Cold start | Seconds (with layers) | Minutes | ~23s first, ~9s warm |
| Streaming | No (for Strands) | Yes | Yes |
| Session isolation | None (stateless) | Manual | Hardware (microVM) |
| Memory mgmt | External (DynamoDB/S3) | External | Built-in AgentCore Memory |
| Pricing | Per-invocation + duration | Per-task-hour | Per-second active compute |

**For the POC**: start with Lambda for speed of iteration. **For production**: graduate to AgentCore Runtime for session isolation, 8-hour execution, managed memory, and consumption-based pricing with free I/O wait.

---

## Gotchas, limitations, and gaps that will bite you

**The 256KB payload wall is the #1 integration pain point.** Agent responses with detailed reasoning chains, tool outputs, or document excerpts routinely exceed this. Implement the claim-check pattern from day one — store all agent outputs in S3, pass only S3 keys through Step Functions. The `middy-store` library automates this. AWS's direct Bedrock integration in Step Functions supports **25MB via S3 Input/Output fields**, but that only works for single-turn model calls, not Strands agent invocations.

**Lambda's 15-minute timeout constrains complex reasoning.** Multi-tool Strands agents with extended thinking commonly run 5-15 minutes. If your agent hits a slow Bedrock response or chains many tool calls, you'll timeout. Mitigation: decompose complex reasoning into multiple Step Functions steps each invoking a simpler, focused agent. Or use AgentCore Runtime (8 hours) and invoke via HTTP.

**MCP connection lifecycle in Lambda is a footgun for multi-tenancy.** MCP connections are stateful. If reused across warm Lambda invocations, they can leak state between users. Always use context managers (`with mcp_client:`) scoped to each invocation. The Strands deploy-to-Lambda docs explicitly call this out.

**Agent non-determinism means retries invoke different reasoning paths.** The same prompt can produce different tool-call sequences. Step Functions retries may trigger entirely different agent behavior. **All tool side-effects must be idempotent.** Design tools with idempotency keys or use conditional writes.

**Step Functions' 25,000 execution history event limit** compounds with agent retry loops. Each state transition generates 2-5 events. Workflows with iterative agent loops can exhaust this limit. Implement event counters and "continue as new execution" patterns for long-running orchestrations.

**Observability correlation across layers requires manual effort.** Step Functions, Lambda, Strands (OTEL), and AgentCore each generate traces. Correlating them end-to-end requires explicit X-Ray/OTEL trace ID propagation — this is not automatic. Instrument this from day one.

**No streaming from Lambda in Step Functions.** Step Functions Lambda invocations are synchronous request-response only. For streaming agent responses to a UI, you need a separate path: API Gateway + Lambda response streaming, WebSockets, or AgentCore's native streaming endpoint.

**AgentCore is AWS-only infrastructure.** While Strands itself is cloud-agnostic (supports OpenAI, Anthropic direct, LiteLLM, Ollama), AgentCore Runtime locks you to AWS. If multi-cloud is a hard requirement, use Strands on ECS/Fargate instead and self-manage the runtime concerns.

**Strands has no native checkpoint/resume for long-running agents** (GitHub issue #1369). If an agent crashes mid-reasoning, there is no built-in mechanism to resume from the last checkpoint. For mission-critical workflows, the Step Functions outer layer provides this durability — if a Lambda/AgentCore task fails, Step Functions retries the entire agent step.

**Cost is dominated by model inference.** For a 10K requests/month workload, expect roughly $5-50 for Step Functions transitions, $35 for Lambda compute, and **$500+ for Bedrock tokens**. Invest in prompt engineering, Strands' prompt/tool caching (`cache_prompt="default"`, `cache_tools="default"`), and result summarization before optimizing infrastructure costs.

---

## Conclusion: a viable stack with clear boundaries

This stack works because each layer does one thing well. Step Functions provides deterministic control flow, visual debugging, and durable execution that agent frameworks cannot match. Strands provides model-driven reasoning with first-class tool use, MCP integration, and multi-agent patterns that Step Functions cannot express. AgentCore provides managed infrastructure — session isolation, memory, identity, observability — that eliminates months of platform engineering.

The architectural insight worth internalizing: **push determinism outward and autonomy inward**. Any decision that can be expressed as a simple condition on structured data belongs in Step Functions Choice states. Any decision requiring judgment, synthesis, or multi-step reasoning belongs inside the Strands agent. The boundary between these layers is the most important design decision in your POC.

For your enterprise evaluation, three things to validate early: whether the **256KB payload limit** requires the claim-check pattern for your data volumes (it almost certainly does), whether your agents complete within **Lambda's 15-minute window** or need AgentCore/Fargate, and whether AgentCore's **~23-second cold start** is acceptable for your latency requirements. Everything else is configuration.