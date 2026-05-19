---
name: Payload Report
description: Unified schema and operations for payload results YAML, autodl JSON, and HTML reports — required for all payload triage actions
---

# Payload Report

This skill defines the consolidated schemas and operations for the three output files produced during payload analysis and triage:

1. **Payload Results YAML** (`payload-results-{tag}.yaml`) — Stateful tracking of payload analysis, failing jobs, candidates, and actions
2. **Autodl JSON** (`payload-analysis-{tag}-autodl.json`) — Flattened denormalized table for database ingestion
3. **HTML Report** (`payload-analysis-{tag}-summary.html`) — Interactive human-readable summary with tables and links

All skills in the payload triage pipeline must use this skill when reading, writing, or updating any of these files.

## When to Use This Skill

Use this skill whenever you need to:
- **Create** results and reports (during `payload-analysis`)
- **Read** candidates and their actions (during `payload-revert`, `payload-experiment`)
- **Append an action** to a candidate (during revert or experiment operations)
- **Update an action's status** (during Phase 2 experiment collection)
- **Update the HTML report** with links to staged reverts and experiment results
- **Generate or update** the autodl JSON file

## File Locations

All files are written to and read from the current working directory:

- `payload-results-{tag}.yaml` — Results tracking file
- `payload-analysis-{sanitized_tag}-autodl.json` — Autodl JSON for database ingestion
- `payload-analysis-{sanitized_tag}-summary.html` — HTML report

Where `{tag}` is the full payload tag and `{sanitized_tag}` has colons and slashes replaced by hyphens.

---

# Payload Results YAML Schema

## File Structure

```yaml
metadata:
  payload_tag: "4.22.0-0.nightly-2026-02-25-152806"
  version: "4.22"
  stream: "nightly"
  architecture: "amd64"
  release_controller_url: "https://amd64.ocp.releases.ci.openshift.org/..."
  analyzed_at: "2026-02-26T10:30:00Z"
  force_accept_recommended: false

failing_jobs:
  - job_name: "periodic-ci-...-e2e-aws-ovn"
    prow_url: "https://prow.ci.openshift.org/..."
    is_aggregated: false
    underlying_job_name: ""
    failure_type: "test"
    root_cause_summary: "OVN gateway mode selection regression"
    streak_length: 5
    originating_payload_tag: "4.22.0-0.nightly-2026-02-20-150000"
    failure_pattern: "F F F F F S S"

candidates:
  - pr_url: "https://github.com/openshift/cno/pull/2037"
    pr_number: 2037
    component: "cluster-network-operator"
    title: "Fix OVN gateway mode selection"
    confidence_score: 95
    rationale: "temporal match + component match + error references code changed"
    failing_jobs:
      - "periodic-ci-...-e2e-aws-ovn"
    actions:
      - type: "revert"
        status: "staged"
        revert_pr_url: "https://github.com/openshift/cno/pull/2038"
        revert_pr_state: "open"
        result_summary: "Revert PR opened and payload jobs triggered"
        jira_key: "TRT-1234"
        jira_url: "https://redhat.atlassian.net/browse/TRT-1234"
        payload_jobs:
          - command: "/payload-job periodic-ci-...-e2e-aws-ovn"
            test_url: "https://pr-payload-tests.ci.openshift.org/runs/ci/..."
            test_prow_url: "https://prow.ci.openshift.org/view/gs/..."
```

### `metadata`

Written once by `payload-analysis`. Never modified by downstream skills.

| Field | Type | Description |
|-------|------|-------------|
| `payload_tag` | string | Full payload tag being analyzed |
| `version` | string | OCP version (e.g., `"4.22"`) |
| `stream` | string | `"nightly"` or `"ci"` |
| `architecture` | string | `"amd64"`, `"arm64"`, `"multi"`, etc. |
| `release_controller_url` | string | URL to the payload on the release controller |
| `analyzed_at` | string | ISO 8601 timestamp of when the analysis was performed |
| `force_accept_recommended` | bool | `true` when all failures are temporary infrastructure issues, no more than 2 blocking jobs failed, and no payload has been accepted in the stream for 18+ hours |

### `failing_jobs[]`

All failed blocking jobs in the payload. Written once by `payload-analysis`. Never modified by downstream skills.

