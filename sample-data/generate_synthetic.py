#!/usr/bin/env python3
"""Generate synthetic sample data matching the schema of the two SUSE
Observability custom dashboards (GenAI Model Cost & Efficiency / GPU
Saturation vs LLM Request Load), for use in a simulated environment with
no dependency on the live cluster.

Metric/label names match what these dashboards actually query in a live
SUSE AI environment -- see sample-data/real/ for actual extracted values
and ranges this was calibrated against.

Usage: python3 generate_synthetic.py [out_dir] [hours] [step_seconds]
"""
import csv
import random
import sys
from pathlib import Path

out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "sample-data/synthetic")
hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
step = int(sys.argv[3]) if len(sys.argv) > 3 else 60
out_dir.mkdir(parents=True, exist_ok=True)

random.seed(42)

START_TS = 1788000000  # arbitrary fixed epoch so runs are reproducible
n_points = (hours * 3600) // step
timestamps = [START_TS + i * step for i in range(n_points)]

MODELS = [
    ("glm-4.7-flash:q4_K_M", "ollama", 0.0000012),   # $ per token, roughly
    ("meu-assistente", "ollama", 0.0000009),
    ("tinyrick/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-GGUF:Q4_K_P", "ollama", 0.0000021),
]
NAMESPACE = "suse-ai"
NODE = "downstream-gpu-worker-0"
GPU_MODEL = "NVIDIA L4"


def write_csv(rows, fields, path):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")


# --- GenAI cost: cumulative counter per model, occasional step increases ---
cost_rows, token_rows, duration_rows = [], [], []
for model, provider, cost_per_token in MODELS:
    cost = 0.0
    tok_in = 0
    tok_out = 0
    dur_sum = 0.0
    dur_count = 0
    for ts in timestamps:
        # sparse, event-driven traffic: ~3% chance of a chat request per step
        if random.random() < 0.03:
            in_tokens = random.randint(20, 400)
            out_tokens = random.randint(20, 600)
            request_cost = (in_tokens + out_tokens) * cost_per_token
            cost += request_cost
            tok_in += in_tokens
            tok_out += out_tokens
            dur_sum += random.uniform(0.4, 6.0)
            dur_count += 1

        cost_rows.append({
            "timestamp": ts, "model": model, "provider": provider,
            "operation": "chat", "namespace": NAMESPACE,
            "cost_usd_cumulative": f"{cost:.7f}",
        })
        token_rows.append({
            "timestamp": ts, "model": model, "provider": provider,
            "token_type": "input", "namespace": NAMESPACE,
            "tokens_cumulative": tok_in,
        })
        token_rows.append({
            "timestamp": ts, "model": model, "provider": provider,
            "token_type": "output", "namespace": NAMESPACE,
            "tokens_cumulative": tok_out,
        })
        duration_rows.append({
            "timestamp": ts, "model": model, "provider": provider,
            "duration_seconds_sum_cumulative": f"{dur_sum:.7f}",
            "request_count_cumulative": dur_count,
        })

write_csv(cost_rows, ["timestamp", "model", "provider", "operation", "namespace", "cost_usd_cumulative"],
          out_dir / "genai_cost.csv")
write_csv(token_rows, ["timestamp", "model", "provider", "token_type", "namespace", "tokens_cumulative"],
          out_dir / "genai_tokens.csv")
write_csv(duration_rows, ["timestamp", "model", "provider", "duration_seconds_sum_cumulative", "request_count_cumulative"],
          out_dir / "genai_duration.csv")

# --- GPU saturation: correlated with a synthetic request-load wave ---
gpu_rows = []
for i, ts in enumerate(timestamps):
    # smooth load wave in [0,1] plus noise, simulating busier daytime hours
    phase = (i % (3600 // step * 6)) / (3600 // step * 6)
    load = max(0.0, 0.5 + 0.45 * random.uniform(-1, 1) * (0.3 + phase) - 0.2)
    load = min(1.0, load)

    util = round(load * 100 + random.uniform(-5, 5))
    util = max(0, min(100, util))
    tensor_active = round(max(0.0, min(1.0, load * 0.8 + random.uniform(-0.05, 0.05))), 3)
    fb_used = round(2000 + load * 18000 + random.uniform(-200, 200))  # MiB, L4 has 24GB
    power = round(30 + load * 60 + random.uniform(-3, 3), 1)  # W, L4 TDP ~72W
    temp = round(35 + load * 30 + random.uniform(-2, 2), 1)  # C

    for metric, value in [
        ("gpu_util_pct", util),
        ("tensor_active_fraction", tensor_active),
        ("fb_used_mib", fb_used),
        ("power_usage_w", power),
        ("gpu_temp_c", temp),
    ]:
        gpu_rows.append({
            "timestamp": ts, "metric": metric, "node": NODE, "gpu": "0",
            "model_name": GPU_MODEL, "namespace": NAMESPACE, "value": value,
        })

write_csv(gpu_rows, ["timestamp", "metric", "node", "gpu", "model_name", "namespace", "value"],
          out_dir / "gpu_saturation.csv")

print("done")
