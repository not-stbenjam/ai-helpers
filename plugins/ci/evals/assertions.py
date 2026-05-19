"""
Custom promptfoo assertions for CI eval skills.

These assertions inspect files the agent wrote during execution by reading
the Write/Edit tool calls from the SDK provider's metadata.
"""

import json
import yaml
import os
import re


def _get_written_files(context):
    """Extract files written by the agent from provider response metadata."""
    response = context.get("providerResponse", {})
    metadata = response.get("metadata", {})
    tool_calls = metadata.get("toolCalls", [])

    files = {}
    for tc in tool_calls:
        if tc.get("name") == "Write":
            inp = tc.get("input", {})
            path = inp.get("file_path", "")
            content = inp.get("content", "")
            if path:
                files[os.path.basename(path)] = content
                files[path] = content
    return files


def output_files_exist(output, context):
    """Verify all three payload analysis output files are produced."""
    files = _get_written_files(context)
    basenames = list(files.keys())

    html = [k for k in basenames if k.endswith("-summary.html")]
    yaml_f = [k for k in basenames if k.startswith("payload-results-") and k.endswith(".yaml")]
    json_f = [k for k in basenames if k.endswith("-autodl.json")]

    missing = []
    if not html:
        missing.append("HTML report (*-summary.html)")
    if not yaml_f:
        missing.append("payload results YAML (payload-results-*.yaml)")
    if not json_f:
        missing.append("autodl JSON (*-autodl.json)")

    if missing:
        return {"pass": False, "score": 0, "reason": f"Missing: {', '.join(missing)}"}
    return {"pass": True, "score": 1, "reason": f"All 3 files found: {html[0]}, {yaml_f[0]}, {json_f[0]}"}


def yaml_results_valid(output, context):
    """Verify the payload results YAML has the required schema."""
    files = _get_written_files(context)
    yaml_files = {k: v for k, v in files.items()
                  if os.path.basename(k).startswith("payload-results-") and k.endswith(".yaml")}

    if not yaml_files:
        return {"pass": False, "score": 0, "reason": "No payload results YAML found"}

    content = list(yaml_files.values())[0]
    try:
        data = yaml.safe_load(content)
    except Exception as e:
        return {"pass": False, "score": 0, "reason": f"Invalid YAML: {e}"}

    if not isinstance(data, dict):
        return {"pass": False, "score": 0, "reason": "YAML root is not a dict"}

    meta = data.get("metadata", {})
    required_meta = ["payload_tag", "version", "stream", "architecture"]
    missing = [f for f in required_meta if f not in meta]
    if missing:
        return {"pass": False, "score": 0, "reason": f"Missing metadata: {', '.join(missing)}"}

    if "failing_jobs" not in data:
        return {"pass": False, "score": 0, "reason": "Missing failing_jobs array"}
    if "candidates" not in data:
        return {"pass": False, "score": 0, "reason": "Missing candidates array"}

    jobs = data.get("failing_jobs", [])
    cands = data.get("candidates", [])
    return {"pass": True, "score": 1, "reason": f"Valid: {len(jobs)} failing jobs, {len(cands)} candidates"}


def json_data_valid(output, context):
    """Verify the autodl JSON is valid with required fields."""
    files = _get_written_files(context)
    json_files = {k: v for k, v in files.items() if k.endswith("-autodl.json")}

    if not json_files:
        return {"pass": False, "score": 0, "reason": "No autodl JSON found"}

    content = list(json_files.values())[0]
    try:
        data = json.loads(content)
    except Exception as e:
        return {"pass": False, "score": 0, "reason": f"Invalid JSON: {e}"}

    if isinstance(data, dict) and "rows" in data:
        data = data["rows"]
    if not isinstance(data, list):
        return {"pass": False, "score": 0, "reason": "JSON root is not an array (or dict with 'rows' key)"}
    if len(data) == 0:
        return {"pass": False, "score": 0, "reason": "JSON array is empty"}

    required = ["payload_tag", "job_name", "failure_type", "root_cause_summary"]
    row = data[0]
    missing = [f for f in required if f not in row]
    if missing:
        return {"pass": False, "score": 0, "reason": f"Missing fields: {', '.join(missing)}"}

    return {"pass": True, "score": 1, "reason": f"Valid JSON: {len(data)} rows, all required fields present"}


def html_report_structure(output, context):
    """Verify the HTML report contains required sections."""
    files = _get_written_files(context)
    html_files = {k: v for k, v in files.items() if k.endswith("-summary.html")}

    if not html_files:
        return {"pass": False, "score": 0, "reason": "No HTML report found"}

    html = list(html_files.values())[0]
    checks = {
        "executive summary": "executive" in html.lower() or "summary" in html.lower(),
        "blocking jobs table": "<table" in html,
        "revert verdict": "revert" in html.lower() or "verdict" in html.lower(),
        "embedded CSS": "<style>" in html,
        "collapsible details": "<details" in html,
    }
    failed = [k for k, v in checks.items() if not v]
    if failed:
        return {"pass": False, "score": 0, "reason": f"Missing: {', '.join(failed)}"}
    return {"pass": True, "score": 1, "reason": f"All {len(checks)} structural checks passed"}


def install_output_files_exist(output, context):
    """Verify install analysis output files are produced."""
    files = _get_written_files(context)

    report = [k for k in files if k.endswith("/report.txt") and "prow-job-analyze-install-failure" in k]
    installer_summary = [k for k in files if k.endswith("/installer-summary.txt")]
    bundle_summary = [k for k in files if k.endswith("/log-bundle-summary.txt")]
    analysis_files = [k for k in files if "prow-job-analyze-install-failure" in k and "/analysis/" in k]

    if not report and not analysis_files:
        if "failure stage" in output.lower() or "root cause" in output.lower():
            return {"pass": True, "score": 1, "reason": "Analysis found in conversation (no separate files)"}
        return {"pass": False, "score": 0, "reason": "Missing analysis report"}

    found = []
    if report:
        found.append(f"report: {os.path.basename(report[0])}")
    if installer_summary:
        found.append(f"installer-summary: {os.path.basename(installer_summary[0])}")
    if bundle_summary:
        found.append(f"bundle-summary: {os.path.basename(bundle_summary[0])}")
    return {"pass": True, "score": 1, "reason": f"Output files found: {'; '.join(found)}"}
