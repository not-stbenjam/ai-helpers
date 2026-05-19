---
name: job-artifacts
description: Search, list, and fetch Prow CI job artifacts from GCS; extract and process must-gather archives
---

# Job Artifacts

This skill provides a unified interface for working with Prow CI job artifacts stored in Google Cloud Storage (GCS). It combines artifact search/listing/fetch operations with must-gather archive extraction and processing.

This skill consolidates two separate skills: prow-job-artifact-search and prow-job-extract-must-gather.

## When to Use This Skill

Use this skill when you need to:
- Browse the artifact directory tree of a Prow job run
- Search for specific files within a job's artifacts
- Fetch the contents of a specific artifact file
- Extract and process must-gather archives
- Discover what artifacts are available before running deeper analysis

## Prerequisites

1. **gcloud CLI Installation**
   - Check if installed: `which gcloud`
   - Installation guide: https://cloud.google.com/sdk/docs/install

2. **gcloud Authentication** (Optional)
   - The `test-platform-results` bucket is publicly accessible
   - No authentication required for read access

3. **Python 3** (3.6 or later)
   - Check: `which python3`

## Script Location

```
plugins/ci/skills/job-artifacts/prow_job_artifact_search.py
plugins/ci/skills/job-artifacts/extract_archives.py
plugins/ci/skills/job-artifacts/generate_html_report.py
```

## Operations

### list — List directory contents

List files and subdirectories at a given path within the job's artifact tree.

```bash
python3 plugins/ci/skills/job-artifacts/prow_job_artifact_search.py \
  <prow-url> list [subpath]
```

**Arguments:**
- `prow-url` (required): The Prow job URL
- `subpath` (optional): Subdirectory path relative to the job root

**Output:**
```json
{
  "success": true,
  "path": "gs://test-platform-results/logs/<job>/<id>/",
  "count": 5,
  "entries": [...]
}
```

### search — Search for files matching a glob pattern

Recursively search for files matching a glob pattern under a given path.

```bash
python3 plugins/ci/skills/job-artifacts/prow_job_artifact_search.py \
  <prow-url> search <pattern> [subpath]
```

**Arguments:**
- `prow-url` (required): The Prow job URL
- `pattern` (required): Glob pattern to match (supports `**` and `*`)
- `subpath` (optional): Subdirectory to search within

**Examples:**
```bash
# Find all interval JSON files
python3 .../prow_job_artifact_search.py <url> search "**/*intervals*.json"

# Find all junit files
python3 .../prow_job_artifact_search.py <url> search "**/junit*.xml"

# Find must-gather archives
python3 .../prow_job_artifact_search.py <url> search "**/must-gather*"
```

**Output:**
```json
{
  "success": true,
  "pattern": "gs://...**/*intervals*.json",
  "count": 3,
  "matches": [...]
}
```

### fetch — Fetch a specific file's contents

Download and return the contents of a specific file.

```bash
python3 plugins/ci/skills/job-artifacts/prow_job_artifact_search.py \
  <prow-url> fetch <filepath> [--max-bytes N]
```

**Arguments:**
- `prow-url` (required): The Prow job URL
- `filepath` (required): Path to the file relative to the job root
- `--max-bytes` (optional): Maximum bytes to read (default: 524288 = 512KB)

**Output:**
```json
{
  "success": true,
  "path": "gs://...",
  "size_bytes": 45230,
  "truncated": false,
  "content": "... file contents ..."
}
```

### extract-must-gather — Extract and process must-gather archives

Extract must-gather archives and generate an interactive HTML file browser.

```bash
python3 plugins/ci/skills/job-artifacts/extract_archives.py \
  <prow-url> [output-dir]
```

**Arguments:**
- `prow-url` (required): The Prow job URL
- `output-dir` (optional): Directory to extract archives to (default: current directory)

**Output:**
- Extracts all must-gather archives found in the job
- Generates interactive HTML file browser at `must-gather-{tag}-browser.html`
- Supports nested archive extraction and multi-select filtering

**Features:**
- Automatic nested archive detection and extraction
- Interactive regex pattern matching for filtering files
- Directory tree visualization
- Large file size indicators

### generate-html-report — Generate interactive HTML report from extracted archives

Generate an HTML file browser report from extracted must-gather content.

```bash
python3 plugins/ci/skills/job-artifacts/generate_html_report.py \
  <archive-path> [output-file]
```

**Arguments:**
- `archive-path` (required): Path to extracted must-gather directory
- `output-file` (optional): Output HTML filename

**Output:**
- Interactive HTML report with:
  - Directory tree navigation
  - Filename search and regex filtering
  - Multi-select file display
  - Syntax highlighting for JSON, YAML, logs

## Common Artifact Paths

| Path | Description |
|------|-------------|
| `build-log.txt` | Top-level build log |
| `artifacts/{target}/` | All artifacts for the test step |
| `artifacts/{target}/openshift-e2e-test/` | E2E test output |
| `artifacts/{target}/openshift-e2e-test/build-log.txt` | E2E test console log |
| `artifacts/{target}/openshift-e2e-test/artifacts/e2e-timelines_spyglass_*.json` | Timeline/interval data |
| `artifacts/{target}/gather-extra/artifacts/oc_cmds/` | Cluster state snapshots |
| `artifacts/{target}/gather-extra/artifacts/pods/` | Pod logs from all namespaces |
| `artifacts/{target}/gather-extra/artifacts/audit_logs/` | API server audit logs |
| `artifacts/{target}/gather-extra/artifacts/journal_logs/` | Node journal logs (systemd) |
| `artifacts/{target}/gather-must-gather/artifacts/` | Must-gather archives |
| `prowjob.json` | Job metadata (payload tag, timing, etc.) |

## URL Formats

The script accepts both Prow UI and gcsweb URLs:
- `https://prow.ci.openshift.org/view/gs/test-platform-results/logs/<job>/<build_id>`
- `https://gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/test-platform-results/logs/<job>/<build_id>`

## Error Handling

- **No matches found**: Returns success with empty matches array
- **gcloud not installed**: Returns error with installation link
- **Invalid path or 404**: Returns error with path details
- **Large files**: Use --max-bytes to limit download size (default 512KB)

## Notes

- The `test-platform-results` bucket is publicly accessible
- No authentication required for read access
- For large files, use --max-bytes to limit download
- All output is JSON on stdout
- The --no-user-output-enabled flag suppresses progress bars

## See Also

- Related Skill: `job-analysis` — uses this skill to fetch artifacts for analysis
- Related Command: `/ci:analyze-prow-job-artifacts` — entry point for artifact exploration
