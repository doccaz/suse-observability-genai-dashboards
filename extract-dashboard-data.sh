#!/usr/bin/env bash
# Pull real sample data for the two dashboards in this repo (GenAI Model
# Cost & Efficiency / GPU Saturation vs LLM Request Load) straight from
# VictoriaMetrics, and flatten it into CSVs under sample-data/real/.
#
# Usage:
#   ./extract-dashboard-data.sh [range_seconds] [step_seconds] [out_dir]
#
# Defaults: range=604800 (7d), step=300 (5m), out_dir=./sample-data/real/<timestamp>
#
# Requires: kubectl configured with a context pointed at your SUSE
# Observability cluster (KUBECONFIG env var, or `kubectl config use-context`),
# and python3. Uses `kubectl port-forward` to reach VictoriaMetrics -- no
# cluster-specific SSH/bastion setup needed.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

RANGE="${1:-604800}"
STEP="${2:-300}"
OUT_DIR="${3:-sample-data/real/$(date +%Y%m%d-%H%M%S)}"

NAMESPACE="${VM_NAMESPACE:-suse-observability}"
SERVICE="${VM_SERVICE:-suse-observability-victoria-metrics}"
LOCAL_PORT="${VM_LOCAL_PORT:-18428}"

METRICS=(
  gen_ai_client_operation_cost_USD_sum
  gen_ai_client_operation_cost_USD_count
  gen_ai_client_token_usage_sum
  gen_ai_client_operation_duration_seconds_sum
  gen_ai_client_operation_duration_seconds_count
  DCGM_FI_DEV_GPU_UTIL
  DCGM_FI_PROF_PIPE_TENSOR_ACTIVE
  DCGM_FI_DEV_FB_USED
  DCGM_FI_DEV_POWER_USAGE
  DCGM_FI_DEV_GPU_TEMP
)

echo "==> Port-forwarding $SERVICE.$NAMESPACE:8428 -> localhost:$LOCAL_PORT"
kubectl -n "$NAMESPACE" port-forward "svc/$SERVICE" "$LOCAL_PORT:8428" >/tmp/pf-$$.log 2>&1 &
PF_PID=$!
trap 'kill $PF_PID 2>/dev/null || true' EXIT

for i in $(seq 1 15); do
  if curl -s -o /dev/null "http://localhost:$LOCAL_PORT/health"; then
    break
  fi
  sleep 1
done
if ! curl -s -o /dev/null "http://localhost:$LOCAL_PORT/health"; then
  echo "Could not reach VictoriaMetrics via port-forward. Check VM_NAMESPACE/VM_SERVICE env vars and cluster access." >&2
  cat /tmp/pf-$$.log >&2
  exit 1
fi

END=$(date +%s)
START=$((END - RANGE))

echo "==> Querying ${#METRICS[@]} metrics, range=${RANGE}s step=${STEP}s"
mkdir -p "$OUT_DIR/raw"
for q in "${METRICS[@]}"; do
  curl -s "http://localhost:$LOCAL_PORT/api/v1/query_range?query=${q}&start=${START}&end=${END}&step=${STEP}" \
    -o "$OUT_DIR/raw/${q}.json"
done

kill $PF_PID 2>/dev/null || true
trap - EXIT

echo "==> Flattening to CSV"
python3 sample-data/_convert_to_csv.py "$OUT_DIR/raw" "$OUT_DIR"

echo "==> Done. CSVs in $OUT_DIR/"
