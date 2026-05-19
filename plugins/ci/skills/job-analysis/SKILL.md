---
name: job-analysis
description: Unified entry point for analyzing all Prow CI job failure types with progressive disclosure of job-type-specific knowledge via references
---

# Job Analysis

This skill provides a single entry point for analyzing Prow CI job failures across all types and platforms. It automatically detects the job type, loads domain-specific knowledge from `references/`, and performs analysis using structured troubleshooting patterns.

This skill consolidates five separate analysis skills into one unified interface with progressive disclosure.

## When to Use This Skill

Use this skill when you need to:
- Analyze why a Prow CI job failed
- Understand installation failures, test failures, or cluster resource exhaustion
- Diagnose failures on different platforms (cloud, bare metal, SNO, hyperShift)
- Generate structured analysis results with root cause recommendations

## Supported Job Types

1. **Install failures** (cloud and bare metal)
   - Cloud IPI (AWS, GCP, Azure, vSphere)
   - Bare metal via dev-scripts
   - Hypershift guest clusters

2. **Test failures** (e2e tests, suite tests, operator tests)
   - Single-cluster tests
   - Hypershift (dual-cluster) tests

3. **Disruption analysis** (timeline/interval data from Sippy)
   - Cache disruption events
   - Non-cache disruption events

4. **Resource usage analysis** (audit logs, pod logs, memory/CPU)
   - Cluster resource lifecycles
   - Pod lifecycle and log analysis

## Prerequisites

1. **Prow job URL**: The job URL from prow.ci.openshift.org or gcsweb
2. **gcloud CLI**: Installed for accessing GCS artifacts (test-platform-results bucket)
3. **Python 3**: 3.6+ for artifact parsing scripts
4. **Related Skills**:
   - `job-artifacts` — for searching and fetching Prow job artifacts
   - `fetch-prowjob-json` — for fetching job metadata

## Implementation Steps

### Step 1: Fetch Job Metadata

Use the `fetch-prowjob-json` skill to fetch prowjob.json metadata from the Prow job:

```json
{
  "status": {
    "state": "failure",
    "startTime": "2026-02-26T10:00:00Z",
    "completionTime": "2026-02-26T11:30:00Z"
  },
  "spec": {
    "job": "periodic-ci-openshift-release-master-nightly-4.22-e2e-aws-ovn",
    "cluster": "build01"
  }
}
```

Extract:
- Job name
- Job state (success/failure)
- Start and completion times
- Job cluster
- Test parameters (if applicable)

### Step 2: Detect Job Type and Platform

Based on the job name and artifact structure, detect:

1. **Is this an install failure?**
   - Check for `install should succeed` or `cluster has minimum resource requirements` in JUnit XML
   - Look for installer logs and bootstrap logs

2. **Is this a bare metal job?**
   - Check job name for patterns like `metal`, `ipi`, `vsphere`
   - Presence of dev-scripts logs in artifacts

3. **Is this a test failure?**
   - Check for JUnit XML with test cases
   - E2E test suite logs

4. **Is this hypershift?**
   - Check for management cluster and guest cluster artifacts
   - Presence of hostedcluster objects

5. **Is this a disruption analysis?**
   - Check for interval data or timeline data from Sippy
   - Time-series event logs

### Step 3: Load Domain-Specific Reference

Based on the detected type, load the appropriate reference file from `references/`:

- **Install (cloud)**: `references/install/cloud.md`
- **Install (bare metal)**: `references/install/metal.md`
- **Test failure**: `references/test-failure/general.md`
- **Disruption analysis**: `references/disruption.md`
- **Resource usage**: `references/resource-usage.md`

The reference provides:
- Common failure patterns for this job type
- Artifact paths and log structures
- Key error signatures to search for
- Diagnostic commands and analysis techniques
- Expected outcomes and interpretations

### Step 4: Extract Artifacts

Use the `job-artifacts` skill to search for and fetch relevant artifacts based on the job type:

**For install failures**:
- build-log.txt (top-level build log)
- Installer logs (bootstrap, wait-for-bootstrap, etc.)
- Pod logs and cluster state snapshots

**For test failures**:
- JUnit XML files (test results)
- E2E test logs and timelines
- Cluster diagnostics and must-gather

**For disruption analysis**:
- Interval data from Sippy (timeline JSON)
- Event logs and pod logs

**For resource usage**:
- Audit logs (API server requests)
- Pod logs from all namespaces
- Node journal logs

### Step 5: Perform Analysis

Using the domain-specific reference as guidance, analyze the extracted artifacts:

1. **Identify the failure mode**: What went wrong (install step, test assertion, event, resource limit)?
2. **Correlate with logs**: Find relevant log entries that explain the failure
3. **Determine root cause**: What was the immediate cause (config error, timeout, resource exhaustion, bug)?
4. **Check for patterns**: Is this a known issue? Have we seen this failure before?
5. **Generate recommendations**: What can be done to fix or mitigate this failure?

### Step 6: Return Analysis Result

Return a structured `ANALYSIS_RESULT` block with:

```
ANALYSIS_RESULT:
failure_type: "install" | "test" | "disruption" | "resource"
failure_stage: "bootstrap" | "cluster-creation" | "wait-for-openshift-install" | ...
root_cause_summary: "Brief one-sentence description of the root cause"
root_cause_details: "Longer explanation with log excerpts and context"
affected_components: ["component1", "component2", ...]
confidence: "high" | "medium" | "low"
error_signatures: ["signature1", "signature2", ...]
recommendations: ["action1", "action2", ...]
artifacts_examined: ["artifact1", "artifact2", ...]
END_ANALYSIS_RESULT
```

---

## Reference Files

### `references/install/cloud.md`

CloudPlatforms installation guide:
- Common bootstrap failures (DNS, node provisioning, network timeouts)
- Cluster creation phases (infrastructure, bootstrap, wait-for-openshift-install)
- Log patterns for etcd quorum issues, API server timeouts, kubelet problems
- Hypershift-specific installation patterns (management vs. guest cluster)

### `references/install/metal.md`

Bare metal (dev-scripts) installation guide:
- Dev-scripts initialization and Metal3 provisioning
- OFCIR (OpenShift For Cluster Image Repository) acquisition
- libvirt, Ironic, and node provisioning failures
- Common metal-specific issues (hardware, network, storage)

### `references/test-failure/general.md`

E2E and operator test failure guide:
- JUnit XML parsing and test assertion failures
- Hypershift dual-cluster analysis (management + guest)
- Must-gather extraction and cluster state diagnostics
- Common test failure patterns (timeouts, resource exhaustion, race conditions)

### `references/disruption.md`

Disruption event analysis guide:
- Timeline data interpretation from Sippy
- Backend classification (cache, non-cache, canary, cloud)
- Event source and node analysis
- Cross-run comparison patterns

### `references/resource-usage.md`

Cluster resource and lifecycle analysis:
- Audit log parsing (resource creation/deletion events)
- Pod lifecycle analysis
- Memory and CPU usage tracking
- Interactive HTML report generation with regex filtering

---

## Error Handling

- If prowjob.json fetch fails, return an error with instructions to provide the job URL
- If artifact search returns no results, note which artifacts were searched and return a partial result
- If the job type cannot be detected, return a diagnostic message with detected signals
- If analysis fails, return the partial analysis with errors noted

## See Also

- Related Skill: `job-artifacts` — searches and fetches Prow job artifacts
- Related Skill: `fetch-prowjob-json` — fetches job metadata
- Related Command: `/ci:analyze-prow-job` — entry point for analyzing a specific job
