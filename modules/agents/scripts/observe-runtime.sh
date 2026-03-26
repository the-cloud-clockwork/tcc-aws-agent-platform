#!/usr/bin/env bash
set -euo pipefail

# observe-runtime.sh — Platform-generic observability for AgentCore Runtimes
#
# Domain-agnostic: works for any domain repo. Discovers runtimes from Terraform
# state and fetches logs, traces, metrics from CloudWatch/X-Ray/OTEL.
#
# Usage:
#   observe-runtime.sh                           # summary table of all runtimes
#   observe-runtime.sh watchlist-screener        # full details for one runtime
#   observe-runtime.sh watchlist-screener --logs # last 50 log lines
#   observe-runtime.sh watchlist-screener --traces # X-Ray traces (last 1h)
#   observe-runtime.sh watchlist-screener --metrics # CloudWatch OTEL metrics
#   observe-runtime.sh watchlist-screener --all  # everything
#   observe-runtime.sh --agents                  # summary of agent runtimes only
#   observe-runtime.sh --mcps                    # summary of MCP runtimes only
#
# Environment:
#   AWS_DEFAULT_REGION   — AWS region (default: eu-west-1)
#   OTEL_LOG_PREFIX      — CloudWatch log group prefix (default: /aws/bedrock-agentcore/runtimes/)
#   OTEL_METRIC_NS       — CloudWatch metric namespace (default: bedrock-agentcore)
#   XRAY_GROUP           — X-Ray trace group (default: auto-detected)

REGION="${AWS_DEFAULT_REGION:-eu-west-1}"
OTEL_LOG_PREFIX="${OTEL_LOG_PREFIX:-/aws/bedrock-agentcore/runtimes/}"
OTEL_METRIC_NS="${OTEL_METRIC_NS:-bedrock-agentcore}"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

# ── Parse args ───────────────────────────────────────────────────────────────
TARGET=""
DO_LOGS=false
DO_TRACES=false
DO_METRICS=false
DO_ALL=false
FILTER_AGENTS=false
FILTER_MCPS=false
LOG_LINES=50
SINCE="1h"

while [[ $# -gt 0 ]]; do
  case $1 in
    --logs)     DO_LOGS=true; shift ;;
    --traces)   DO_TRACES=true; shift ;;
    --metrics)  DO_METRICS=true; shift ;;
    --all)      DO_ALL=true; shift ;;
    --agents)   FILTER_AGENTS=true; shift ;;
    --mcps)     FILTER_MCPS=true; shift ;;
    --lines)    LOG_LINES="$2"; shift 2 ;;
    --since)    SINCE="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: $0 [runtime-name] [--logs] [--traces] [--metrics] [--all] [--agents] [--mcps] [--lines N] [--since DURATION]"
      exit 0 ;;
    -*)         echo "Unknown flag: $1"; exit 1 ;;
    *)          TARGET="$1"; shift ;;
  esac
done

if $DO_ALL; then
  DO_LOGS=true
  DO_TRACES=true
  DO_METRICS=true
fi

# ── Discover runtimes ────────────────────────────────────────────────────────

list_runtimes() {
  aws bedrock-agentcore-control list-agent-runtimes \
    --max-results 50 --region "$REGION" --output json 2>/dev/null | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
runtimes = data.get('agentRuntimes', [])
for r in sorted(runtimes, key=lambda x: x.get('agentRuntimeName','')):
    name = r.get('agentRuntimeName','')
    rid = r.get('agentRuntimeId','')
    status = r.get('status','?')
    version = r.get('agentRuntimeVersion','?')
    updated = r.get('lastUpdatedAt','')[:19]
    print(f'{name}\t{rid}\t{status}\tv{version}\t{updated}')
"
}

# ── Summary table ────────────────────────────────────────────────────────────

