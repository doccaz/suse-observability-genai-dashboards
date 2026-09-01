#!/usr/bin/env python3
"""Load the flattened sample-data CSVs (real/ or synthetic/) back into a
VictoriaMetrics instance as proper time series, via the native
/api/v1/import JSON-lines endpoint -- so the two dashboards in this repo
(GenAI Model Cost & Efficiency / GPU Saturation vs LLM Request Load),
which are plain PromQL against these exact metric/label names, render
against simulated data in any VictoriaMetrics you point this at (e.g. a
local `docker run -p 8428:8428 victoriametrics/victoria-metrics` sandbox).

Usage:
  python3 insert_to_victoriametrics.py <csv_dir> [vm_url]

  csv_dir   directory containing genai_cost.csv, genai_tokens.csv,
            genai_duration.csv, gpu_saturation.csv (i.e. real/ or synthetic/)
  vm_url    VictoriaMetrics base URL (default: http://localhost:8428)

Requires: python3 only (urllib, no extra deps).
"""
import csv
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

csv_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "sample-data/real")
vm_url = (sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8428").rstrip("/")

# series[(metric_name, frozenset(labels.items()))] = {ts_ms: value}
series = defaultdict(dict)


def add_point(metric_name, labels, ts_seconds, value):
    if value in (None, ""):
        return
    key = (metric_name, tuple(sorted(labels.items())))
    series[key][int(ts_seconds) * 1000] = float(value)


def read_csv(name):
    path = csv_dir / name
    if not path.exists():
        print(f"skip (missing): {path}")
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


# --- GenAI cost ---
for row in read_csv("genai_cost.csv"):
    labels = {
        "gen_ai_request_model": row["model"],
        "gen_ai_response_model": row["model"],
        "gen_ai_provider_name": row["provider"],
        "gen_ai_operation_name": row["operation"],
        "k8s_namespace_name": row["namespace"],
        "k8s_cluster_name": "downstream",
    }
    add_point("gen_ai_client_operation_cost_USD_sum", labels, row["timestamp"], row["cost_usd_cumulative"])

# --- GenAI tokens ---
for row in read_csv("genai_tokens.csv"):
    labels = {
        "gen_ai_request_model": row["model"],
        "gen_ai_response_model": row["model"],
        "gen_ai_provider_name": row["provider"],
        "gen_ai_token_type": row["token_type"],
        "k8s_namespace_name": row["namespace"],
        "k8s_cluster_name": "downstream",
    }
    add_point("gen_ai_client_token_usage_sum", labels, row["timestamp"], row["tokens_cumulative"])

# --- GenAI duration (sum + count) ---
for row in read_csv("genai_duration.csv"):
    labels = {
        "gen_ai_request_model": row["model"],
        "gen_ai_response_model": row["model"],
        "gen_ai_provider_name": row["provider"],
        "k8s_cluster_name": "downstream",
    }
    add_point("gen_ai_client_operation_duration_seconds_sum", labels, row["timestamp"],
              row["duration_seconds_sum_cumulative"])
    add_point("gen_ai_client_operation_duration_seconds_count", labels, row["timestamp"],
              row["request_count_cumulative"])

# --- GPU saturation ---
METRIC_NAME_MAP = {
    "gpu_util_pct": "DCGM_FI_DEV_GPU_UTIL",
    "tensor_active_fraction": "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE",
    "fb_used_mib": "DCGM_FI_DEV_FB_USED",
    "power_usage_w": "DCGM_FI_DEV_POWER_USAGE",
    "gpu_temp_c": "DCGM_FI_DEV_GPU_TEMP",
}
for row in read_csv("gpu_saturation.csv"):
    metric_name = METRIC_NAME_MAP.get(row["metric"])
    if not metric_name:
        continue
    labels = {
        "k8s_node_name": row["node"],
        "Hostname": row["node"],
        "gpu": row["gpu"],
        "modelName": row["model_name"],
        "namespace": row["namespace"],
        "k8s_cluster_name": "downstream",
    }
    add_point(metric_name, labels, row["timestamp"], row["value"])

# --- Build VictoriaMetrics import JSON lines ---
lines = []
for (metric_name, label_items), points in series.items():
    ts_sorted = sorted(points.items())
    metric = {"__name__": metric_name, **dict(label_items)}
    lines.append(json.dumps({
        "metric": metric,
        "values": [v for _, v in ts_sorted],
        "timestamps": [t for t, _ in ts_sorted],
    }))

print(f"Built {len(lines)} series ({sum(len(p) for p in series.values())} total samples)")

payload = ("\n".join(lines) + "\n").encode()
req = urllib.request.Request(
    f"{vm_url}/api/v1/import",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"Import OK: HTTP {resp.status}")
except urllib.error.HTTPError as e:
    print(f"Import FAILED: HTTP {e.code} {e.reason}\n{e.read().decode(errors='replace')}", file=sys.stderr)
    sys.exit(1)
except urllib.error.URLError as e:
    print(f"Could not reach {vm_url}: {e.reason}", file=sys.stderr)
    print("Start a local sandbox with e.g.:\n  docker run -d -p 8428:8428 victoriametrics/victoria-metrics", file=sys.stderr)
    sys.exit(1)

print(f"Done. Query it at {vm_url}/api/v1/query?query=DCGM_FI_DEV_GPU_UTIL (or point the dashboards' PrometheusTimeSeriesQuery datasource at {vm_url}).")
