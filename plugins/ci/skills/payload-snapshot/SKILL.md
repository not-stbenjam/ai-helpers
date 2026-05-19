---
name: Payload Snapshot
description: Deterministic Phase 1 data gathering for payload analysis — fetches all required payload context to .work/<tag>/
---

# Payload Snapshot

This skill deterministically gathers all required data for payload analysis into a structured snapshot directory (`.work/<tag>/`), enabling repeatable and cheaper evaluation of payload regressions.

It consolidates data-fetching operations that were previously scattered across the payload-analysis skill, making them cacheable and testable in isolation.

## When to Use This Skill

Use this skill when you need to:
- Gather all data required for payload analysis before running analysis
- Cache payload data for repeated analysis runs
- Provide deterministic inputs to downstream analysis
- Avoid refetching data between Phase 1 and Phase 2 operations

## Inputs

- `payload_tag`: The full payload tag (e.g., `4.22.0-0.nightly-2026-02-25-152806`)
- `snapshot_dir`: Directory to write snapshot data (default: `.work/<tag>/`)
- `skip_existing`: If true, skip re-fetching data if snapshot already exists (default: false)

## Output

A complete snapshot directory at `.work/<tag>/` containing:

```
.work/<tag>/
├── payload-history.json          # Full payload history with phase and timing
├── failing-jobs.json             # All failing blocking jobs with details
├── new-prs/
│   ├── {originating-tag}.json    # PRs first landing in each originating payload
│   ├── {originating-tag}.json
│   └── ...
├── sippy-test-rates.json         # Pass rates for failing tests (from Sippy)
├── regressions.json              # Regression details from internal tracking
├── changelog.json                # Payload changelog (what changed in this payload)
├── previous-analyses/
│   ├── {previous-tag}.json       # Previous Claude analyses (if any)
│   └── ...
└── manifest.json                 # Index of all snapshot contents
```

## Implementation Steps

### Step 1: Fetch Payload History

Fetch the payload history from the release controller for the stream/architecture of the target payload.

**Output**: `.work/<tag>/payload-history.json`

```json
{
  "payloads": [
    {
      "tag": "4.22.0-0.nightly-2026-02-25-152806",
      "phase": "Rejected",
      "releaseTime": "2026-02-25T15:28:06Z",
      "url": "https://amd64.ocp.releases.ci.openshift.org/..."
    }
  ]
}
```

**Purpose**: Determine rejection streak, identify originating payloads for failures.

### Step 2: Build Failure Streaks and Identify Originating Payloads

Analyze the payload history to:
1. Count consecutive rejections leading up to the target payload
2. For each job name, identify the earliest payload where that job first started failing

**Output**: Included in `.work/<tag>/payload-history.json` with enriched fields:

```json
{
  "rejection_streak": 5,
  "total_payloads_in_stream": 42,
  "failing_job_origin_map": {
    "periodic-ci-...-e2e-aws-ovn": "4.22.0-0.nightly-2026-02-20-150000",
    "periodic-ci-...-e2e-gcp-ovn": "4.22.0-0.nightly-2026-02-23-080000"
  }
}
```

### Step 3: Fetch New PRs for Each Originating Payload

For each unique originating payload tag, fetch the list of new PRs that landed in that payload.

**Output**: `.work/<tag>/new-prs/{originating-tag}.json`

```json
{
  "originating_tag": "4.22.0-0.nightly-2026-02-20-150000",
  "new_prs": [
    {
      "number": 2037,
      "url": "https://github.com/openshift/cno/pull/2037",
      "title": "Fix OVN gateway mode selection",
      "component": "cluster-network-operator",
      "author": "author-name"
    }
  ]
}
```

**Purpose**: Identify candidate reverts — PRs that landed before the failure originated.

### Step 4: Fetch Sippy Test Pass Rates

For each failing test identified in the payload, fetch historical pass rates from Sippy to assess test stability.

**Output**: `.work/<tag>/sippy-test-rates.json`

```json
{
  "passing_tests": [
    {
      "name": "openshift-e2e-test-pod-to-pod-with-local-pv",
      "pass_rate_30d": 95.2,
      "pass_rate_7d": 92.1
    }
  ]
}
```

**Purpose**: Distinguish regression-induced failures from chronically flaky tests.

### Step 5: Fetch Regression Details

Fetch regression tracking data from internal sources (e.g., regression database, previous triage notes).

**Output**: `.work/<tag>/regressions.json`

```json
{
  "regressions": [
    {
      "name": "OVN gateway mode regression",
      "status": "open",
      "tickets": ["TRT-1234"],
      "related_payloads": ["4.22.0-0.nightly-2026-02-20-150000"],
      "components": ["cluster-network-operator"]
    }
  ]
}
```

**Purpose**: Track previously identified regressions and their resolution status.

### Step 6: Fetch Changelog

Fetch the diff/changelog showing what changed between this payload and the previous one.

**Output**: `.work/<tag>/changelog.json`

```json
{
  "previous_payload": "4.22.0-0.nightly-2026-02-25-151000",
  "commits": [
    {
      "hash": "abc123def456",
      "repo": "openshift/cno",
      "message": "Fix OVN gateway mode selection",
      "author": "author-name"
    }
  ]
}
```

**Purpose**: Correlate new PRs with code changes to strengthen candidate assessment.

### Step 7: Fetch Previous Claude Analyses

Search for and fetch any previous Claude analyses of this payload or related payloads.

**Output**: `.work/<tag>/previous-analyses/`

```
previous-analyses/
├── {tag}.json    # Full analysis results from previous run
└── ...
```

**Purpose**: Avoid re-analyzing if previous analysis is still valid; provide continuity.

### Step 8: Write Manifest

Create a manifest file listing all snapshot contents with timestamps and checksums.

**Output**: `.work/<tag>/manifest.json`

```json
{
  "tag": "4.22.0-0.nightly-2026-02-25-152806",
  "created_at": "2026-02-26T10:30:00Z",
  "created_by": "payload-snapshot skill",
  "files": {
    "payload-history.json": {
      "size": 45230,
      "sha256": "abc123...",
      "fetched_at": "2026-02-26T10:29:50Z"
    },
    "new-prs/4.22.0-0.nightly-2026-02-20-150000.json": {
      "size": 12450,
      "sha256": "def456...",
      "fetched_at": "2026-02-26T10:30:05Z"
    }
  },
  "summary": {
    "rejection_streak": 5,
    "failing_jobs_count": 4,
    "candidate_prs_count": 12,
    "originating_payloads": 2
  }
}
```

**Purpose**: Document snapshot provenance and summary stats for verification.

## Caching and Idempotency

- If `.work/<tag>/manifest.json` already exists and `skip_existing` is true, skip all fetches and report cached snapshot
- If any individual fetch fails, record the error and continue with remaining fetches
- Return a summary of what was fetched and what failed

## Error Handling

- If release controller is unreachable, stop and inform the user
- If Sippy API is unavailable, log warning but continue with other fetches
- If previous analyses cannot be found, continue (they are optional)
- Return summary of all errors at the end

## See Also

- Related Skill: `payload-analysis` — consumes this snapshot for analysis
- Related Command: `/ci:payload-snapshot` — entry point for creating a snapshot
