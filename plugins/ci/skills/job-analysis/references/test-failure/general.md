# Test Failure Analysis

Analysis of failed Prow CI tests including JUnit parsing, build-log analysis, must-gather diagnostics, and HyperShift dual-cluster patterns.

## JUnit XML Discovery

Search for JUnit files under the artifacts directory using `{JOB_NAME}` (from `.spec.job` in prowjob.json), NOT `{target}`. On PR jobs these values differ.

```bash
gcloud storage ls "gs://test-platform-results/{bucket-path}/artifacts/{JOB_NAME}/**/junit*.xml" 2>/dev/null
```

### Parsing Failed Test Cases

Collect every `<testcase>` element where:
- A `<failure>` or `<error>` child element is present, OR
- The attribute `status="failed"`

For each, record: `step_name` (from `classname` or `name`), `failure_message` (from `<failure>` or `<error>` text), and `junit_file` (source XML path).

## Multi-Step CI Workflow Analysis

CI workflows (HyperShift, bare-metal, OADP) have multi-step pipelines. When no specific test name is given, analyze all failed CI steps.

### Step Phase Classification

The `junit_operator.xml` contains phase-level testcases:
- `"Run multi-stage test pre phase"` -- setup/installation steps
- `"Run multi-stage test test phase"` -- functional test steps
- `"Run multi-stage test post phase"` -- gather/cleanup steps

**Routing by phase:**
- **`pre` phase**: Installation/setup failures -- delegate to install failure analysis. Must-gather is NOT attempted (no live apiserver).
- **`test` phase**: Functional test failures -- full analysis with must-gather.
- **`post` phase**: Gather/cleanup failures -- informational only, usually a consequence of earlier failures.

If phase-level testcases are absent, fall back to `ci-operator-step-graph.json` for step ordering and naming conventions.

### Step-Specific Logs

```bash
# Download step-specific build log
gcloud storage cp \
  "gs://test-platform-results/{bucket-path}/artifacts/{JOB_NAME}/{step_name}/build-log.txt" \
  .work/{build_id}/logs/{step_name}-build-log.txt --no-user-output-enabled
```

If not found, fall back to scanning the top-level `build-log.txt` for lines mentioning `{step_name}` with surrounding context.

## Aggregated Jobs

Aggregated jobs run the same job in parallel (typically 10 times) with statistical analysis. Detect by `aggregated-` prefix in job name or an `aggregator` step in prowjob.json.

### Failure Modes

1. **Statistically significant test failure**: Test fails frequently enough across runs to be flagged as a regression. Investigate the test itself.

2. **Insufficient completed runs**: Not enough runs completed for statistical testing. Manifests as mass test failures across unrelated tests. Root cause: whatever prevented runs from completing (infra issues, install failures, product bugs). Investigate underlying job runs that did not complete.

3. **Non-deterministic test presence**: Test only ran in a subset of completed jobs. Failure message: "Passed X times, failed Y times, skipped Z times: we require at least N attempts...". This is a regression -- someone introduced a test that doesn't produce results deterministically.

### Finding Underlying Job Run URLs

Download the aggregated JUnit XML:
```
gs://test-platform-results/{bucket-path}/artifacts/release-analysis-aggregator/openshift-release-analysis-aggregator/artifacts/release-analysis-aggregator/{job-name}/{payload-tag}/junit-aggregated.xml
```

Each `<testcase>` `<system-out>` contains YAML with `passes:`, `failures:`, `skips:` lists. Each entry has `jobrunid` (build ID) and `humanurl` (Prow URL for the run).

## Interval Files (E2E Timelines)

Search for E2E timeline artifacts:
```bash
gcloud storage ls 'gs://test-platform-results/{bucket-path}/**/e2e-timelines_spyglass_*json'
```

There may be up to two matching files. Scan for:
- **Test failure timing**: `source = "E2ETest"` with `message.annotations.status = "Failed"` -- note `from` and `to` timestamps
- **Related cluster events**: Intervals overlapping the failed test's timeframe with `level = "Error"` or `level = "Warning"` and `source = "OperatorState"`

## Symptom Labels

Check `artifacts/job_labels/` for JSON symptom files (exclude `label-summary.html`). Symptoms are machine-detected environmental observations, NOT root causes. Use as investigative context.

## Must-Gather Detection

### HyperShift Patterns

