# 6. Cloud Run OpenTelemetry telemetry export path

Date: 2026-07-08

Owner: Fabian Spieß · Informed: Platform Engineering, Johannes "Hannes" Zorn, Arne Baumann

## Status

Proposed

Tracked as [OP-3108](https://aignx.atlassian.net/browse/OP-3108)

Implementation PRs:

- [gitops#3459](https://github.com/aignostics/gitops/pull/3459) — `aignx-otel-gateway` instance on `shared-tools`, Contour `HTTPProxy`, `k8sAttributes.enabled` toggle.
- [foundry-python-core#96](https://github.com/aignostics/foundry-python-core/pull/96) — `otel_initialize()` in `aignostics_foundry_core.otel`, wired into `boot()`; `instrument_fastapi()` applied automatically by `init_api()`.
- [foundry-python#385](https://github.com/aignostics/foundry-python/pull/385) — unconditional Direct VPC egress in the generated Cloud Run manifest/deploy workflow.
- [foundry-infrastructure#10](https://github.com/aignostics/foundry-infrastructure/pull/10) — unconditional `vpc_network`/`vpc_subnetwork` placeholders in `project.hcl`, companion fix for foundry-python#385.

## Context

Foundry services running on Cloud Run (e.g. `pviz`) need to send traces, metrics, and logs
into the shared observability stack (Tempo, Loki, Prometheus/Thanos), the same way GKE-hosted
services already do. Today every OTel collector is cluster-internal — nothing is reachable
from Cloud Run, which sits on the shared VPC but outside any GKE cluster's pod network.

Existing GKE-hosted services already use a single OTLP gRPC endpoint, one OTel push
gateway collector, fanning out to traces/metrics/logs internally and the goal is to give
Foundry Cloud Run services the same experience: one endpoint, no per-signal config, no code
beyond pointing the SDK at it.

Out of scope per that ticket:
changing telemetry export for existing in-cluster services, and per-signal endpoints.

This decision spans four repositories: `gitops` (the collector instance, ingress, and cert
wiring), this repo, `foundry-python-core` (how a Foundry service actually emits telemetry),
and the two Copier templates that scaffold every Foundry service, `foundry-python` and
`foundry-infrastructure` (Direct VPC egress reachability, see Network reachability below).


**Not up for discussion here**: the `collector-push-gateway` chart itself — a Deployment-mode
OTel push gateway collector with an optional two-tier loadbalancing backend, k8s metadata
enrichment, and fan-out to Tempo/Loki/Prometheus. This is in PEng's standard collector
pattern, already deployed elsewhere in the fleet. That architecture is a given. What this ADR
does cover: creating a new instance of it for Cloud Run, how that instance is exposed
(adding an ingress, since none of the standing instances need one) and specific enhancements
applied to this instance to make it suitable for a non-k8s sources, e.g. disabling `k8sattributes`
enrichment.

**Also out of scope**: authentication. Neither this new gateway nor any existing collector in
the fleet authenticates callers — the entire telemetry stack chain today trusts network
location alone (reachable only from inside the VPC/cluster pod network). Adding
authentication — e.g. Contour's `HTTPProxy.spec.virtualhost.jwtProviders` (Envoy's `jwt_authn`
filter, which could verify Google-issued Cloud Run service-account identity tokens)
is a valid improvement worth considering, but it would apply to the
whole chain, not just this one gateway, and is out of scope here rather than solved as a
side effect of this decision.

### Which collector instance Cloud Run talks to

A new, vpc-only instance of the standard OTel push gateway collector: `collector-push-gateway`
(same chart, unchanged architecture) deployed in `shared-tools`, in loadbalancing mode,
reachable only over the shared VPC via Direct VPC egress, never
publicly.

### Reachability — Direct VPC connection

Being in a GCP project attached to the shared VPC does not, by itself, give Cloud Run a path
to reach anything on that VPC. Google's own docs confirm Shared VPC service-project membership
only makes subnets *available* but Cloud Run must be explicitly configured with Direct VPC
egress (a specific network + subnet) to actually route traffic there instead of the public
internet.

What's already in place: 44 Foundry service-projects have `enable_cloudrun_vpc_access = true`
(`gcp-service-projects` Terraform module), each granting the Cloud Run service agent
`roles/compute.networkUser` on a dedicated per-project/per-env subnet. This is IAM only — it
permits Direct VPC egress, it doesn't configure it on any actual Cloud Run resource.

What's incomplete on the `foundry-python` template side:
- The generated Cloud Run manifest (`service.template.yaml.jinja`) already carries the Direct
  VPC egress annotations (`run.googleapis.com/network-interfaces`,
  `vpc-access-egress: private-ranges-only`), but only rendered
  if cloud sql or memorystore is enabled, not for general reachability.
- Even where it does render, the subnet values feeding it (`vpc_network`/`vpc_subnetwork` in
  the service's own `infrastructure/<env>/project.hcl`) are manual placeholders
  (`PLACEHOLDER_VPC_NETWORK`/`PLACEHOLDER_VPC_SUBNETWORK`) filled in by hand after onboarding.

Net effect: reachability isn't a solved problem for any Foundry Cloud Run service today,
Cloud-SQL/Memorystore-enabled or not. This is the largest open risk for this ADR's rollout.

Resolved direction: Direct VPC egress will be unconditional, every Cloud Run service gets
it regardless of whether it uses Cloud SQL/Memorystore.

### Alternatives considered — Sidecar collector vs. direct SDK export from Cloud Run

This is a separate axis from the instance question above: does each Cloud Run service run its
own local collector hop, or export straight to the shared instance?

**Option A — Sidecar OTel Collector per Cloud Run service**
Each Cloud Run revision runs its own collector as a second container, forwarding OTLP upstream
to the shared instance. Foundry services are built into an image and deployed via the GCP API
from a generated Knative `Service` manifest (`deployment/cloudrun/service.template.yaml.jinja`
in the `foundry-python` Copier template, applied via the `deploy-cloudrun` GitHub Action), and
Cloud Run's multi-container/sidecar support is exposed directly through that manifest —
mechanically adding a second container is straightforward. The real benefit would be scaling.
A sidecar scales automatically alongside each Cloud Run instance, so collector capacity always
tracks the service's own traffic with no separate scaling decision to make.
Metrics are the hard blocker: our stack ingests metrics exclusively via
Prometheus **scrape** (a `ServiceMonitor` targeting a stable in-cluster Service). There is no Thanos
Receive enabled anywhere in the fleet, and we don't run a real Prometheus Pushgateway
either. A sidecar bundled into an ephemeral, non-cluster Cloud Run instance has no stable,
discoverable target for Prometheus to scrape. Its metrics
would simply never be, or with a static target configuration in Prometheus potentially too late,
collected. This rules the option out.

**Option B (chosen) — Direct SDK export to the shared instance**
Cloud Run services export via the OTel SDK's own OTLP exporter straight to the gateway, no local hop.
This also matches how this same repo already handles error tracking: Sentry is integrated as in-process SDK instrumentation.

Accepted risk: with no local buffer, telemetry the SDK hasn't flushed yet (spans queued in
`BatchSpanProcessor`, metric points accumulated since the last periodic export) is lost if the
Cloud Run instance is torn down first — scale-to-zero, revision replacement, or a crash. Cloud
Run sends `SIGTERM` with a grace period (10s default, extendable) before `SIGKILL`; registering
a shutdown hook that force-flushes the tracer/meter providers catches most of this, but it's a
mitigation, not a guarantee (an abrupt kill or a grace period shorter than the flush can still
drop data).

Because every service points at this one gateway endpoint rather than a vendor-specific one,
the export destination is switchable later (e.g. to Grafana Cloud or another vendor) by
reconfiguring only the gateway's own exporters.

### Alternatives considered — Gateway Ingress

**Option A — `nginx-internal` Ingress + `GRPCS` backend-protocol annotation**
`nginx-internal` already runs on `shared-tools`. A plain `Ingress` with
`nginx.ingress.kubernetes.io/backend-protocol: "GRPCS"` (plus `proxy-ssl-verify: "off"`, since
the collector's cert isn't issued for the public hostname) would work.
Rejected: ingress-nginx is a deprecated ingress controller company-wide — the org has already
standardized on Contour as the forward-looking ingress technology, so this isn't only about
elegance for this one gateway.

**Option B (chosen) — Add `contour-internal` to `shared-tools`, use a Contour `HTTPProxy`**
Contour's `HTTPProxy` has a native per-route `services[].protocol: tls` field — no
backend-protocol annotation needed. Required adding `shared-tools` to the `contour-internal`
ApplicationSet (envoy-internal IngressClass), which didn't run there before.


### Alternatives considered — k8s metadata enrichment for a non-k8s source

**Option A — Leave the `k8sattributes` processor always on**
No chart change needed.
Rejected: Cloud Run isn't a Kubernetes workload. The processor can't resolve pod identity for
it and would attach empty or misleading `k8s.pod.name`/`k8s.deployment.name`/`k8s.namespace.name`
labels to Cloud Run telemetry — actively degrading data quality in Tempo/Loki/Prometheus rather
than just being a no-op.

**Option B (chosen) — Add a `k8sAttributes.enabled` toggle to the `collector-push-gateway` chart**
Defaults to `true` (no behavior change for any existing collector instance); set to `false`
only for the new `aignx-otel-gateway` instance on `shared-tools`.

### Alternatives considered — how a Foundry Python service instruments itself

**Option A — `opentelemetry-instrument` CLI wrapper (zero-code)**
Wrap the Cloud Run service's startup command with the `opentelemetry-instrument` launcher;
configure entirely through environment variables.
Rejected: the actual Cloud Run startup command is generated per-service by the
`foundry-python` Copier *template* (`deployment/cloudrun/service.template.yaml.jinja`), which
only affects newly generated or explicitly re-templated (`copier update`) services.
Additionally this kind of instrumentation only provides predefined instrumentation and helps in case of lack of codeownership.

**Option B (chosen) — Programmatic init inside this repo's `boot()`**
Add `otel_initialize()` (`aignostics_foundry_core.otel`), following the pattern already
established for Sentry: a pydantic-settings-driven `enabled` flag,
called once from `boot()`, which every generated Foundry service already calls before
instantiating FastAPI/uvicorn. One `aignostics-foundry-core` version bump reaches every service
that upgrades its dependency — no per-service code or template changes for process-level
tracing/metrics.
Request-level FastAPI span instrumentation (`instrument_fastapi(app)`) needs the live `app`
object, which doesn't exist yet when `boot()` runs — but `init_api()` (the function that
actually constructs it) does, and always runs after `boot()`, since it's only reachable via
code that imports the project package, which is where `boot()` fires as an `__init__.py` side
effect. So `init_api()` applies it automatically instead of requiring template wiring.

### Alternatives considered — per-signal export defaults

**Option A — One `enabled` flag governing traces, metrics, and logs together**
Simplest mental model, matches the original `sentry_initialize()`-style single switch.
Rejected: log volume and cost characteristics differ meaningfully from traces/metrics (far
higher per-request volume in most services).

**Option B (chosen) — Independent per-signal toggles under a master switch**
`enabled` remains the overall kill switch; `traces_enabled` and `metrics_enabled` default to
`True` once it's on (preserving the original combined behavior as the default), `logs_enabled`
defaults to `False`. A service can disable any single signal (e.g. metrics only) without
affecting the others.

### GCP-native observability — not a considered alternative

It's also worth noting this ADR doesn't exclude it, since instrumentation
is configured entirely through the standard `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable.
any individual service remains free to point its SDK at Google's own OTLP-compatible
endpoint instead of our solution.

## Decision

Deploy `collector-push-gateway` (loadbalancing mode) on `shared-tools` as `aignx-otel-gateway`,
exposed only internally via a Contour `HTTPProxy`
(reachable from Cloud Run over the shared VPC via Direct VPC egress, never publicly), backed by
an explicit `cert-manager.io/v1 Certificate` and with `k8sAttributes.enabled: false` for this
instance only.

On the service side, add `otel_initialize()` to `aignostics_foundry_core.boot()`, mirroring the
existing `sentry_initialize()` pattern: a master `{PROJECT}_OTEL_ENABLED` switch, with traces
and metrics independently defaulting on (`traces_enabled`/`metrics_enabled`) once that's set and
`OTEL_EXPORTER_OTLP_ENDPOINT` is configured (standard, unprefixed OTel env vars — not
project-specific ones); logs bridged from loguru via a custom sink but gated behind a separate
`{PROJECT}_OTEL_LOGS_ENABLED` flag, off by default. Each signal can also be disabled
individually. No sidecar collector, no CLI-wrapper instrumentation. The only `foundry-python`
template change is Direct VPC egress becoming unconditional — FastAPI instrumentation itself
needs no template wiring, since `init_api()` in this repo applies it automatically.

## Consequences

**Easier**:
- Foundry service owners get parity with existing mono services: one OTLP endpoint, one env
  var to point at it, no per-signal configuration.
- Every Foundry Python service gets tracing/metrics support via a single
  `aignostics-foundry-core` version bump — no per-service code or template changes.
- The `k8sAttributes.enabled` toggle is reusable for any future non-k8s telemetry source, not
  just Cloud Run.
- Adding `contour-internal` to `shared-tools` and using `HTTPProxy` avoids nginx
  backend-protocol annotation workarounds and matches how the rest of the fleet already
  exposes gRPC-speaking backends.
- Routing Cloud Run metrics through the collector, rather than any hypothetical direct push
  straight to a metrics backend, keeps cardinality control and label normalization centralized
  (the same `attributes/drop_high_cardinality`/`resource/drop_high_cardinality` processors and
  `k8s.cluster.name`-style conventions every other source already goes through) instead of each
  new source inventing its own. Same reasoning applies to traces/logs — one place owns what
  gets attached to telemetry before it lands in Tempo/Loki/Prometheus, giving every consumer of
  that data (dashboards, alerts, on-call) a common, predictable shape regardless of source.

**Harder / risks**:
- `shared-tools` now runs two ingress controllers (`nginx-internal` and `envoy-internal`)
  instead of one — a small increase in operational surface for that cluster.
- Reachability isn't guaranteed for any Foundry Cloud Run service today (see Network
  reachability above) — closing that gap is out of scope for this ADR, tracked as follow-up.
- The gateway starts with conservative replica counts (2 push-gateway / 2 loadbalancer-backend)
  since this is a new, currently-zero-traffic path — will need revisiting once real traffic
  lands.
- Logs being opt-in means a service that only sets `{PROJECT}_OTEL_ENABLED=true` will not see
  its logs in Loki via this path — a support/documentation risk if not made clear in onboarding
  material (the companion runbook covers this).