| Field | Type | Description |
|-------|------|-------------|
| `job_name` | string | Full periodic job name |
| `prow_url` | string | Prow URL for the failing run |
| `is_aggregated` | bool | Whether this is an aggregated job |
| `underlying_job_name` | string | For aggregated jobs, the underlying periodic job name; `""` otherwise |
| `failure_type` | string | `"test"`, `"install"`, `"upgrade"`, or `"infra"` |
| `root_cause_summary` | string | Brief description of the failure mode |
| `streak_length` | int | Consecutive payloads this job has been failing |
| `originating_payload_tag` | string | The payload where this job first started failing in the current streak |
| `failure_pattern` | string | Pass/fail history across the lookback window, most recent first (e.g., `"F F F S F F"`) |

### `candidates[]`

Each entry represents a PR identified as a candidate cause of payload failures. Top-level candidate fields are written once by `payload-analysis` and are read-only to downstream skills. The `actions` sub-array is mutable.

| Field | Type | Description |
|-------|------|-------------|
| `pr_url` | string | GitHub PR URL |
| `pr_number` | int | PR number |
| `component` | string | OCP component name |
| `title` | string | PR title |
| `confidence_score` | int | 0-100 confidence that this PR caused the failures |
| `rationale` | string | Explanation of why this PR is a candidate |
| `failing_jobs` | array of strings | Job names from the top-level `failing_jobs[]` that this candidate is blamed for |
| `actions` | array | Actions taken on this candidate (see below) |

### `candidates[].actions[]`

Actions taken on a candidate. New entries are **appended** by downstream skills. Existing entries may be **updated in place** by revert/experiment operations.

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `"revert"` or `"experiment"` |
| `status` | string | See status values below |
| `revert_pr_url` | string | URL of the revert PR (draft or real) |
| `revert_pr_state` | string | `"draft"`, `"open"`, `"merged"`, `"closed"` |
| `result_summary` | string | Brief description of the outcome |
| `jira_key` | string | TRT JIRA key (e.g., `"TRT-1234"`), or `""` |
| `jira_url` | string | TRT JIRA URL, or `""` |
| `payload_jobs` | array | Payload validation jobs triggered (see below) |

**Status values:**

| Status | Meaning |
|--------|---------|
| `"open"` | Pre-existing revert PR found open during analysis |
| `"merged"` | Pre-existing revert PR already merged |
| `"staged"` | Revert PR and JIRA created, payload jobs triggered (used by `type: "revert"`) |
| `"pending"` | Experiment dispatched, payload jobs running, results not yet collected |
| `"passed"` | Payload jobs passed with the revert — candidate confirmed as cause |
| `"failed"` | Payload jobs still fail with the revert — candidate is innocent |
| `"inconclusive"` | Mixed or unfinished results |
| `"skipped_conflict"` | Revert has merge conflicts, skipped |
| `"deferred"` | Jobs skipped due to triggering limits, or candidate exceeded max experiment count |

### `candidates[].actions[].payload_jobs[]`

Payload validation jobs triggered against the revert PR.

| Field | Type | Description |
|-------|------|-------------|
| `command` | string | The payload command posted on the PR (e.g., `/payload-job periodic-ci-...-e2e-aws-ovn`) |
| `test_url` | string | pr-payload-tests URL for the run |
| `test_prow_url` | string | Prow URL for the resulting test run |

## YAML Operations

### Create (used by `payload-analysis`)

Write a new `payload-results-{tag}.yaml` with `metadata`, `failing_jobs`, and `candidates` populated. Candidates with no pre-existing revert start with `actions: []`. If a pre-existing revert PR is discovered, append an action with `type: "revert"` and `status: "open"` or `"merged"`.

### Read Candidates (used by `payload-revert`, `payload-experiment`)

Read the file. Filter candidates by `confidence_score` range. Exclude candidates that already have an action with `status` of `"open"` or `"merged"`. Return matching candidates with full job details from the top-level `failing_jobs[]` array.

### Append Action (used by revert/experiment operations)

For a given candidate (matched by `pr_url`), append a new entry to its `actions` array. Do not modify existing action entries.

### Update Action Status (used by Phase 2 experiment collection)

For a given candidate's action entry (matched by `pr_url` and `type`), update its `status`, `result_summary`, `revert_pr_state`, `jira_key`, `jira_url`, and `payload_jobs` fields in place.

### Resume Detection (used by `payload-experiment`)

Scan all candidates. If any candidate has an action with `type: "experiment"` and `status: "pending"`, Phase 2 processing is available. Process only pending experiments — leave others unchanged.

---

# Payload Autodl JSON Schema

## File Structure

