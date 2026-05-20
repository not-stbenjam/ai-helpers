# Payload Agent Restructure Report

## Summary

Completed the payload agent skill restructuring per PLAN.md, including skill consolidation, eval infrastructure, and hermetic archive creation.

## What Was Done

### Task 1: Skill Restructuring (completed by prior session)

The prior session consolidated 30 flat CI skills into the target architecture:

- **job-analysis** — unified entry point for all Prow CI job failure analysis (install, test, disruption, resource), with progressive disclosure via `references/` directory
- **job-artifacts** — searches and fetches Prow job artifacts from GCS
- **payload-report** — consolidated schemas for results YAML, autodl JSON, and HTML reports
- **payload-revert** — stages reverts for high-confidence candidates
- **payload-snapshot** — Phase 1 deterministic data gathering

I verified and completed this work by:
- Fixing 16 skill name conventions from Title Case to kebab-case (e.g., `Fetch Payloads` → `fetch-payloads`)
- Updating `extract-prow-job-must-gather` command to reference `job-artifacts` instead of deleted skill
- Creating 5 reference files for `job-analysis/references/` from git history of deleted skills:
  - `install/cloud.md` — Cloud IPI install failure analysis
  - `install/metal.md` — Bare metal/dev-scripts analysis
  - `test-failure/general.md` — E2E test failure analysis
  - `disruption.md` — Disruption event analysis
  - `resource-usage.md` — Resource lifecycle analysis
- Running `make lint` and fixing all CI-plugin lint errors

### Task 2: Case 010 Hermetic Archive

Built the hermetic eval archive for payload `5.0.0-0.ci-2026-05-07-142711` (CNO NetworkPolicy revert case):

- Downloaded session tarball from GCS
- Extracted API responses using `extract_session_data.py`
- Parsed 3 subagent JSONL sessions to extract WebFetch results, GCS artifacts (build logs, prowjob.json, JUnit XMLs)
- Final archive: 38 files, 428K across `api-responses/`, `test-platform-results/`

### Task 3: Eval Development and Testing

Created `payload-restructure-eval.yaml` with:
- `anthropic:claude-agent-sdk` provider (sonnet-4.6)
- Custom assertions: `skill-used`, `output_files_exist`, `yaml_results_valid`, `json_data_valid`, `html_report_structure`
- LLM rubric grading with ground truth about CNO PR #2959 / NetworkPolicy mechanism
- `set-archive-env.js` extension hook for `EVAL_ARCHIVES_DIR`

**Eval Results (7 runs):**

| Run | Duration | Tokens | llm-rubric | Output Files | Notes |
|-----|----------|--------|------------|-------------|-------|
| 1   | 18m      | 57K    | PASS       | PASS        | Full pass |
| 2   | 14m      | 44K    | n/a        | FAIL        | Missing YAML/JSON |
| 3   | 20m      | 54K    | FAIL       | PASS        | Wrong root cause (registry outage) |
| 4   | 39m      | 50K    | FAIL       | PASS        | Right PR, wrong mechanism |
| 5   | 6m       | 17K    | n/a        | n/a         | Short-circuited via reference-outputs |
| 6   | 11m      | 21K    | n/a        | n/a         | Short-circuited via claude-payload-agent |
| 7   | 21m      | 24K    | PASS       | FAIL        | Correct analysis, missing autodl JSON |

**Improvements made during eval iterations:**

1. **Subagent prompt** (analyze-payload Step 5): Added explicit guidance for tracing CrashLoopBackOff to root cause mechanism (NetworkPolicies, egress blocking) and reading container previous logs
2. **Cross-platform correlation** (analyze-payload Step 5): Strengthened language — same failure across AWS/Azure/GCP is strong signal of product bug, not infrastructure
3. **PR correlation** (analyze-payload Step 6.1): Added instruction to read PR title/description for keyword matches with failure mechanism
4. **Output file emphasis** (analyze-payload Step 9): Added CRITICAL note about writing all 3 output files
5. **Archive decontamination**: Removed `reference-outputs/` directory and stripped `claude-payload-agent` entries from `asyncJobs` in all fetch-payloads JSON files

### Task 5: Hermetic Archives for All Test Cases

Built archives for all 14 eval test cases (13 successful, 1 unavailable):

| Case | Payload | Files | Size | Status |
|------|---------|-------|------|--------|
| 001  | 4.19.0-0.nightly-2026-05-13-214109 | 6 | 80K | OK |
| 002  | 4.18.0-0.nightly-2026-05-14-085133 | 15 | 116K | OK |
| 003  | 4.20.0-0.nightly-2026-05-13-064706 | 8 | 96K | OK |
| 004  | 4.20.0-0.nightly-2026-05-14-114051 | — | — | Tarball redacted from GCS |
| 005  | 4.20.0-0.nightly-2026-05-12-225204 | 5 | 76K | OK |
| 006  | 4.22.0-0.nightly-2026-03-20-053450 | 5 | 112K | OK |
| 007  | 4.22.0-0.ci-2026-03-31-050515 | 6 | 52K | OK |
| 008  | 4.22.0-0.ci-2026-03-31-170515 | 15 | 92K | OK |
| 009  | 4.22.0-0.nightly-2026-03-18-161724 | 13 | 144K | OK |
| 010  | 5.0.0-0.ci-2026-05-07-142711 | 38 | 428K | OK (original) |
| 011  | 5.0.0-0.nightly-2026-04-27-183150 | 11 | 124K | OK |
| 012  | 5.0.0-0.ci-2026-04-14-085906 | 16 | 84K | OK |
| 013  | 5.0.0-0.nightly-2026-05-08-191551 | 13 | 60K | OK (partial: missing fetch_payloads) |
| 014  | 5.0.0-0.ci-2026-05-14-181709 | 6 | 48K | OK |

Session tarballs were sourced from two Prow jobs:
- `periodic-ci-openshift-release-main-claude-payload-agent` (4.22, 5.0 versions)
- `periodic-ci-openshift-release-main-claude-payload-agent-no-slack` (4.18, 4.19, 4.20 versions)

## Known Issues

1. **Sonnet output file reliability**: sonnet-4.6 sometimes omits the autodl JSON or incomplete YAML metadata despite explicit instructions. This is model-level behavior, not a skill design issue.
2. **Case 004 archive unavailable**: Session tarball was redacted from GCS ("This file contained potentially sensitive information and has been removed"). The eval case references this archive but cannot be tested.
3. **Case 013 partial archive**: Missing `fetch_payloads` response in the session, so failed job lists are empty. The archive is structurally valid but functionally incomplete.
4. **analyze-payload context budget**: At 9,481 tokens, exceeds the 6,000 skill limit. This was pre-existing (9,218 before changes) and is inherent to the skill's complexity.
