# syntax=docker/dockerfile:1

# The official sts CLI image is distroless (just /usr/bin/sts, no shell/jq/kubectl),
# so we only borrow the binary from it rather than using it as a base.
FROM stackstate/stackstate-cli2:3.9.0 AS sts

# bci-micro/bci-minimal have no usable package manager front-end; stage jq/grep/sed
# (and their shared-lib deps) with zypper --installroot from bci-base, then copy the
# staged root into the minimal final image below.
FROM registry.suse.com/bci/bci-base:15.7 AS builder
ARG TARGETARCH
ARG KUBECTL_VERSION=v1.30.4
RUN zypper --gpg-auto-import-keys --installroot /staging -n install --no-recommends -y \
      jq grep sed ca-certificates \
 && curl -fsSL -o /staging/usr/local/bin/kubectl \
      "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
 && chmod +x /staging/usr/local/bin/kubectl

FROM registry.suse.com/bci/bci-minimal:15.7
LABEL org.opencontainers.image.source="https://github.com/doccaz/suse-observability-genai-dashboards" \
      org.opencontainers.image.description="Minimal SLE BCI image with sts, jq, kubectl, for the suse-observability-genai-dashboards Helm chart's hook Jobs"
COPY --from=builder /staging/ /
COPY --from=sts /usr/bin/sts /usr/local/bin/sts
