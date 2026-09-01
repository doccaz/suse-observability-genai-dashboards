# SUSE Observability GenAI Dashboards

Two ready-to-apply [SUSE Observability](https://www.suse.com/products/suse-observability/) dashboards for anyone running the SUSE AI stack (Ollama/vLLM + OpenWebUI, instrumented via the [SUSE AI Observability Extension](https://github.com/SUSE/suse-ai-observability-extension)):

- **[`genai-model-cost-efficiency.yaml`](dashboards/genai-model-cost-efficiency.yaml)** — cost, token usage, and latency broken down by model. Answers "which model is expensive," "which model is slow," and "which model is truncating responses."
- **[`gpu-saturation-vs-llm-load.yaml`](dashboards/gpu-saturation-vs-llm-load.yaml)** — NVIDIA DCGM GPU metrics correlated against GenAI request rate and latency. Answers "is the GPU actually the bottleneck, or is it something else."

Both are written as plain YAML and applied via the `sts` CLI — no manual panel-clicking required. This repo doubles as a tutorial: if you've never built a SUSE Observability dashboard outside the UI before, read on.

## Who this is for

Anyone who already has SUSE Observability running and ingesting GenAI telemetry (via the OpenTelemetry Collector + the OpenWebUI Pipelines filter) and wants dashboards for it, plus the general recipe to build their own. It assumes:

- A working SUSE Observability instance, reachable over HTTPS.
- GenAI metrics already flowing in (`gen_ai_client_*` series) — if they aren't yet, see the [SUSE AI Observability Extension](https://github.com/SUSE/suse-ai-observability-extension) and [official monitoring guide](https://documentation.suse.com/suse-ai-factory/latest/pdf/AI-monitoring_en.pdf) first.
- Optionally, NVIDIA GPU nodes with the [GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/index.html) installed (for the second dashboard — its DCGM exporter is what feeds `DCGM_FI_DEV_*` metrics).

## Quick start

1. Install the [`sts` CLI](https://documentation.suse.com/suse-observability/latest/) if you don't have it already (SUSE Observability's own install docs cover this, or grab it from `https://dl.stackstate.com/stackstate-cli/install.sh`).
2. Authenticate with an **admin-scoped** credential — see [Authentication](#authentication) below, this is the part that trips people up.
3. Apply both dashboards:
   ```bash
   sts dashboard apply --context admin -f dashboards/genai-model-cost-efficiency.yaml
   sts dashboard apply --context admin -f dashboards/gpu-saturation-vs-llm-load.yaml
   ```
4. Open SUSE Observability's UI → *Dashboards*. Each dashboard has a **Cluster** picker at the top — select the cluster your SUSE AI workloads run in.

That's it. Re-running `sts dashboard apply` on the same file after it's been applied once updates it in place (the CLI records the assigned `id` server-side; see [Updating a dashboard](#updating-a-dashboard-you-already-applied) if you want to manage that locally instead).

## Authentication

SUSE Observability dashboards are Perses-schema YAML under the hood, and `sts dashboard apply`/`edit`/`delete` need write access to them. A service token scoped to a narrower role (e.g. a Kubernetes-troubleshooting role) will get a bare `403 Forbidden` — there's no clearer error than that, so if you hit one, this is almost always why.

Create (or reuse) an **admin-scoped** service token:

```bash
sts service-token create --name dashboard-management --roles stackstate-admin
```

Then save it as a named CLI context:

```bash
sts context save --name admin \
  --url https://<your-suse-observability-host> \
  --api-token <the-token-from-above>
```

Every `sts dashboard ...` command below assumes `--context admin`. If you have a browser session logged in as an admin user, that account's personal API token (under your user settings) also works with `--api-token`.

## Understanding the dashboard schema

You don't need to know Perses to use the two dashboards above as-is, but you'll want this to customize them or build your own.

A dashboard YAML has three parts:

```yaml
name: My Dashboard          # shown in the UI
scope: publicDashboard      # visible to everyone with dashboard read access
dashboard:
  metadata:
    project: '{"saveVariables":false}'
  spec:
    layouts: [ ... ]         # WHERE panels sit on the grid
    panels: { ... }          # WHAT each panel shows
    variables: [ ... ]        # dropdown pickers panels can reference, e.g. ${cluster}
```

**`layouts`** is a 24-column grid. Each item is `{x, y, width, height}` plus a `content.$ref` pointing at a named panel:

```yaml
layouts:
- kind: Grid
  spec:
    items:
    - x: 0
      "y": 0
      width: 12
      height: 4
      content:
        $ref: '#/spec/panels/my_panel'
```

**`panels`** is a map from that same name to a `display` (title/description), a `plugin` (chart type), and one or more `queries`. Panel kinds confirmed working in this recipe: `TimeSeriesChart`, `StatChart`, `GaugeChart`, `Markdown`. Queries are PromQL, wrapped as:

```yaml
queries:
- kind: TimeSeriesQuery
  spec:
    plugin:
      kind: PrometheusTimeSeriesQuery
      spec:
        alias: ${gen_ai_request_model}     # legend label, can reference query result labels
        query: sum by (gen_ai_request_model)(rate(gen_ai_client_operation_duration_seconds_count{k8s_cluster_name="${cluster}"}[${__rate_interval}]))
```

`${__rate_interval}` is a built-in variable that resolves to a sane `rate()`/`increase()` window for whatever time range the dashboard viewer has selected — always prefer it over a hardcoded `[5m]`.

**`variables`** define dropdown pickers, sourced from real label values rather than typed in by hand — this is what makes `${cluster}` in both dashboards here a real picker instead of a hardcoded string:

```yaml
variables:
- perseslistvariable:
    kind: ListVariable
    spec:
      name: cluster
      display:
        name: Cluster
      allowAllValue: false
      allowMultiple: false
      sort: alphabetical-asc
      plugin:
        kind: MetricLabelValues
        spec:
          labelName: k8s_cluster_name
          matchers:
          - gen_ai_client_operation_duration_seconds_count   # any metric that carries the label you want values from
  persestextvariable: null
```

The easiest way to learn this schema further is to export one of SUSE Observability's own built-in dashboards (every install ships a few — Kubernetes Cluster, Data/Logs/Metrics/Topology/Traces processing) and read it as a worked example:

```bash
sts dashboard list --context admin -o json      # find an id
sts dashboard describe --context admin --id <id> -o text > example.yaml
```

## Discovering your own metric and label names

Don't guess PromQL — different SUSE Observability/extension versions can emit slightly different metric names, and you should always confirm against your own instance. Query VictoriaMetrics' Prometheus-compatible HTTP API directly. From a node with cluster access:

```bash
POD_IP=$(kubectl get pod suse-observability-victoria-metrics-0-0 \
  -n suse-observability -o jsonpath='{.status.podIP}')

# every metric name currently being ingested that looks GenAI- or GPU-related
curl -s http://$POD_IP:8428/api/v1/label/__name__/values | tr ',' '\n' | grep -i 'gen_ai\|dcgm'

# the full label set for one specific metric
curl -s "http://$POD_IP:8428/api/v1/series?match[]=gen_ai_client_operation_cost_USD_sum"
```

(Note: querying the VictoriaMetrics *service* by DNS name from a bare node generally won't resolve — cluster DNS isn't configured on the node's own resolver. Go through a pod IP, or `kubectl exec` into any pod that has `curl`, instead.)

At the time this repo was built, the confirmed metric/label set was:

| Domain | Metrics | Key labels |
|---|---|---|
| GenAI (OpenWebUI Pipelines filter) | `gen_ai_client_operation_cost_USD_{sum,count,bucket}`, `gen_ai_client_operation_duration_seconds_{sum,count,bucket}`, `gen_ai_client_token_usage_{sum,count,bucket}` | `gen_ai_request_model`, `gen_ai_response_model`, `gen_ai_provider_name`, `gen_ai_operation_name`, `gen_ai_token_type` (`input`/`output`), `k8s_cluster_name`, `k8s_namespace_name` |
| GPU (NVIDIA DCGM exporter) | `DCGM_FI_DEV_GPU_UTIL` (0–100), `DCGM_FI_DEV_FB_USED`/`_FREE` (MiB), `DCGM_FI_DEV_POWER_USAGE` (W), `DCGM_FI_DEV_GPU_TEMP`, `DCGM_FI_PROF_PIPE_TENSOR_ACTIVE` (0–1 fraction) | `k8s_node_name`, `container`, `k8s_namespace_name` (tagged with the *workload's* namespace using the GPU, not `gpu-operator`) |

`DCGM_FI_PROF_PIPE_TENSOR_ACTIVE` is worth calling out specifically: it's a more honest saturation signal for LLM inference than raw `DCGM_FI_DEV_GPU_UTIL`, since it reflects tensor-core activity specifically rather than "the GPU did anything at all in this sample window." The `gpu-saturation-vs-llm-load.yaml` dashboard plots both side by side for exactly this reason.

## Customizing

Both dashboard files are ordinary YAML — copy a panel block, change its `query`/`alias`/`display.name`, and give it a new key under `panels:` plus a grid slot under `layouts:`. Then re-apply:

```bash
sts dashboard apply --context admin -f dashboards/genai-model-cost-efficiency.yaml
```

Some ideas that weren't built into these two, but the same metric catalog supports:

- **Per-user cost attribution** — none of the shipped GenAI metrics carry a user identity today (only `chat_id`-scoped tracing does). If that matters to you, it needs a small addition to the OpenWebUI Pipelines filter itself to tag spans/metrics with the requesting user, before it's buildable as a dashboard.
- **Finish-reason breakdown** — `gen_ai.response.finish_reasons` is captured on trace spans (not the metrics used here); a topology/traces-based panel could surface how often responses are getting cut off by `length` vs. ending cleanly at `stop`.
- **Multi-GPU-node comparison** — add a `k8s_node_name` variable alongside `cluster` if you have more than one GPU worker, and split the GPU panels `by (k8s_node_name)`.

## Updating a dashboard you already applied

`sts dashboard apply` creates a new dashboard when the YAML has no `id` field, and updates in place when it does. The files in this repo intentionally ship **without** an `id`, so they stay portable across different SUSE Observability instances — applying them fresh always creates a new dashboard rather than assuming a specific instance's dashboard ID.

If you want to manage updates to a specific instance's copy under version control, add the `id` this instance assigned (from the `apply`/`list` output) as a second line, right after `name:`:

```yaml
name: GenAI Model Cost & Efficiency
id: 244506610432277
description: ...
```

Other useful verbs:

```bash
sts dashboard list --context admin                       # see everything, with ids
sts dashboard edit --context admin --id <id>              # opens live YAML in $EDITOR, applies on save
sts dashboard clone --context admin --id <id>              # duplicate as a starting point
sts dashboard delete --context admin --id <id>              # remove permanently
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `403 Forbidden` on `dashboard apply`/`list`/`service-token create` | The active context's token doesn't have the `stackstate-admin` role. | Mint/use an admin-scoped token — see [Authentication](#authentication). |
| A `histogram_quantile(...rate(...[$__rate_interval]))` panel is empty | GenAI chat completions are sparse, event-driven data, not a continuous stream — a short selected time range (e.g. "Last 15 minutes") may not contain enough samples for `rate()` to compute anything. | Widen the dashboard's time range to at least "Last 1 hour", especially in a low-traffic environment. |
| `Cluster` dropdown is empty, or panels show no data after selecting one | The `matchers` metric named in the `variables` block (`gen_ai_client_operation_duration_seconds_count` / `DCGM_FI_DEV_GPU_UTIL`) isn't present yet on this instance — either telemetry isn't flowing, or your extension version uses different metric names. | Re-run the [discovery queries](#discovering-your-own-metric-and-label-names) above against your instance and adjust the `matchers`/label names to match what's actually there. |
| Total Usage Cost panel stays empty while everything else populates | Cost is computed client-side by the Pipelines filter from a `pricing.json` catalog it fetches over HTTP at startup — if that fetch fails (wrong URL, network policy, etc.), no cost is ever recorded for any model, silently. | Check the `PRICING_JSON` env var on the OpenWebUI Pipelines deployment resolves and returns 200; the filter logs `"Cost is 0 or negative... not recording"` when debug logging is enabled, which confirms this exact failure mode. |

## Sample data

Don't have GenAI/GPU traffic flowing yet, or want to try these dashboards without touching a live cluster? `sample-data/` has everything to populate a throwaway VictoriaMetrics with data in the right shape:

- **`sample-data/synthetic/`** — plausible fake time series (cost, tokens, duration, GPU util/tensor-active/memory/power/temp) matching the metric and label names above, generated by `sample-data/generate_synthetic.py [out_dir] [hours] [step_seconds]`. No cluster access needed.
- **`sample-data/real/`** — an actual export pulled from a live SUSE AI environment, as a concrete example of real shape/scale (sparse cost/token events, a GPU idling most of the time — see the [sparse-data troubleshooting row](#troubleshooting) above).
- **`extract-dashboard-data.sh [range_seconds] [step_seconds] [out_dir]`** — re-pulls a fresh `real/`-style export from your own cluster via `kubectl port-forward` to the VictoriaMetrics service (override the namespace/service name with `VM_NAMESPACE`/`VM_SERVICE` env vars if yours differ from the defaults). Pipes through `sample-data/_convert_to_csv.py` to flatten the raw Prometheus JSON into CSV.
- **`sample-data/insert_to_victoriametrics.py <csv_dir> [vm_url]`** — loads either CSV set back into a target VictoriaMetrics via its native `/api/v1/import` endpoint, reconstructing the original metric names/labels so both dashboards render against it unchanged. Handy against a local sandbox:

  ```bash
  docker run -d -p 8428:8428 victoriametrics/victoria-metrics
  python3 sample-data/insert_to_victoriametrics.py sample-data/synthetic http://localhost:8428
  ```

  Then point the dashboards' `PrometheusTimeSeriesQuery` datasource at that instance. Note that an instant query at "now" will come back empty since the sample timestamps are fixed in the past — use a time range that covers them.

## References

- [SUSE Observability documentation](https://documentation.suse.com/suse-observability/latest/)
- [SUSE AI Observability Extension (GitHub)](https://github.com/SUSE/suse-ai-observability-extension) — the OpenWebUI Pipelines filter (`suse_ai_filter.py`) that produces the `gen_ai_client_*` metrics used here, plus the `pricing.json` cost catalog.
- [Monitoring SUSE AI with OpenTelemetry and SUSE Observability](https://documentation.suse.com/suse-ai-factory/latest/pdf/AI-monitoring_en.pdf) (PDF) — the official guide for wiring up GPU/vLLM/Milvus/OpenSearch/OpenWebUI telemetry in the first place.
- [AI Factory Deployment guide](https://documentation.suse.com/suse-ai-factory/latest/pdf/AI-Factory-deployment_en.pdf) (PDF) — broader SUSE AI Factory stack deployment.
- [Perses](https://perses.dev/) — the open dashboard schema/engine SUSE Observability dashboards are built on. Its own docs are a good reference for panel/query plugin options beyond what's used here.

## License

Apache-2.0, matching the license of the SUSE AI Observability Extension these dashboards depend on.
