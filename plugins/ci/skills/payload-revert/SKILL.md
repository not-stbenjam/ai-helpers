---
name: payload-revert
description: Consolidated workflow for staging reverts, experimenting with candidates, and creating revert PRs with JIRA integration and CI override commands
---

# Payload Revert

This skill consolidates three related workflows into one:
1. **Stage reverts** (high-confidence candidates) — Create JIRA bugs, open revert PRs, trigger payload jobs
2. **Experiment** (medium-confidence candidates) — Phase 1: Open draft reverts and trigger jobs; Phase 2: Collect results
3. **Create revert PR** — Git revert workflow with Revertomatic template and CI override commands

## When to Use This Skill

Use this skill to:
- **Stage reverts** for high-confidence candidates (confidence >= 85)
- **Experiment** with medium-confidence candidates (confidence 60-85)
- **Create a revert PR** manually (following OpenShift quick-revert policy)

## Prerequisites

1. **GitHub CLI (gh)**: Installed and authenticated
2. **JIRA MCP** (for staging reverts): Configured for creating TRT issues
3. **Git**: Installed and configured
4. **Repository Access**: User must have push access to their fork of each target repository
5. **Related Skills**:
   - `payload-report` — for reading/writing results YAML, autodl JSON, and HTML reports
   - `fetch-jira-issue` — for looking up context when creating revert PRs
   - `trigger-payload-job` — for triggering payload validation jobs

---

# Stage Reverts Workflow (High-Confidence)

Use this workflow to stage reverts for candidates with confidence score >= 85.

## Overview

For each candidate, execute in sequence:
1. Check JIRA for existing bug (idempotency)
2. Create TRT JIRA bug (if needed)
3. Open revert PR (idempotency check)
4. Trigger payload validation jobs
5. Update results YAML and reports

## Step 1: Check Jira MCP Availability

Before launching subagents, verify the Jira MCP server is working by attempting a lightweight call (e.g., JQL search or user profile fetch).

If the call fails (tool not found, connection error, authentication error), stop and inform the user:
1. **Fix and retry**: "Fix your Jira MCP configuration and tell me when it's working. I'll pick up where I left off."
2. **Continue without Jira**: "Continue without creating Jira issues. I'll open the revert PRs and trigger payload jobs, and give you the details to create Jira issues yourself afterward."

Default to option 2 if running autonomously. If the user chooses option 1, re-run the check when they say it's ready.

## Step 2: Launch Subagents

For each qualifying revert candidate, launch a parallel subagent. Each subagent executes Steps 3–5 in order.

## Step 3: Create TRT JIRA Bug (with idempotency check)

If Jira MCP was unavailable in Step 1 and the user chose to continue without it, skip Jira creation and proceed to Step 4. After all subagents complete, print the Jira issue details for each candidate so the user can create them manually.

**Preflight**: Before creating a new issue, search for an existing TRT bug for this PR using Jira JQL search.

If a matching issue is found, reuse its key and URL — skip creation and proceed to Step 4.

**Create** (only if no existing issue found): Use the Jira MCP create issue tool with:
- project_key: "TRT"
- issue_type: "Bug"
- summary: A concise description of the problem (symptom, not solution)
- description: Jira wiki markup with payload regression details, evidence, and action
- labels: ["trt-incident", "ai-generated-jira"]

Record the created (or reused) JIRA key and URL.

## Step 4: Open Revert PR (with idempotency check)

**Preflight**: Check whether a revert PR already exists using gh pr list.

If an open or draft revert PR is found, reuse its URL — skip creation and proceed to Step 5.

**Create** (only if no existing revert PR found): Use the revert PR creation workflow.

Record the revert PR URL (created or reused).

## Step 5: Trigger Payload Jobs

Use the `trigger-payload-job` skill to trigger payload validation jobs on the revert PR.

Record the payload_test_url and job prow URLs.

## Step 6: Update Results YAML and Reports

Each subagent uses the `payload-report` skill to update results YAML, HTML report, and autodl JSON with revert details.

---

# Experiment Workflow (Medium-Confidence)

Use this workflow to experimentally test candidates with confidence score 60-85.

## Overview

Two-phase workflow:
- **Phase 1**: Open draft revert PRs and trigger payload validation jobs
- **Phase 2**: Collect and analyze results; promote confirmed causes to staging

## Phase 1: Dispatch Experiments

### Step 1: Launch Subagents

For each qualifying candidate, launch a parallel subagent.

### Step 2: Create Draft Revert PR (with idempotency check)

**Preflight**: Check whether a draft revert PR already exists.