show_summary() {
  echo -e "${BOLD}AgentCore Runtimes${NC}"
  echo

  local runtimes
  runtimes=$(list_runtimes)

  # Filter if requested
  if $FILTER_AGENTS; then
    runtimes=$(echo "$runtimes" | grep -v "_mcp" || true)
  elif $FILTER_MCPS; then
    runtimes=$(echo "$runtimes" | grep "_mcp" || true)
  fi

  local total=0 ready=0 failed=0

  printf "${BOLD}%-40s %-8s %-6s %-20s %s${NC}\n" "Runtime" "Status" "Ver" "Updated" "Logs (bytes)"
  printf '%.0s─' {1..95}; echo

  while IFS=$'\t' read -r name rid status version updated; do
    [[ -z "$name" ]] && continue
    total=$((total + 1))

    # Get log group size
    local log_bytes
    log_bytes=$(aws logs describe-log-groups \
      --log-group-name-prefix "${OTEL_LOG_PREFIX}${name##*_}" \
      --query 'logGroups[0].storedBytes' --output text --region "$REGION" 2>/dev/null || echo "0")
    [[ "$log_bytes" == "None" ]] && log_bytes=0

    # Color status
    local status_color="$RED"
    if [[ "$status" == "READY" ]]; then
      status_color="$GREEN"
      ready=$((ready + 1))
    else
      failed=$((failed + 1))
    fi

    # Derive short name (strip prefix)
    local short_name="${name}"

    printf "%-40s ${status_color}%-8s${NC} %-6s %-20s %s\n" \
      "$short_name" "$status" "$version" "$updated" "$log_bytes"
  done <<< "$runtimes"

  echo
  echo -e "Total: ${BOLD}$total${NC} | ${GREEN}Ready: $ready${NC} | ${RED}Failed: $failed${NC}"
}

# ── Runtime detail ───────────────────────────────────────────────────────────

show_runtime_detail() {
  local name="$1"
  echo -e "${BOLD}Runtime: $name${NC}"
  echo

  # Find runtime by partial name match
  local runtime_info
  runtime_info=$(list_runtimes | grep "$name" | head -1)

  if [[ -z "$runtime_info" ]]; then
    echo -e "${RED}Runtime not found: $name${NC}"
    echo "Available runtimes:"
    list_runtimes | cut -f1
    return 1
  fi

  IFS=$'\t' read -r full_name rid status version updated <<< "$runtime_info"

  local status_color="$GREEN"
  [[ "$status" != "READY" ]] && status_color="$RED"

  echo -e "  Name:    ${BOLD}$full_name${NC}"
  echo -e "  ID:      $rid"
  echo -e "  Status:  ${status_color}${status}${NC}"
  echo -e "  Version: $version"
  echo -e "  Updated: $updated"

  # Detect type
  local runtime_type="agent"
  [[ "$full_name" == *"_mcp"* ]] && runtime_type="mcp"
  echo -e "  Type:    $runtime_type"
  echo

  # Log group info
  local log_group="${OTEL_LOG_PREFIX}${name}"
  local log_info
  log_info=$(aws logs describe-log-groups \
    --log-group-name-prefix "$log_group" \
    --query 'logGroups[0].{bytes:storedBytes,retention:retentionInDays,streams:metricFilterCount}' \
    --output json --region "$REGION" 2>/dev/null || echo "{}")

  echo -e "${CYAN}CloudWatch Log Group${NC}: $log_group"
  echo "  $(echo "$log_info" | python3 -c "
import json, sys
d = json.load(sys.stdin)
b = d.get('bytes', 0) or 0
r = d.get('retention', '?')
if b > 1048576: size = f'{b/1048576:.1f} MB'
elif b > 1024: size = f'{b/1024:.1f} KB'
else: size = f'{b} B'
print(f'Size: {size} | Retention: {r} days')
" 2>/dev/null || echo "No log group")"
  echo
}

# ── Logs ─────────────────────────────────────────────────────────────────────

show_logs() {
  local name="$1"
  local log_group="${OTEL_LOG_PREFIX}${name}"

  echo -e "${CYAN}═══ Logs (last $LOG_LINES lines, since $SINCE) ═══${NC}"
  echo

  aws logs tail "$log_group" \
    --since "$SINCE" \
    --format short \
    --region "$REGION" 2>&1 | tail -"$LOG_LINES" | while read -r line; do
    # Color errors red, warnings yellow
    if echo "$line" | grep -qi "error\|exception\|traceback\|failed"; then
      echo -e "${RED}$line${NC}"
    elif echo "$line" | grep -qi "warn"; then
      echo -e "${YELLOW}$line${NC}"
    elif echo "$line" | grep -qi "otel\|trace\|span\|export"; then
      echo -e "${BLUE}$line${NC}"
    else
      echo "$line"
    fi
  done
  echo
}

