{{/*
Chart name and version label
*/}}
{{- define "genai-dashboards.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "genai-dashboards.labels" -}}
helm.sh/chart: {{ include "genai-dashboards.chart" . }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
ServiceAccount name
*/}}
{{- define "genai-dashboards.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (printf "%s-genai-dashboards" .Release.Name) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Name of the ConfigMap tracking assigned dashboard ids
*/}}
{{- define "genai-dashboards.idConfigMapName" -}}
{{- printf "%s-dashboard-ids" .Release.Name -}}
{{- end -}}

{{/*
Validate required suseObservability values. Call from templates that need it.
*/}}
{{- define "genai-dashboards.validate" -}}
{{- if not .Values.suseObservability.url -}}
{{- fail "suseObservability.url is required (the SUSE Observability instance URL, e.g. https://observability.example.com)" -}}
{{- end -}}
{{- if not .Values.suseObservability.existingSecret.name -}}
{{- fail "suseObservability.existingSecret.name is required: create a Secret holding your admin-scoped API token and reference it here. This chart does not accept a plaintext token via values.yaml." -}}
{{- end -}}
{{- end -}}
