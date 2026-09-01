#!/usr/bin/env python3
"""Flatten raw VictoriaMetrics query_range JSON exports into clean CSVs
for the two custom SUSE Observability dashboards (GenAI Model Cost &
Efficiency / GPU Saturation vs LLM Request Load).

Usage: python3 _convert_to_csv.py <raw_json_dir> <out_dir>
"""
import json
import csv
import sys
from pathlib import Path

raw_dir = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)


def load(name):
    f = raw_dir / name
    if not f.exists():
        return []
    return json.load(open(f)).get("data", {}).get("result", [])


def write_csv(rows, fields, path):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")


# --- GenAI Model Cost & Efficiency ---
rows = []
for series in load("gen_ai_client_operation_cost_USD_sum_7d.json") or load("gen_ai_client_operation_cost_USD_sum.json"):
    m = series["metric"]
    for ts, val in series["values"]:
        rows.append({
            "timestamp": ts,
            "model": m.get("gen_ai_request_model"),
            "provider": m.get("gen_ai_provider_name"),
            "operation": m.get("gen_ai_operation_name"),
            "namespace": m.get("k8s_namespace_name"),
            "cost_usd_cumulative": val,
        })
write_csv(rows, ["timestamp", "model", "provider", "operation", "namespace", "cost_usd_cumulative"],
          out_dir / "genai_cost.csv")

rows = []
for series in load("gen_ai_client_token_usage_sum.json"):
    m = series["metric"]
    for ts, val in series["values"]:
        rows.append({
            "timestamp": ts,
            "model": m.get("gen_ai_request_model"),
            "provider": m.get("gen_ai_provider_name"),
            "token_type": m.get("gen_ai_token_type"),
            "namespace": m.get("k8s_namespace_name"),
            "tokens_cumulative": val,
        })
write_csv(rows, ["timestamp", "model", "provider", "token_type", "namespace", "tokens_cumulative"],
          out_dir / "genai_tokens.csv")

rows = []
sums = {}
counts = {}
for series in load("gen_ai_client_operation_duration_seconds_sum.json"):
    m = series["metric"]
    key = (m.get("gen_ai_request_model"), m.get("gen_ai_provider_name"))
    for ts, val in series["values"]:
        sums[(key, ts)] = val
for series in load("gen_ai_client_operation_duration_seconds_count.json"):
    m = series["metric"]
    key = (m.get("gen_ai_request_model"), m.get("gen_ai_provider_name"))
    for ts, val in series["values"]:
        counts[(key, ts)] = val
for (key, ts), val in sums.items():
    model, provider = key
    rows.append({
        "timestamp": ts,
        "model": model,
        "provider": provider,
        "duration_seconds_sum_cumulative": val,
        "request_count_cumulative": counts.get((key, ts), ""),
    })
write_csv(rows, ["timestamp", "model", "provider", "duration_seconds_sum_cumulative", "request_count_cumulative"],
          out_dir / "genai_duration.csv")

# --- GPU Saturation vs LLM Request Load ---
gpu_metrics = {
    "DCGM_FI_DEV_GPU_UTIL.json": "gpu_util_pct",
    "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE.json": "tensor_active_fraction",
    "DCGM_FI_DEV_FB_USED.json": "fb_used_mib",
    "DCGM_FI_DEV_POWER_USAGE.json": "power_usage_w",
    "DCGM_FI_DEV_GPU_TEMP.json": "gpu_temp_c",
}
rows = []
for fname, colname in gpu_metrics.items():
    for series in load(fname):
        m = series["metric"]
        for ts, val in series["values"]:
            rows.append({
                "timestamp": ts,
                "metric": colname,
                "node": m.get("k8s_node_name") or m.get("Hostname"),
                "gpu": m.get("gpu"),
                "model_name": m.get("modelName"),
                "namespace": m.get("namespace"),
                "value": val,
            })
write_csv(rows, ["timestamp", "metric", "node", "gpu", "model_name", "namespace", "value"],
          out_dir / "gpu_saturation.csv")

print("done")