```json
{
    "table_name": "payload_triage",
    "schema": {
        "payload_tag": "string",
        "version": "string",
        "stream": "string",
        "architecture": "string",
        "phase": "string",
        "release_controller_url": "string",
        "analyzed_at": "string",
        "rejection_streak": "int64",
        "total_blocking_jobs": "int64",
        "failed_blocking_jobs": "int64",
        "force_accept_recommended": "int64",
        "job_name": "string",
        "prow_url": "string",
        "failure_type": "string",
        "root_cause_summary": "string",
        "streak_length": "int64",
        "is_new_failure": "int64",
        "originating_payload_tag": "string",
        "candidate_pr_url": "string",
        "candidate_title": "string",
        "candidate_repo": "string",
        "candidate_confidence_score": "int64",
        "candidate_rationale": "string",
        "revert_pr_url": "string",
        "revert_pr_status": "string"
    },
    "schema_mapping": null,
    "rows": [
        {
            "payload_tag": "4.22.0-0.nightly-2026-02-25-152806",
            "version": "4.22",
            "stream": "nightly",
            "architecture": "amd64",
            "phase": "Rejected",
            "release_controller_url": "https://amd64.ocp.releases.ci.openshift.org/...",
            "analyzed_at": "2026-02-26T10:30:00Z",
            "rejection_streak": "5",
            "total_blocking_jobs": "42",
            "failed_blocking_jobs": "4",
            "force_accept_recommended": "0",
            "job_name": "periodic-ci-openshift-release-main-ci-4.22-e2e-aws-ovn",
            "prow_url": "https://prow.ci.openshift.org/view/gs/...",
            "failure_type": "test",
            "root_cause_summary": "OVN gateway mode selection regression",
            "streak_length": "5",
            "is_new_failure": "0",
            "originating_payload_tag": "4.22.0-0.nightly-2026-02-20-150000",
            "candidate_pr_url": "https://github.com/openshift/cno/pull/2037",
            "candidate_title": "Fix OVN gateway mode selection",
            "candidate_repo": "openshift/cluster-network-operator",
            "candidate_confidence_score": "95",
            "candidate_rationale": "Error references code changed by this PR",
            "revert_pr_url": "https://github.com/openshift/cno/pull/2038",
            "revert_pr_status": "open"
        }
    ],
    "chunk_size": 0,
    "expiration_days": 0,
    "partition_column": ""
}
```

## Row Cardinality Rules

| Scenario | Rows for that job |
|----------|-------------------|
| Failed job, no candidate | 1 row — candidate fields are `""` / `"0"` |
| Failed job, 1 candidate | 1 row — candidate fields populated |
| Failed job, 2+ candidates | N rows — job fields identical, candidate fields differ per candidate |
| Passed job | 0 rows — not included |

## Field Rules

1. **All row values MUST be strings** — wrap every value in double quotes (e.g., `"5"` not `5`).
2. **Empty/missing values** are empty strings (`""`). For int64 fields with no value, use `"0"`.
3. **`is_new_failure`**: `"1"` for true, `"0"` for false.
4. **`candidate_confidence_score`**: Integer 0-100, e.g. `"95"`. `"0"` when no candidate.
5. **`revert_pr_url`**: URL of the revert PR (pre-existing or created by revert operations). `""` if none.
6. **`revert_pr_status`**: `"open"`, `"merged"`, `"draft"`, `"closed"`, or `""` if no revert.
7. **`schema_mapping`** is always `null`.
8. **`chunk_size`**, **`expiration_days`**, and **`partition_column`** are always `0`, `0`, and `""`.

## Field Descriptions

### Payload-level fields (denormalized across all rows)

| Field | Type | Description |
|-------|------|-------------|
| `payload_tag` | string | Full payload tag |
| `version` | string | OCP version (e.g., `"4.22"`) |
| `stream` | string | `"nightly"` or `"ci"` |
| `architecture` | string | `"amd64"`, `"arm64"`, `"multi"`, etc. |
| `phase` | string | Payload phase: `"Rejected"`, `"Accepted"`, `"Ready"` |
| `release_controller_url` | string | URL to the payload on the release controller |
| `analyzed_at` | string | ISO 8601 timestamp of when the analysis was performed |
| `rejection_streak` | int64 | Number of consecutive rejected payloads leading up to the target |
| `total_blocking_jobs` | int64 | Total number of blocking jobs in the payload |
| `failed_blocking_jobs` | int64 | Number of failed blocking jobs |
| `force_accept_recommended` | int64 | `1` if all failures are temporary infrastructure, no more than 2 blocking jobs failed, and no payload accepted in 18+ hours; `0` otherwise |

### Job-level fields