If found, reuse it — skip creation and proceed to Step 3.

**Create**: Use the revert PR creation workflow with --draft flag.

Record the draft revert PR URL.

### Step 3: Trigger Payload Jobs

Use the trigger-payload-job skill with the draft revert PR URL.

Record the payload_test_url and job prow URLs.

### Step 4: Update Results YAML (Phase 1)

Use the payload-report skill to append an action with type: "experiment" and status: "pending".

## Phase 2: Collect Results

### Preflight: Detect Resume Scenario

Scan the results YAML. If any candidate has an action with type: "experiment" and status: "pending", Phase 2 processing is available.

### Step 1: Poll Payload Jobs

For each pending experiment, poll the job status using trigger-payload-job skill. Wait for all jobs to complete.

### Step 2: Analyze Results

For each candidate, determine the outcome:
- **PASS** (confirmed cause): All triggered jobs passed
- **FAIL** (innocent): One or more jobs still failed with the revert
- **INCONCLUSIVE** (mixed results): Some jobs passed, some failed

### Step 3: Update Results YAML (Phase 2)

Update each pending action's status, revert_pr_state, and result_summary.

### Step 4: Update Reports

Update the HTML report and autodl JSON with final experiment results.

---

# Create Revert PR Workflow (Git Revert + Revertomatic Template)

Use this workflow to create a revert PR following the OpenShift quick-revert policy.

## Optional Parameters

- **--draft**: Create the revert PR as a draft. Used by the experimental revert workflow.
- **--context**: When the caller passes context directly, skip the JIRA lookup. The provided context string is used in the PR body.
- **--no-prompt**: Do not prompt the user for input. Used by autonomous workflows.

## Implementation Steps

### Step 1: Extract PR Information

Use gh CLI to fetch PR details and validate the PR is merged.

### Step 2: Identify the Upstream Repository

Parse the PR URL to determine owner and repository.

### Step 3: Ensure User Has a Fork

Check if fork exists; create one if not.

### Step 4: Clone and Set Up Repository

Clone the upstream repo with proper remotes:
- upstream: canonical repo
- fork: user's fork (for pushing revert branch)

### Step 5: Gather Context (if not provided via --context)

If --context was provided: Use the provided context string and proceed to Step 6.

Otherwise: Use fetch-jira-issue skill to look up JIRA ticket (if provided) and extract context. Fallback to interactive prompts if JIRA lookup fails.

### Step 6: Detect Commit Message Convention

Check recent commits to determine if the repository uses the UPSTREAM: <tag>: convention.

If convention is detected, the revert must follow the same format.

### Step 7: Create Revert Branch and Perform Revert

Create a revert branch and perform git revert -m1 to revert the merge commit.

If UPSTREAM convention was detected, amend the commit message to include the prefix.

#### Handling Merge Conflicts

**Strategy A: Resolve simple/obvious conflicts** (generated files, one-line changes, etc.)
- Examine, resolve, stage, and continue the revert
- Amend the commit message to note the conflict resolution

**Strategy B: Revert dependent commits** (if later commits depend on the reverted changes)
- Identify dependent commits and revert them first (reverse chronological order)
- Document what was reverted in the final commit message

After conflict resolution, push to the fork.

### Step 8: Create Revert PR with Revertomatic Template

Create the revert PR (with --draft flag if specified) using the Revertomatic template format in the PR body.

### Step 9: Generate CI Override Commands

List all failing status contexts and determine which need /override commands.

Filter out fast quality gates (unit, lint, images, verify, tide, etc.) — do NOT override these.

For remaining statuses, generate /override commands with appropriate reasons.

### Step 10: Return Revert Details

Return the revert PR URL, CI override commands, and instructions for the author.

---

## Error Handling

- If JIRA MCP is unavailable, Step 1 handles it. If JIRA creation fails for other reasons, continue with the revert PR and note the error.
- If the revert PR fails (e.g., merge conflicts), record the error and skip payload job triggering for that candidate.
- If payload job triggering fails, record the error but keep the JIRA and revert PR.
- Do not let one failed candidate block processing of others.

## See Also

- Related Skill: `payload-report` — schemas for results YAML, autodl JSON, and HTML reports
- Related Skill: `fetch-jira-issue` — looks up JIRA context for revert PRs
- Related Skill: `trigger-payload-job` — triggers payload validation jobs
- Related Command: `/ci:payload-revert` — stages reverts for high-confidence candidates
- Related Command: `/ci:payload-experiment` — experimentally tests medium-confidence candidates
