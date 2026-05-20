# Resource Usage Analysis

Analysis of Kubernetes resource lifecycles in Prow CI job artifacts by parsing audit logs and pod logs from GCS, generating interactive HTML reports with timelines.

## Resource Specification Format

Resources are specified as a comma-delimited list in the format `[namespace:][kind/]name`:

| Example | Meaning |
|---------|---------|
| `pod/etcd-0` | Pod named etcd-0 in any namespace |
| `openshift-etcd:pod/etcd-0` | Pod in specific namespace |
| `etcd-0` | Any resource named etcd-0 (no kind filter) |
| `pod/etcd-0,configmap/cluster-config` | Multiple resources |
| `resource-name-1\|resource-name-2` | Multiple resources using regex OR |
| `e2e-test-project-api-.*` | Pattern matching with regex wildcards |

All three components (namespace, kind, name) support regex patterns.

## GCS Artifact Paths

### Target Extraction
Extract the `--target=` value from prowjob.json ci-operator args. Non-ci-operator jobs (no `--target`) cannot be analyzed.

### Audit Logs
```
gs://test-platform-results/{bucket-path}/artifacts/{target}/gather-extra/artifacts/audit_logs/
```
Contains JSONL files (one JSON object per line).

### Pod Logs
```
gs://test-platform-results/{bucket-path}/artifacts/{target}/gather-extra/artifacts/pods/
```
Contains plain text log files organized by namespace/pod.

## Audit Log Entry Format (JSONL)

Each line is a JSON object with fields:
- `verb` -- action (get, list, create, update, patch, delete, watch)
- `user.username` -- user making request
- `responseStatus.code` -- HTTP response code (integer)
- `objectRef.namespace` -- namespace (if namespaced)
- `objectRef.resource` -- lowercase plural kind (e.g., "pods", "configmaps")
- `objectRef.name` -- resource name
- `requestReceivedTimestamp` -- ISO 8601 timestamp

### Filtering and Matching
- Uses **regex matching** on `objectRef.namespace` and `objectRef.name`
- Pipe operator for multiple resources: `resource1|resource2`
- Wildcards: `e2e-test-.*` matches all resources starting with `e2e-test-`
- Plain strings use fast substring search (optimization)

### Summary Format
```
{verb} {resource}/{name} in {namespace} by {username} -> HTTP {code}
```
Example: `create pod/etcd-0 in openshift-etcd by system:serviceaccount:kube-system:deployment-controller -> HTTP 201`

### Severity Levels
- 200-299: `info`
- 400-499: `warn`
- 500-599: `error`

## Pod Log Format

Plain text, one line per entry. Common formats:

### Glog Format
```
E0910 11:43:41.153414 ...
```
- First character: severity (`E`=error, `W`=warn, `I`=info, `F`=fatal->error)
- `0910`: month/day (MMDD)
- `11:43:41.153414`: time with microseconds

### Standard Timestamp Format
```
2026-02-26T10:00:00.000000Z ...
```

Non-glog logs default to `info` level.

## Parsing Scripts

### parse_all_logs.py

Parses both audit logs and pod logs, outputs combined JSON:

```bash
python3 plugins/ci/skills/prow-job-analyze-resource/parse_all_logs.py \
  <resource_pattern> \
  <audit_logs_dir> \
  <pods_dir> \
  > all_entries.json
```

The script:
1. Finds all `.log` files in both directories
2. Parses audit logs (JSONL) and pod logs (plain text)
3. Filters matches using regex patterns
4. Combines and sorts all entries chronologically
5. Outputs status to stderr, JSON to stdout

### generate_html_report.py

Generates interactive HTML report from parsed JSON:

```bash
python3 plugins/ci/skills/prow-job-analyze-resource/generate_html_report.py \
  all_entries.json \
  "{prowjob_name}" \
  "{build_id}" \
  "{target}" \
  "{resource_pattern}" \
  "{gcsweb_url}"
```

Output: `.work/prow-job-analyze-resource/{build_id}/{first_resource_name}.html`

### HTML Report Features
- **Interactive timeline**: SVG with colored vertical lines (white/gray=info, yellow=warn, red=error), clickable to jump to entries
- **Log entries**: Timestamp, level badge, source file:line, summary, expandable full content
- **Filter controls**: By level, by resource, by time range
- **Search**: Within entries
- **Syntax highlighting**: For JSON content in audit log entries
- All CSS and JavaScript inline for portability

## Entry Structure (JSON Output)

Each entry from the parse script contains:
- `source`: "audit" or "pod"
- `filename`: Full path to source log file
- `line_number`: Line number in source file (1-indexed)
- `level`: "info", "warn", or "error"
- `timestamp`: ISO 8601 datetime (entries without timestamps sorted to end)
- `content`: Full original line/JSON
- `summary`: Formatted summary (audit: verb/resource/namespace/user/code; pod: first 200 chars)

## Namespace vs Project

In OpenShift, a `project` is essentially a `namespace` with additional metadata. Searching for a namespace name will find both namespace and project resources in audit logs.

## Resource Name Matching Tips

- User-provided names may not exactly match actual resource names (e.g., user asks for `e2e-test-project-api-p28m` but actual resource is `e2e-test-project-api-p28mx`)
- Use regex patterns like `e2e-test-project-api-p28m.*` to find partial matches
- May match multiple related resources (namespace, project, rolebindings) -- report all matches for complete lifecycle context
