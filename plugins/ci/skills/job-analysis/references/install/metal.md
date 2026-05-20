# Install Failures -- Bare Metal (dev-scripts)

Bare metal IPI installation analysis for jobs using dev-scripts, Metal3, and Ironic.

## Metal Installation Architecture

Metal IPI jobs use three layers:

1. **dev-scripts** (https://github.com/openshift-metal3/dev-scripts): Framework for setting up and installing OpenShift on bare metal
2. **Metal3**: Kubernetes-native interface to Ironic
3. **Ironic**: Bare metal provisioning service (manages node registration, power, imaging)

Failures can occur at any layer, and analysis must check all of them.

## Network Architecture (IPv6/Disconnected Jobs)

**"Disconnected" refers to the cluster nodes, NOT the hypervisor.**

### Hypervisor (dev-scripts host)
- **HAS** full internet access
- Downloads packages, container images, dependencies from public internet
- Runs dev-scripts Ansible playbooks
- Hosts a local mirror registry to serve the cluster

### Cluster VMs/Nodes
- Run in a **private IPv6-only network** (when IP_STACK=v6)
- **NO** direct internet access
- Pull container images from the hypervisor's local mirror registry only

### Common Misconception
- WRONG: "The hypervisor cannot access the internet, so downloads fail"
- CORRECT: "The hypervisor has internet access. If downloads fail, the remote service/URL is likely down or the resource was removed"

### Implications
- **Dev-scripts failures (steps 01-05)**: External download failures mean the remote service/URL is down, not a network restriction
- **Installation failures (step 06+)**: If cluster nodes can't pull images, check the local mirror registry on the hypervisor
- **HTTP 403/404 during dev-scripts**: Usually the resource was removed upstream, not a network issue

## OFCIR Host Acquisition

Before installation starts, the job acquires a bare metal host from OFCIR (OpenShift For Cluster Image Repository).

### Artifacts
- **Build log**: `{target}/ofcir-acquire/build-log.txt` -- JSON with pool, provider, host details
- **JUnit**: `{target}/ofcir-acquire/artifacts/junit_metal_setup.xml` -- test `[sig-metal] should get working host from infra provider`

### Key Fields from Build Log
- `pool`: OFCIR pool name (e.g., "cipool-ironic-cluster-el9", "cipool-ibmcloud")
- `provider`: Infrastructure provider (e.g., "ironic", "equinix", "aws", "ibmcloud")
- `name`: Host name allocated

If OFCIR acquisition fails, installation never starts. Report pool and provider info and stop analysis.

## Dev-Scripts Logs

### Location
```
{target}/baremetalds-devscripts-setup/artifacts/root/dev-scripts/logs/
```

### Structure
Numbered log files showing each setup step sequentially (01-requirements, 02-host-config, ..., 06-create-cluster).

**Dev-scripts invokes the installer**, so `.openshift_install*.log` files will also be present in devscripts directories.

### Key Distinction
- Failure in steps 01-05: Problem is in the setup process (host config, Ironic setup, installer build)
- Failure in step 06 / installer logs: Problem is in cluster installation

### Key Errors to Search For
- Host configuration failures (networking, DNS, storage setup)
- Ironic/Metal3 setup issues (BMC connectivity, provisioning network, node registration)
- Installer build failures
- Install-config validation errors

## libvirt Console Logs

### Location
```
{target}/baremetalds-devscripts-gather/artifacts/libvirt-logs.tar
```

Contains VM/node console logs (e.g., `{cluster}-bootstrap_console.log`, `{cluster}-master-N_console.log`).

### What to Look For
Console logs show the complete boot sequence as if watching a physical console:
- **Kernel boot failures/panics**: "panic", "kernel", "oops"
- **Ignition failures**: "ignition", "config fetch failed", "Ignition failed"
- **Network configuration issues**: "dhcp", "network unreachable", "DNS", "timeout"
- **Disk mounting failures**: "mount", "disk", "filesystem"
- **Service startup failures**: systemd errors, service failures

## Ironic Logs (from log-bundle)

**Two sets of Ironic logs exist in different locations -- check the RIGHT ones based on what failed.**

### Bootstrap Ironic (master provisioning)
```
bootstrap/journals/ironic.log
bootstrap/journals/metal3-baremetal-operator.log
```

### Control-Plane Ironic (worker provisioning)
```
control-plane/{node-ip}/containers/metal3-ironic-*.log
control-plane/{node-ip}/containers/metal3-baremetal-operator-*.log
```

### Which Logs to Check
- Masters failed to provision: check `bootstrap/journals/ironic.log`
- Workers failed to provision: check `control-plane/{ip}/containers/metal3-ironic-*.log`
- Unsure: check all

### Key Ironic Errors
- BMC (IPMI, Redfish) communication errors
- Node registration failures
- Power state query failures
- Provisioning state transitions stuck
- SSL errors, BMC connection failures

### Node UUID Mapping
Ironic logs use node UUIDs (e.g., `b7fa5b83-91d0-46ee-acd2-e4b33e9ac983`). Map UUIDs to BareMetalHost names using installer logs or must-gather to identify which specific node failed.

## sosreport

### Location
```
{target}/baremetalds-devscripts-gather/artifacts/sosreport-*.tar.xz
```

### Purpose
Hypervisor system diagnostics -- only needed for hypervisor-level issues:
- `var/log/messages` -- hypervisor system log
- `sos_commands/` -- diagnostic command output
- `etc/libvirt/` -- libvirt configuration

### What to Look For
- Libvirt errors
- Network configuration problems on hypervisor
- Resource constraints (CPU, memory, disk)

## Squid Proxy Logs

### Location
```
{target}/baremetalds-devscripts-gather/artifacts/squid-logs.tar
```

### Purpose
The squid proxy runs on the hypervisor for **INBOUND** access (CI -> cluster), NOT for outbound access (cluster -> registry).

### What to Look For
- Failed connections from CI to the cluster
- HTTP errors or blocked requests
- Network routing issues between CI and cluster

## Common Metal Failure Patterns

| Issue | Symptoms | Where to Look |
|-------|----------|---------------|
| Dev-scripts host config | Early failure before cluster creation | Dev-scripts logs (host config step) |
| Ironic/Metal3 setup | Provisioning failures, BMC errors | Dev-scripts logs (Ironic setup) |
| BMC communication | BareMetalHost stuck registering, power state failures | Ironic logs in log-bundle, BareMetalHost status |
| Node boot failure | VMs/nodes won't boot | Console logs (kernel, boot sequence) |
| Ignition failure | Nodes boot but don't provision | Console logs (Ignition messages) |
| Network config | DHCP failures, DNS issues | Console logs, dev-scripts host config |
| CI access issues | Tests can't connect to cluster | Squid logs (proxy logs for CI -> cluster) |
| Hypervisor issues | Resource constraints, libvirt errors | sosreport (system logs, libvirt config) |

## Analysis Order

1. **Check OFCIR acquisition first** -- if it failed, installation never started
2. **Check dev-scripts logs** -- they show setup and installation (dev-scripts invokes the installer)
3. **Check installer logs in devscripts** -- look for `.openshift_install*.log` files
4. **Check Ironic logs** -- for BMC/provisioning issues (use correct set based on master vs worker)
5. **Check console logs** -- for boot sequence, ignition, kernel issues
6. **Check sosreport** -- only for hypervisor-level issues
7. **Check squid logs** -- for CI access issues to the cluster
