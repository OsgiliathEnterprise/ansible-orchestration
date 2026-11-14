# Kube Node Join

## Purpose

Define how a Kubernetes worker node obtains its own least-privilege identity and joins the cluster, decoupled from master post-processing state — so convergence is order-tolerant and no worker shares another host's admin credentials.

## Requirements

### Requirement: Worker node client certificate is per-node and IPA-signed
Each worker node SHALL obtain its own client certificate from the `kubeclusteradm` CA (CA #2) — matching how the runtime renewal script renews it — via the `freeipa.ansible_freeipa.ipacert` module, requesting principal `host/<node>` with the `kubernetesNodes` profile so the issued certificate carries subject organization `system:nodes` and the `system:node:<hostname>` kubelet identity. The node's private key and CSR SHALL be generated on the node itself, and the node SHALL self-enroll using a ticket minted on the node from its own `/etc/krb5.keytab` host principal. A worker SHALL NOT reuse another host's (e.g. the master's) admin client certificate as its kubelet identity, and the master SHALL NOT mint the node's key or CSR on the node's behalf.

#### Scenario: Node cert requested with node-scoped subject
- **WHEN** a worker node runs and its client certificate does not yet exist
- **THEN** a private key and CSR are generated on that node, for that node alone
- **THEN** the CSR carries `O=system:nodes` and the request names principal `host/<node>` with the `kubernetesNodes` profile
- **THEN** the certificate is requested via `ipacert` with `ca=kubeclusteradm` (CA #2) and placed under `/etc/kubernetes/pki/` on the node

#### Scenario: Node self-enrolls with its own identity
- **WHEN** a worker node enrolls its client certificate
- **THEN** the enrollment authenticates with a `krb_ticket` keytab ticket minted on the node from `/etc/krb5.keytab` (principal `host/<node>`) — no admin ticket is minted for this purpose on the IPA server
- **THEN** the node's private key is never copied off the node

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
A worker node SHALL wait until the Kubernetes API server reports healthy before configuring kubelet credentials and starting the kubelet. The readiness gate SHALL verify the API server's serving certificate chains to the node's own trust anchor, and the trust anchor SHALL be installed on the node from FreeIPA before the gate runs.

#### Scenario: Join gated on healthz
- **WHEN** a worker node is ready to join but the API server is not yet reachable
- **THEN** the join step retries until `https://<api>:6443/healthz` returns 200
- **THEN** kubelet credentials are configured only after readiness is confirmed

#### Scenario: Readiness gate verifies TLS trust against the node's own CA
- **WHEN** a worker node runs the API readiness gate
- **THEN** the healthz poll verifies the API server's serving certificate against the node's locally installed trust anchor
- **THEN** the gate passes only when the API is reachable and its certificate chains to that trust anchor
- **THEN** the trust anchor verified by the gate is the same CA the node commits to its kubelet configuration

#### Scenario: Trust anchor mismatch fails fast at the gate
- **WHEN** the API server serves a certificate that does not chain to the node's trust anchor (e.g. the master was re-initialized after the node's anchor was fetched)
- **THEN** the readiness gate fails with a TLS verification error at the top of the join block
- **THEN** no drop-in surgery, kubelet state reset, or kubelet restart occurs before the failure surfaces

#### Scenario: Trust anchor survives node state reset
- **WHEN** the join block resets kubeadm state after the readiness gate passes (the reset wipes `/etc/kubernetes/pki/`)
- **THEN** the trust anchor is reinstalled on the node from the verified fetch before kubelet configuration proceeds
- **AND** kubelet starts with a valid `certificate-authority` file present

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

### Requirement: Worker kubelet authenticates API-proxied requests with x509 client certificates
A worker node's kubelet configuration SHALL enable x509 client-certificate authentication
against a merged CA bundle (`/etc/kubernetes/pki/ca-bundle.crt` containing exactly the two
FreeIPA-fetched certificates, the `kubeclusteradm` CA #2 and `kubernetes-ca` CA #1, and never
the kubeadm self-signed CA), disable anonymous authentication, and authorize via
`mode: Webhook`.

#### Scenario: Bundle installed alongside the trust anchor
- **WHEN** a worker node prepares to join
- **THEN** `/etc/kubernetes/pki/ca-bundle.crt` contains exactly the `kubeclusteradm` (CA #2) and `kubernetes-ca` (CA #1) certificates fetched from FreeIPA, and no kubeadm self-signed certificate
- **THEN** the bundle is reinstalled if `kubeadm reset` wipes `/etc/kubernetes/pki/`

#### Scenario: Worker kubelet config carries the auth blocks
- **WHEN** the minimal kubelet config is written on the worker
- **THEN** it contains `authentication.anonymous.enabled: false`, `authentication.webhook.enabled: true`, `authentication.x509.clientCAFile: /etc/kubernetes/pki/ca-bundle.crt`, and `authorization.mode: Webhook`

#### Scenario: Proxied subresources reach pods on the worker
- **WHEN** the API server proxies `kubectl exec` or `kubectl logs` for a pod scheduled on the worker
- **THEN** the kubelet accepts the API server's CA #2-issued client certificate instead of answering `401 Unauthorized`
