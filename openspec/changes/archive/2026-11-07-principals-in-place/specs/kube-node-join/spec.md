# Spec Delta: kube-node-join

## MODIFIED Requirements

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