**Pattern 1 -- Unified Archive** (`dump-management-cluster`):
- Single archive with both management and hosted cluster data
- Management data at `logs/artifacts/output/`
- Hosted cluster data at `logs/artifacts/output/hostedcluster-{name}/`
- Used by: `hypershift-aws-e2e-external` workflow

**Pattern 2 -- Dual Archives** (`gather-must-gather` + `dump`):
- Standard must-gather for management cluster
- Separate hypershift-dump for additional data (may or may not have hosted cluster)
- Used by: `hypershift-kubevirt-e2e-aws` workflow

**Pattern 3 -- Standard Only** (`gather-must-gather`):
- Standard OpenShift must-gather only, no HyperShift-specific dump

### Detection Logic

```bash
# Pattern 1: Unified archive
gcloud storage ls "gs://.../$JOB_NAME/dump-management-cluster/artifacts/artifacts.tar*"

# Pattern 2/3: Standard must-gather
gcloud storage ls "gs://.../$JOB_NAME/gather-must-gather/artifacts/must-gather.tar"

# Pattern 2: HyperShift dump (multiple possible locations)
gcloud storage ls "gs://.../$JOB_NAME/**/artifacts/hypershift-dump.tar"
gcloud storage ls "gs://.../$JOB_NAME/**/artifacts/**/hostedcluster.tar"
```

Check for `hostedcluster-*` directory in archives to determine if hosted cluster data is present.

## Must-Gather Analysis

Run targeted cluster diagnostics focused on test-relevant issues:

```bash
# Core diagnostics
python3 $SCRIPTS_DIR/analyze_clusteroperators.py "$MUST_GATHER_PATH"
python3 $SCRIPTS_DIR/analyze_pods.py "$MUST_GATHER_PATH" --problems-only
python3 $SCRIPTS_DIR/analyze_nodes.py "$MUST_GATHER_PATH" --problems-only
python3 $SCRIPTS_DIR/analyze_events.py "$MUST_GATHER_PATH" --type Warning --count 50

# Conditional: network diagnostics (if job name matches network|ovn|sdn|connectivity|route|ingress|egress)
python3 $SCRIPTS_DIR/analyze_network.py "$MUST_GATHER_PATH"

# Conditional: etcd diagnostics (if job name matches etcd|apiserver|control-plane|kube-apiserver)
python3 $SCRIPTS_DIR/analyze_etcd.py "$MUST_GATHER_PATH"
```

For HyperShift, run diagnostics separately for management and hosted clusters.

## Crash-Looping Container Investigation

**Be tenacious.** Never stop at "containers are crash-looping" -- find out *why*.

Sources to pursue:
- **Must-gather**: Pod YAMLs with `containerStatuses` (`exitCode`, `lastState.terminated.reason`, `restartCount`), container logs (current and previous), events, operator conditions
- **Gather-extra / gather-audit logs**: Additional diagnostics from extra gather steps
- **Step-level build logs**: Error output, stack traces, timeout messages
- **Interval file events**: Operator state transitions and warnings

Always trace upstream through the dependency chain to the originating error.

## Root Cause Correlation

### Temporal Correlation
- Use interval file timestamps to identify when the test was running
- Cluster operator conditions, pod events, and warning events within +/-5 minutes of test failure are most relevant

### Component Correlation
- **Namespace**: Test namespace -> check for pod failures in that namespace
- **Test type**: Network tests -> network operator, CNI pods; Storage tests -> storage operator, CSI pods; API tests -> kube-apiserver pods
- **Stack trace keywords**: "connection refused" -> pod restarts, network issues; "timeout" -> node pressure, resource constraints; "not found" -> resource deletion events

### HyperShift Cross-Cluster Correlation
- **Management cluster issues** affect: HostedControlPlane pods (kube-apiserver, etcd in `clusters-{namespace}`), HyperShift operator, management nodes
- **Hosted cluster issues** affect: Worker node pods, cluster operators, application workloads
- Cross-cluster: management node pressure -> hosted control plane unavailable; HyperShift operator error -> HostedControlPlane rollout failed

## CI Step Script Errors

If the error is a scripting issue in a CI step (unbound variable, syntax error, missing command, bad exit code from a shell script) rather than a product bug, check for recent commits to that step's script in the `openshift/release` repository. Identifying the responsible PR early informs the rest of the analysis.
