# suse-observability-genai-dashboards (Helm chart)

Installs the two GenAI dashboards from this repo into a running [SUSE Observability](https://www.suse.com/products/suse-observability/) instance, using a Helm hook Job that runs `sts dashboard apply` on your behalf.

## Prerequisites

- A SUSE Observability instance reachable from inside the cluster you're installing into (or otherwise reachable over HTTPS from the Job's pod).
- An admin-scoped **service token** (see the root [README's Authentication section](../README.md#authentication) for how to mint one with `sts service-token create --name dashboard-management --roles stackstate-admin` — a personal API token from the UI also works, but a service token is the credential meant for this kind of unattended automation).
- The cluster running the Job needs egress to `dl.stackstate.com` (to install the `sts` CLI) and to your SUSE Observability URL.

## Install

1. Create a Secret holding your service token — the chart never accepts a plaintext token via `values.yaml`:

   ```bash
   kubectl create secret generic suse-observability-token \
     --from-literal=serviceToken=<your-admin-scoped-service-token>
   ```

2. Add the repo and install:

   ```bash
   helm repo add suse-observability-genai-dashboards https://doccaz.github.io/suse-observability-genai-dashboards/
   helm repo update

   helm install genai-dashboards suse-observability-genai-dashboards/suse-observability-genai-dashboards \
     --set suseObservability.url=https://<your-suse-observability-host> \
     --set suseObservability.existingSecret.name=suse-observability-token
   ```

3. Check the apply Job if a dashboard doesn't show up:

   ```bash
   kubectl logs job/genai-dashboards-genai-dashboards-apply-1
   ```

`helm upgrade` re-runs the same Job. The chart tracks the dashboard id SUSE Observability assigns on first apply in a `<release>-dashboard-ids` ConfigMap, and injects it back into the YAML before re-applying, so upgrades update the same dashboards in place instead of creating duplicates.

## Values

| Key | Default | Description |
|---|---|---|
| `suseObservability.url` | `""` | SUSE Observability instance URL (required) |
| `suseObservability.existingSecret.name` | `""` | Secret holding the service token (required) |
| `suseObservability.existingSecret.key` | `serviceToken` | Key within that Secret |
| `suseObservability.insecureSkipVerify` | `false` | Skip TLS verification (self-signed certs) |
| `dashboards.costEfficiency.enabled` | `true` | Apply the GenAI cost/efficiency dashboard |
| `dashboards.gpuSaturation.enabled` | `true` | Apply the GPU saturation dashboard |
| `cleanupOnUninstall` | `false` | Run `sts dashboard delete` for tracked dashboards on `helm uninstall` |
| `image.repository` / `image.tag` | `alpine/k8s` / `1.30.4` | Image used to run the apply/cleanup Jobs (has `kubectl`, `curl`, `jq`; installs `sts` at runtime) |

See [`values.yaml`](values.yaml) for the full list.

## Uninstall

```bash
helm uninstall genai-dashboards
```

By default this leaves the dashboards in place in SUSE Observability. Set `cleanupOnUninstall: true` before uninstalling if you want them deleted automatically.

## Limitations

- The apply/cleanup Jobs install the `sts` CLI at runtime from `dl.stackstate.com` rather than baking it into a custom image, to avoid maintaining a separate container image. This means the Job needs network egress at install/upgrade time.
- Dashboard-id tracking relies on `sts dashboard list -o json` carrying `name`/`id` fields that match by dashboard name; if two dashboards share a name in the same SUSE Observability instance, tracking can pick the wrong one. Don't reuse dashboard names across unrelated installs of this chart into the same instance.

## For maintainers: publishing a new chart version

`.github/workflows/release-chart.yaml` packages and publishes this chart to the `gh-pages` branch (via [chart-releaser](https://github.com/helm/chart-releaser-action)) whenever `charts/**` changes on `main`, but it silently no-ops if `Chart.yaml`'s `version:` hasn't been bumped (`skip_existing: true`) — bump it on every change meant to ship. The `gh-pages` branch and GitHub Pages itself (Settings → Pages → source: `gh-pages`) need to be set up once, by hand, before `helm repo add` resolves at all.
