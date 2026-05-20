# Disruption Analysis

Analysis of disruption events in Prow CI job runs using interval/timeline data, audit logs, pod logs, and CPU metrics.

## Interval File JSON Structure

Each timeline item has this structure:

```json
{
  "level": "Error",
  "source": "Disruption",
  "locator": {
    "type": "Disruption",
    "keys": {
      "backend-disruption-name": "host-to-host-new-connections",
      "connection": "new",
      "disruption": "host-to-host-from-node-...-worker-X-to-node-...-master-0-endpoint-10.0.0.5"
    }
  },
  "message": {
    "reason": "DisruptionBegan",
    "humanMessage": "... stopped responding to GET requests over new connections",
    "annotations": { "reason": "DisruptionBegan" }
  },
  "from": "2026-03-21T21:50:24Z",
  "to": "2026-03-21T21:50:26Z"
}
```

### Key Fields
- **`source`**: Event category. `"Disruption"` for disruption events
- **`level`**: `"Error"`, `"Warning"`, `"Info"`. Disruption events are Error or Warning
- **`locator.keys.backend-disruption-name`**: The backend being monitored
- **`locator.keys.disruption`**: For host-to-host backends, encodes `host-to-host-from-node-{src}-to-node-{dst}-endpoint-{ip}`
- **`locator.keys.connection`**: `"new"` or `"reused"`
- **`message.reason`**: `"DisruptionBegan"` or `"DisruptionEnded"`

## Finding Timeline Files

Timeline file locations vary by job type:
- **Non-upgrade jobs**: Usually one file at `artifacts/{target}/openshift-e2e-test/artifacts/junit/e2e-timelines_spyglass_{timestamp}.json`
- **Upgrade jobs**: Usually two files (one per phase -- upgrade and conformance), possibly under different workflow step directories

```bash
# List all timeline files
gcloud storage ls "gs://test-platform-results/logs/{job_name}/{build_id}/artifacts/**/e2e-timelines_spyglass_*.json"
```

**GCS bucket note**: Prow URLs may contain `origin-ci-test` in the path, but the actual bucket is always `test-platform-results`.

### Phase Detection
For upgrade jobs with two timeline files: the first file (sorted by filename) is the upgrade phase, the second is the conformance/e2e test phase.

## Backend Classification

| Backend Type | Name Pattern | Root Cause Indicator |
|-------------|-------------|---------------------|
| **Cache** | Name contains `cache` | etcd or global networking problem |
| **Non-cache** | Standard backends | Component or cluster networking problem |
| **Canary** | `ci-cluster-network-liveness` | Test infrastructure network issues |
| **Cloud** | Cloud network-liveness backends | Cloud provider issues |

### Critical Diagnostic Pattern

When **all 4 variants** of a backend fail simultaneously (e.g., `openshift-api-new-connections`, `openshift-api-reused-connections`, `cache-openshift-api-new-connections`, `cache-openshift-api-reused-connections`), the root cause is almost always **control plane node resource exhaustion** (disk I/O -> etcd stalls -> apiserver timeouts), not a networking issue.

Confirming evidence: etcd `slow fdatasync`, `apply took too long`, and `ExtremelyHighIndividualControlPlaneCPU` alerts.

## Source-Node Analysis

### Patterns
- **single-source-fan-out**: All disruptions from one node to many targets. Source-side issue (OVS stall, CPU starvation, disk I/O) -- not network-wide
- **multi-source**: Disruptions from multiple source nodes. Network-wide, destination-side, or infrastructure-level issue
- **unknown**: Backend type doesn't include node info (e.g., ingress-routed backends like image-registry)

When single-source-fan-out is detected, focus investigation on that specific node: CPU, disk I/O, OVS vswitchd logs, heavy workloads.

## Concurrent Event Sources

| Source | What It Tells You |
|--------|-------------------|
| `OVSVswitchdLog` | OVS packet processing stalls; poll intervals >500ms = networking frozen; >1000ms = OVS essentially frozen |
| `CPUMonitor` | Nodes with CPU >95% (starves OVS and other system processes) |
| `CloudMetrics` | Azure disk IOPS saturation, queue depth, bandwidth (disk I/O pressure) |
| `EtcdLog` | `apply took too long`, `slow fdatasync`, ReadIndex delays |
| `EtcdDiskCommitDuration` | etcd disk commit above 25ms threshold |
| `EtcdDiskWalFsyncDuration` | etcd WAL fsync above 10ms threshold |
| `AuditLog` | API request failures during disruption |
| `Alert` | Firing Prometheus alerts (ExtremelyHighIndividualControlPlaneCPU, etc.) |
| `NodeMonitor` / `MachineMonitor` | Node NotReady, machine phase changes |
| `ClusterVersion` / `ClusterOperator` | Upgrade progress, operator status |
| `E2ETest` | Active test phase (upgrade vs post-upgrade e2e tests) |

## Audit Log Signals

For kube-api, oauth-api, and openshift-api disruption:
- **Audit entries show failures during disruption**: API server received requests but couldn't process them (internal issue)
- **No audit entries during disruption**: Requests never reached the API server (connectivity issue)

## etcd Signals

