# Install Failures -- Cloud Platforms

Cloud IPI (Installer-Provisioned Infrastructure) installation analysis for AWS, GCP, Azure, and vSphere platforms.

## Job Name Conventions

Job names encode critical environment details:

| Pattern in Name | Meaning |
|-----------------|---------|
| `upgrade-from-stable-4.X` | Minor upgrade job: installs 4.X first, then upgrades to target version |
| `upgrade` (no `upgrade-from-stable`) | Micro upgrade: installs earlier payload in same minor stream, then upgrades |
| `fips` | FIPS mode enabled -- watch for crypto library, TLS/SSL, cert validation errors |
| `ipv6` or `dualstack` | IPv6 or dual-stack networking; most IPv6 jobs are disconnected with local mirror registry |
| `single-node` | All workloads on one node; prone to resource exhaustion |
| `techpreview` | Additional feature gates enabled; bootstrap failures may be in TechPreview-gated code paths |
| `aws`, `gcp`, `azure` | Cloud platform |
| `ovn` | OVN-Kubernetes networking (standard) |

For upgrade jobs: if installation fails, the upgrade never happens. Installation failures in upgrade jobs are still installation failures.

## JUnit Failure Stages

The `junit_install.xml` file contains a test case `install should succeed: <stage>` that classifies the failure:

| Failure Stage | What It Means | Where to Look |
|---------------|---------------|---------------|
| `configuration` | Install-config.yaml validation failed | Installer log only; extremely rare |
| `infrastructure` | Cloud resource creation failed before bootstrap | Installer log for cloud API errors (quota, rate limits, outages, permissions) |
| `cluster bootstrap` | Bootstrap node failed to bring up temporary control plane | Log bundle: bootkube.log, etcd.log, kube-apiserver.log, serial console |
| `cluster creation` | Cluster operators failed to deploy/stabilize | gather-must-gather operator logs (if must-gather.tar exists) |
| `cluster operator stability` | Operators stuck in unstable state (available=False, progressing=True, degraded=True) | gather-must-gather operator conditions |
| `other` | Unknown failure mode | Full log analysis required |

The `install-status.txt` file contains only the installer exit code. Always prefer `junit_install.xml` for determining the failure stage.

## Symptom Labels

The CI system may attach symptom labels as JSON artifacts under `artifacts/job_labels/`. These are machine-detected environmental observations (not root causes) that provide context. Parse any JSON files found there and include them as investigative context.

## GCS Artifact Paths

### Locating Installer Logs
```bash
# Find all installer logs (exclude deprovision logs -- they're from cluster teardown)
gcloud storage ls -r gs://test-platform-results/{bucket-path}/artifacts/ 2>&1 \
  | grep -E "\.openshift_install.*\.log$" | grep -v "deprovision"
```

### Locating Log Bundle
```bash
# Log bundles are .tar files (NOT .tar.gz) starting with log-bundle-
gcloud storage ls -r gs://test-platform-results/{bucket-path}/artifacts/ 2>&1 \
  | grep -E "log-bundle.*\.tar$"
```
Prefer non-deprovision log bundles. Deprovision bundles capture state after teardown, not during installation.

### Locating JUnit
```bash
gcloud storage ls -r gs://test-platform-results/{bucket-path}/artifacts/ 2>&1 | grep "junit_install.xml"
```

## Log Bundle Structure

```
log-bundle-{timestamp}/
  bootstrap/journals/
    bootkube.log          # Bootkube service that starts initial control plane
    kubelet.log           # Kubelet service logs
    crio.log              # Container runtime logs
    journal.log.gz        # Complete system journal (gzipped)
  bootstrap/network/
    ip-addr.txt           # IP addresses
    ip-route.txt          # Routing table
    hostname.txt          # Hostname
  serial/
    {cluster}-bootstrap-serial.log    # Bootstrap node console
    {cluster}-master-N-serial.log     # Master node consoles
  clusterapi/
    *.yaml                # Kubernetes resource definitions
    etcd.log              # etcd logs
    kube-apiserver.log    # API server logs
  failed-units.txt        # Failed systemd units
  gather.log              # Log bundle collection process
```