| Field | Type | Description |
|-------|------|-------------|
| `job_name` | string | Full periodic job name |
| `prow_url` | string | Prow URL for the failing run |
| `failure_type` | string | `"test"`, `"install"`, `"upgrade"`, or `"infra"` |
| `root_cause_summary` | string | Brief description of the failure mode |
| `streak_length` | int64 | Consecutive payloads this job has been failing |
| `is_new_failure` | int64 | `1` if the job first started failing in the target payload, `0` otherwise |
| `originating_payload_tag` | string | The payload where this job first started failing in the current streak |

### Candidate-level fields

| Field | Type | Description |
|-------|------|-------------|
| `candidate_pr_url` | string | GitHub PR URL, or `""` if no candidate |
| `candidate_title` | string | PR title, or `""` |
| `candidate_repo` | string | GitHub `org/repo`, or `""` |
| `candidate_confidence_score` | int64 | 0-100 confidence score, `0` when no candidate |
| `candidate_rationale` | string | Explanation of why this PR is a candidate, or `""` |
| `revert_pr_url` | string | URL of a revert PR if one exists, or `""` |
| `revert_pr_status` | string | `"open"`, `"merged"`, `"draft"`, `"closed"`, or `""` |

## JSON Operations

### Create (used by `payload-analysis`)

Generate the full autodl JSON file with all rows populated. Each failed blocking job produces at least one row. Candidate fields are populated when a PR is correlated, otherwise they are empty strings / `"0"`.

### Update Revert Status (used by revert operations)

After staging reverts, find rows matching `candidate_pr_url` and set:
- `revert_pr_url`: URL of the revert PR (created or pre-existing)
- `revert_pr_status`: `"open"` (or `"draft"` if draft)

### Update Experiment Status (used by experiment operations)

**Phase 1 (dispatch):** After creating draft revert PRs, find rows matching `candidate_pr_url` and set:
- `revert_pr_url`: URL of the draft revert PR
- `revert_pr_status`: `"draft"`

**Phase 2 (collection):** After collecting experiment results, find rows matching `candidate_pr_url` and update:
- **PASS** (confirmed cause): `revert_pr_status`: `"open"`
- **FAIL** (innocent): `revert_pr_url`: `""`, `revert_pr_status`: `""` (draft was closed)

---

# HTML Report Schema

The HTML report (`payload-analysis-{sanitized_tag}-summary.html`) provides a human-readable summary of the payload analysis with interactive tables and links.

## Operations

### Create (used by `payload-analysis`)

Generate the HTML report with the following sections (see `analyze-payload` SKILL.md Step 7 for full requirements):

1. **Payload Summary** — Tag, version, stream, architecture, phase, rejection streak
2. **Analysis Metadata** — Timestamp, force_accept_recommended flag, total/failed job counts
3. **Failed Jobs Table** — Per-job failure info with links to Prow runs
4. **Recommended Reverts Table** — Candidates with confidence scores ≥85, with columns:
   - **Component** — from candidate.component
   - **PR** — link to candidate.pr_url with `#{pr_number}`
   - **Title** — from candidate.title
   - **Confidence** — candidate.confidence_score
   - **Failing Jobs** — comma-separated job names
   - **Rationale** — candidate.rationale
   - **Status** — `Pending` badge (status: `pending`)

5. **Per-Job Details** — For each failed job, show:
   - Job name with Prow link
   - Failure type, root cause summary, streak length
   - List of candidates blamed for this job (links to PRs)

### Update with Revert Links (used by revert/experiment operations)

After staging reverts or experiments, update the "Recommended Reverts" table to add columns for each successfully staged candidate:

- **Revert PR** — Link to the revert PR (e.g., `<a href="{revert_pr_url}">#{revert_pr_number}</a>`)
- **JIRA** — Link to the TRT issue (e.g., `<a href="{jira_url}">{jira_key}</a>`)
- **Payload Jobs** — Link to the pr-payload-tests URL (e.g., `<a href="{payload_test_url}">Payload Test</a>`)
- **Status** — Badge showing `Revert Staged` (use CSS class `badge-staged` or similar)

If the report has no "Recommended Reverts" section (all candidates scored below 85), add one before the per-job details section using the same HTML structure.

---

## See Also

- Related Skill: `payload-analysis` — creates all report files
- Related Skill: `payload-revert` — stages reverts and updates reports
- Related Skill: `payload-experiment` — experimentally tests candidates and updates reports
- Related Command: `/ci:payload-revert` — stages reverts for high-confidence candidates
- Related Command: `/ci:payload-experiment` — experimentally tests medium-confidence candidates