Key messages:
- `"apply request took too long"` -- etcd under write pressure
- `"slow fdatasync"` -- disk I/O bottleneck
- `"waiting for ReadIndex response took too long"` -- etcd read latency
- Commit duration above 25ms or WAL fsync above 10ms thresholds

## CPU and Resource Pressure

- **CPU >95% on the disruption source node**: OVS/networking starvation
- **Azure disk IOPS at 100%**: Disk I/O saturation cascading to CPU and etcd
- **Disk queue depth >10x threshold**: Severe I/O contention

## E2E Test Correlation

Query timeline files for `E2ETest` source items overlapping the disruption window. The test name is in `locator.keys.e2e-test`.

**For multi-run analysis**: Cross-reference tests active during disruption across runs. Tests appearing in 3+ runs during disruption are especially interesting -- they may trigger resource pressure that causes disruption.

Tests that *fail* during disruption are usually *victims*. Tests that *pass* but consistently appear during disruption across runs are more likely to be contributing to resource pressure.

## Node Shutdown Sequencing

When disruption coincides with node events, check:
- Did the poller go `readyz=false` as expected during node shutdown?
- Were endpoint slices updated accordingly?
- Did the test framework watcher see the endpoint removed and stop disruption polling?

## Endpoint Slice Updates

Check audit logs for `endpointslices` resource modification events during disruption windows. Verify that readiness changes triggered appropriate endpoint updates.

## Cross-Run Comparison (Multiple Runs)

### Pattern Detection
- **Same backends at similar relative times**: Likely product bug or test sequencing issue
- **Same backends at different times**: Infrastructure-sensitive but product-related
- **Different backends across runs**: Infrastructure/environment-specific
- **ci-cluster-network-liveness disrupted**: Those runs have unreliable disruption data. Still include them but note the caveat. Non-disruption signals (etcd, CPU, alerts) remain valid
- **Cache backends consistently disrupted**: Systemic etcd or networking issue
- **Non-cache backends consistently disrupted**: Component-specific problem

### Alignment and Correlation
- Compare which backends are disrupted in each run
- Identify consistently disrupted backends (systemic) vs intermittent ones
- Check if etcd leader changes correlate with cache-backend disruption across runs
- Check if mass disruption consistently correlates with high CPU or node pressure

## Deep-Dive Artifact Paths

Only download these if timeline data analysis is insufficient:

```bash
# Audit logs
gcloud storage cp -r "gs://test-platform-results/{bucket-path}/artifacts/{target}/gather-extra/artifacts/audit_logs/" ...

# etcd pod logs
gcloud storage cp -r "gs://test-platform-results/{bucket-path}/artifacts/{target}/gather-extra/artifacts/pods/openshift-etcd/" ...
```

## Deep Links

### Run-Level
- **Prow**: `https://prow.ci.openshift.org/view/gs/test-platform-results/logs/{job_name}/{build_id}`
- **Sippy Intervals**: `https://sippy.dptools.openshift.org/sippy-ng/job_runs/{build_id}/{job_name}/intervals`

### GCS Artifact
- Base: `https://gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/test-platform-results/logs/{job_name}/{build_id}/artifacts/`
- Timeline: `{base}{target}/openshift-e2e-test/artifacts/junit/e2e-timelines_spyglass_{timestamp}.json`
- Audit logs: `{base}{target}/gather-extra/artifacts/audit_logs/`
- etcd pods: `{base}{target}/gather-extra/artifacts/pods/openshift-etcd/`
- Journal logs: `{base}{target}/gather-extra/artifacts/journal_logs/`
- Must-gather: `{base}{target}/gather-extra/artifacts/must-gather/`

Use inline reference-style links when citing evidence (link to the specific artifact, not a separate "Links" section).

## PromQL Queries (Manual Investigation)

For cases requiring live cluster metrics (not available in artifacts):

```promql
-- Top CPU consumers across all nodes
topk(25, sum by (namespace) (rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])))

-- CPU on a specific node
topk(25, sum by (namespace) (rate(container_cpu_usage_seconds_total{container!="",pod!="",node="<node-name>"}[5m])))

-- E2E test CPU on a specific node
topk(10, sum by (namespace) (rate(container_cpu_usage_seconds_total{container!="",pod!="",node="<node-name>",namespace=~"^e2e-.*"}[5m])))
```

## Disruption Parser

Use the included `parse_disruption.py` script for automated extraction and classification:

```bash
python3 plugins/ci/skills/analyze-disruption/parse_disruption.py \
  .work/disruption-analysis/{date}/{build_id}/logs/e2e-timelines_spyglass_*.json \
  --backends {backend_filter} \
  --window 60 \
  --format text
```

The script automatically:
- Extracts all disruption events (Error/Warning level)
- Classifies each backend (cache, non-cache, canary, cloud)
- Detects which phase each disruption occurred in (upgrade vs conformance)
- Detects source-node fan-out patterns
- Extracts concurrent events within the disruption window
- Summarizes OVS vswitchd stalls, CPU pressure, Azure disk metrics, etcd pressure
- Assesses network-liveness status (clean, minor, degraded, unreliable)

Use `--format json` for structured data for further analysis.