## Installer Log Format

```
time="2026-02-26T10:00:00Z" level=<level> msg="<message>"
```

Levels: `info`, `warning`, `error`, `fatal`.

## Analysis Strategy: Work Backwards

OpenShift installations exhibit eventual consistency behavior:
- Components report transient errors while waiting for dependencies
- Early errors often resolve themselves and are NOT the root cause
- Example: Ingress operator errors while waiting for networking, which errors while waiting for other components

**Always start from the END of the installer log and work backwards:**

1. Find the **last** `level=error` or `level=fatal` messages
2. Find the last "Still waiting for..." or "Cluster operators X, Y, Z are not available" messages
3. Track backwards to find when the failing component first started having issues
4. Ignore early errors unless they persist to the end

## Failure-Specific Analysis

### Bootstrap Failures (`cluster bootstrap`)

Bootstrap failures are varied and complex. Thoroughly examine the log bundle:

1. Read `bootstrap/journals/bootkube.log` -- identify every process that started, crashed, or errored with timestamps
2. For crashed processes (non-zero exit, ContainerDied): read stderr/stdout, check exit codes, kernel messages, resource utilization
3. Cross-reference with `clusterapi/kube-apiserver.log`, `clusterapi/etcd.log`, `bootstrap/journals/kubelet.log`
4. Check `serial/{cluster}-bootstrap-serial.log` for kernel panics, ignition failures, disk errors
5. Check `failed-units.txt` for failed systemd units

### Infrastructure Failures (`infrastructure`)

Focus on installer log (failure happens before bootstrap, so log bundle may not exist):
- Cloud quota exceeded: `QuotaExceeded`, `LimitExceeded`
- Rate limiting: `RequestLimitExceeded`, `Throttling`
- Authentication/permission errors
- Infrastructure provisioning varies by version:
  - Newer versions use **Cluster API (CAPI)**: look for Machine/MachineSet errors
  - Older versions use **Terraform**: look for terraform state/apply errors

### Cluster Creation Failures (`cluster creation`)

Cluster bootstrapped but operators failed to deploy:
- Check for `must-gather*.tar` in the gather-must-gather step directory
- If NO .tar file exists: must-gather collection failed (cluster too unstable) -- do NOT suggest downloading it
- If must-gather exists: check operator logs, degraded cluster operators, resource conflicts

### Cluster Operator Stability Failures (`cluster operator stability`)

Operators stuck in unstable state:
- Check operators with `available=False`, `progressing=True`, or `degraded=True`
- Review operator logs in gather-must-gather (if .tar exists)
- Look at time-series of operator status changes

## Common Error Patterns

| Symptom | Likely Cause | What to Check |
|---------|-------------|---------------|
| `context deadline exceeded` / `timeout` | Component waited too long for dependency | What component timed out; check its dependencies |
| `bootstrap etcd not starting` | etcd formation failure | `clusterapi/etcd.log`, `bootkube.log` |
| `API server not responding` | kube-apiserver startup failure | `clusterapi/kube-apiserver.log` |
| `Masters not joining` | Network or ignition issue | Master serial console logs |
| `Operators degraded` | Post-bootstrap deployment issue | Operator-specific logs in must-gather |
| `QuotaExceeded` / `LimitExceeded` | Cloud quota hit | Installer log cloud API errors |

## Installation Stages (Chronological)

1. **Pre-installation**: Validate install-config.yaml, credential checks, image resolution
2. **Infrastructure Creation**: Create cloud resources (VMs, networks, storage)
3. **Bootstrap**: Bootstrap node boots with temporary control plane, etcd starts
4. **Master Node Bootstrap**: Masters boot, join bootstrap etcd, form permanent control plane
5. **Bootstrap Complete**: Bootstrap no longer needed, control plane transferred to masters
6. **Cluster Operator Initialization**: Core operators start deploying
7. **Cluster Operator Stabilization**: Operators reach stable state (available=True, progressing=False, degraded=False)
8. **Install Complete**: All operators stable, cluster functional
