# Kube Node Join

## Purpose

Define how a Kubernetes worker node obtains its own least-privilege identity and joins the cluster, decoupled from master post-processing state — so convergence is order-tolerant and no worker shares another host's admin credentials.

## Requirements

### Requirement: Worker node client certificate is per-node and IPA-signed
Each worker node SHALL request its own client certificate from the `kubernetes-ca` via the `freeipa.ansible_freeipa.ipacert` module, with subject organization `system:nodes` and common name `system:node:<hostname>`. A worker SHALL NOT reuse another host's (e.g. the master's) admin client certificate as its kubelet identity.

#### Scenario: Node cert requested with node-scoped subject
- **WHEN** a worker node runs and its client certificate does not yet exist
- **THEN** a private key and CSR are generated for that node
- **THEN** the CSR carries `O=system:nodes` and `CN=system:node:<hostname>`
- **THEN** the certificate is requested via `ipacert` with `ca=kubernetes-ca` and placed under `/etc/kubernetes/pki/`

#### Scenario: Node does not reuse master admin cert
- **WHEN** a worker node configures its kubelet credentials
- **THEN** the kubelet client certificate is the node's own per-node certificate, not the master's `kubeadm.crt`
- **THEN** no task copies the master's `admin.conf`, `kubeadm.crt`, or `kubeadm.pem` onto the worker

### Requirement: Worker node trust anchor is obtained from IPA
A worker node SHALL obtain its Kubernetes CA certificate (`/etc/kubernetes/pki/ca.crt`) directly from the FreeIPA `kubernetes-ca`, not by copying it off the master.

#### Scenario: CA fetched from IPA
- **WHEN** a worker node prepares to join
- **THEN** `/etc/kubernetes/pki/ca.crt` on the node is sourced from the `kubernetes-ca` certificate in FreeIPA
- **THEN** the node's trust anchor matches the CA that signed the API server serving certificate

### Requirement: Node join waits for API server readiness
A worker node SHALL wait until the Kubernetes API server reports healthy before configuring kubelet credentials and starting the kubelet.

#### Scenario: Join gated on healthz
- **WHEN** a worker node is ready to join but the API server is not yet reachable
- **THEN** the join step retries until `https://<api>:6443/healthz` returns 200
- **THEN** kubelet credentials are configured only after readiness is confirmed

### Requirement: Node certificate request requires the kubernetes-ca to exist
A worker node's certificate request SHALL proceed only once the `kubernetes-ca` exists in FreeIPA, so that join ordering does not depend on a fixed play sequence.

#### Scenario: Cert request gated on CA existence
- **WHEN** a worker node attempts its certificate request and no `kubernetes-ca` yet exists
- **THEN** the request waits until the `kubernetes-ca` is present before proceeding

### Requirement: Convergence is order-tolerant across master and nodes
Worker-node preparation (packages, CRI, firewall, NFS) SHALL run without depending on master post-processing; only the join step depends on API-server readiness. The converge scenario SHALL NOT require a fully-completed master play to precede the node work.

#### Scenario: Node prep independent of master post-processing
- **WHEN** the role runs across master and worker hosts in a single pass
- **THEN** worker package/CRI/firewall/NFS preparation completes without requiring the master's IPA certificate swap to have finished
- **THEN** only the join step is gated on API-server readiness

### Requirement: Worker registers with node-scoped identity
After joining, a worker node SHALL appear in the cluster authenticated as `system:node:<hostname>` in group `system:nodes`, not as an admin or master-group user.

#### Scenario: Node registered under system:node identity
- **WHEN** a worker has joined and its kubelet is running
- **THEN** the node's client certificate authenticates as `system:node:<hostname>` in group `system:nodes`
- **THEN** confirming registration uses the node's own per-node credentials, not master admin credentials

### Requirement: Join verification is independent of master post-processing
The step that confirms a worker has registered SHALL use the worker's own per-node identity (its locally-constructed `/etc/kubernetes/kubelet.conf`) and SHALL NOT depend on any master kubeconfig (e.g. `admin.conf`) having been re-pointed at the IPA CA by a later master post-processing step (`ipa-pki-swap`).

#### Scenario: Verify with node's own identity before pki-swap
- **WHEN** a worker has joined but the master's `admin.conf` has not yet been re-pointed at the IPA CA (i.e. `ipa-pki-swap` has not run)
- **THEN** confirming the node registered succeeds using the node's own `/etc/kubernetes/kubelet.conf`
- **THEN** the check does not fail with a TLS "unknown authority" error caused by a stale master trust anchor