# ── X-Ray Traces ─────────────────────────────────────────────────────────────

show_traces() {
  local name="$1"

  echo -e "${CYAN}═══ X-Ray Traces (last $SINCE) ═══${NC}"
  echo

  local start_time end_time
  # Convert SINCE to epoch
  if [[ "$SINCE" == *h ]]; then
    start_time=$(date -d "${SINCE%h} hours ago" +%s 2>/dev/null || date -v-"${SINCE%h}"H +%s 2>/dev/null)
  elif [[ "$SINCE" == *m ]]; then
    start_time=$(date -d "${SINCE%m} minutes ago" +%s 2>/dev/null || date -v-"${SINCE%m}"M +%s 2>/dev/null)
  else
    start_time=$(date -d "1 hour ago" +%s 2>/dev/null || date -v-1H +%s 2>/dev/null)
  fi
  end_time=$(date +%s)

  local filter="service(\"$name\")"

  aws xray get-trace-summaries \
    --start-time "$start_time" --end-time "$end_time" \
    --filter-expression "$filter" \
    --region "$REGION" --output json 2>/dev/null | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
traces = data.get('TraceSummaries', [])
if not traces:
    print('  No traces found for this runtime in the time window.')
    print(f'  Filter: {\"$filter\"}')
    sys.exit(0)

print(f'  Found {len(traces)} trace(s)')
print()
print(f'{\"Trace ID\":<40} {\"Duration\":<12} {\"Status\":<10} {\"Fault\":<8} {\"Error\":<8}')
print('-'*78)
for t in traces[:20]:
    tid = t.get('Id','?')
    dur = f'{t.get(\"Duration\",0):.3f}s'
    code = t.get('Http',{}).get('HttpStatus', '-')
    fault = 'YES' if t.get('HasFault') else '-'
    error = 'YES' if t.get('HasError') else '-'
    print(f'{tid:<40} {dur:<12} {code:<10} {fault:<8} {error:<8}')
" 2>&1
  echo
}

# ── OTEL Metrics ─────────────────────────────────────────────────────────────

show_metrics() {
  local name="$1"

  echo -e "${CYAN}═══ OTEL Metrics (namespace: $OTEL_METRIC_NS) ═══${NC}"
  echo

  # List metrics for this service
  aws cloudwatch list-metrics \
    --namespace "$OTEL_METRIC_NS" \
    --dimensions "Name=service.name,Value=$name" \
    --region "$REGION" --output json 2>/dev/null | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
metrics = data.get('Metrics', [])
if not metrics:
    print(f'  No metrics found in namespace \"$OTEL_METRIC_NS\" for service \"$name\"')
    print(f'  (Metrics appear after the runtime has handled requests with OTEL instrumentation)')
    sys.exit(0)

print(f'  Found {len(metrics)} metric(s)')
print()
seen = set()
for m in metrics:
    mn = m.get('MetricName','?')
    if mn not in seen:
        seen.add(mn)
        dims = ', '.join(f'{d[\"Name\"]}={d[\"Value\"]}' for d in m.get('Dimensions',[]))
        print(f'  {mn:<50} [{dims}]')
" 2>&1

  # Also check the domain namespace
  echo
  echo -e "${CYAN}Custom namespace: QITP${NC}"
  aws cloudwatch list-metrics \
    --namespace "QITP" \
    --dimensions "Name=service.name,Value=$name" \
    --region "$REGION" --output json 2>/dev/null | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
metrics = data.get('Metrics', [])
if not metrics:
    print('  No custom metrics yet')
else:
    for m in metrics:
        print(f'  {m.get(\"MetricName\",\"?\")}')
" 2>&1
  echo
}

# ── Main ─────────────────────────────────────────────────────────────────────

if [[ -z "$TARGET" ]]; then
  # No target — show summary table
  show_summary
else
  # Show runtime detail
  show_runtime_detail "$TARGET"

  # Default: if no specific flags, show logs
  if ! $DO_LOGS && ! $DO_TRACES && ! $DO_METRICS; then
    DO_LOGS=true
  fi

  $DO_LOGS && show_logs "$TARGET"
  $DO_TRACES && show_traces "$TARGET"
  $DO_METRICS && show_metrics "$TARGET"
fi
