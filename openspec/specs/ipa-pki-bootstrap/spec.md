# IPA PKI Bootstrap

## Purpose

After `kubeadm init`, swap the kubeadm-generated PKI with certificates signed by the FreeIPA `kubernetes-ca` sub-CA. This includes the API server certificate, front-proxy client certificate, kubelet client certificate, and service account key, ensuring all Kubernetes control plane components trust the IPA CA.

## Requirements

### Requirement: IPA PKI bootstrap runs unconditionally on masters
The IPA PKI bootstrap tasks SHALL execute on every master host without requiring a boolean toggle.

#### Scenario: IPA PKI runs on masters
- **WHEN** the role runs and the host is in `kube_masters_group`
- **THEN** IPA PKI infrastructure setup executes
- **THEN** IPA PKI certificate swap executes

### Requirement: Kubernetes CA certificate is available on master
The master SHALL have both FreeIPA CA certificates available for the two-CA model: the cluster
trust anchor CA (`kubernetes-ca`, CA #1) at `/etc/kubernetes/pki/ca.crt.new` and the client CA
(`kubeclusteradm`, CA #2) at `/etc/kubernetes/pki/ca.crt.kubeclusteradm`.

#### Scenario: CA #1 certificate is downloaded
- **WHEN** the PKI swap runs on the master
- **THEN** the `kubernetes-ca` (CA #1) CA certificate is fetched from the IPA server (delegated) and installed at `/etc/kubernetes/pki/ca.crt.new`

#### Scenario: CA #2 certificate is downloaded
- **WHEN** the PKI swap runs on the master
- **THEN** the `kubeclusteradm` (CA #2) CA certificate is fetched from the IPA server (delegated) and installed at `/etc/kubernetes/pki/ca.crt.kubeclusteradm`

### Requirement: Kubernetes CA is installed as the cluster trust anchor
The master SHALL install the `kubernetes-ca` (CA #1) certificate as the cluster trust anchor.

#### Scenario: Trust anchor is CA #1
- **WHEN** the PKI swap installs the trust anchor
- **THEN** `/etc/kubernetes/pki/ca.crt` contains the `kubernetes-ca` (CA #1) CA certificate only

### Requirement: API server serving certificate is IPA-signed
The master SHALL request and install the API server serving certificate signed by the
`kubernetes-ca` (CA #1) CA, so the cluster trust anchor validates it.

#### Scenario: Serving certificate is CA #1-signed
- **WHEN** the API server certificate is requested
- **THEN** it is issued by the `kubernetes-ca` (CA #1) CA with the `kubeAdministrators` profile and principal `HTTP/apiserver.kubernetes.osgiliath.test`

### Requirement: Front-proxy client certificate is IPA-signed
The master SHALL request and install the front-proxy client certificate signed by the
`kubeclusteradm` (CA #2) CA.

#### Scenario: Front-proxy client certificate is CA #2-signed
- **WHEN** the front-proxy client certificate is requested
- **THEN** it is issued by the `kubeclusteradm` (CA #2) CA with the `kubeAdministrators` profile and principal `host/master.osgiliath.test`

### Requirement: Kubelet client certificate is IPA-signed
The master SHALL request and install the kubelet client certificate signed by the
`kubeclusteradm` (CA #2) CA.

#### Scenario: Kubelet client certificate is CA #2-signed
- **WHEN** the kubelet client certificate is requested
- **THEN** it is issued by the `kubeclusteradm` (CA #2) CA with the `kubeAdministrators` profile and principal `host/master.osgiliath.test`

### Requirement: Admin user principal is created via native ipauser module
The `kubeclusteradm` IPA user principal SHALL be created via the `freeipa.ansible_freeipa.ipauser` Ansible module and SHALL NOT use a shell-based `ipa user-add` command. The principal SHALL be created with first name `kube`, last name `ClusterAdmin`, the configured admin email address, and the realm password.

#### Scenario: Principal is created when missing
- **WHEN** the role runs on the IPA server and the `kubeclusteradm` principal does not exist
- **THEN** the principal is created via the `freeipa.ansible_freeipa.ipauser` module with first name `kube`, last name `ClusterAdmin`, the configured admin email address, and the realm password

#### Scenario: Principal creation is idempotent
- **WHEN** the role runs on the IPA server and the `kubeclusteradm` principal already exists
- **THEN** no error is raised and the task reports that the principal is already present

#### Scenario: No shell user-add for admin principal
- **WHEN** the role runs
- **THEN** no shell-based `ipa user-add` command is executed to create the `kubeclusteradm` principal

### Requirement: Admin user certificate is IPA-signed
The admin user certificate SHALL be requested from the `kubernetes-ca` via the `freeipa.ansible_freeipa.ipacert` module instead of being locally signed with the kubeadm-generated CA key.

#### Scenario: Admin cert is IPA-signed
- **WHEN** the role runs and `kubeadm.crt` does not exist
- **THEN** a private key is generated at `{{ kube_credential_folder }}/kubeadm.pem`
- **THEN** a CSR is generated with CN `kubeClusteradm` and `O=clusterAdministrators`
- **THEN** the certificate is requested via `ipacert` module with `ca=kubernetes-ca`
- **THEN** the signed certificate is placed at `{{ kube_credential_folder }}/kubeadm.crt`

#### Scenario: Admin cert already exists
- **WHEN** the role runs and `kubeadm.crt` already exists
- **THEN** no new certificate request is performed

### Requirement: SA key is generated locally
The system SHALL generate a private key for service account token signing at `/etc/kubernetes/pki/sa.key`.

#### Scenario: SA key is generated
- **WHEN** the role runs and `sa.key` does not exist
- **THEN** an ECDSA private key is generated at `/etc/kubernetes/pki/sa.key`

### Requirement: Certificate requests use ipacert module
All certificate requests SHALL use the `freeipa.ansible_freeipa.ipacert` Ansible module and SHALL NOT use shell-based `ipa cert-request` commands.

#### Scenario: No shell cert requests
- **WHEN** the role runs
- **THEN** all certificate requests are performed via `freeipa.ansible_freeipa.ipacert` module calls
- **THEN** no `ipa cert-request` shell commands are executed

### Requirement: IPA PKI swap runs after kubeadm init
The IPA PKI certificate generation and swap tasks SHALL complete after the `kubeadm init` command has succeeded.

#### Scenario: Correct execution order
- **WHEN** the role runs
- **THEN** `kubeadm init` completes successfully with its own PKI
- **THEN** IPA PKI tasks generate certificates and swap into `/etc/kubernetes/pki/`
- **THEN** component configs are patched to trust the IPA CA
- **THEN** the API server static pod is restarted to pick up new certificates

### Requirement: API server serves traffic after PKI swap
After the static pods are restarted following the PKI certificate swap, the system SHALL verify that the API server is healthy and that its serving certificate chains to the expected trust anchor before proceeding. Readiness polling SHALL be a TLS-validated healthz check against a SAN-matching API address, anchored to the CA the API is expected to present at that point in the sequence.

#### Scenario: API server ready after swap
- **WHEN** the role runs on a master and the API server static pod has been restarted with new certificates
- **THEN** the healthz endpoint returns 200 over a TLS-validated connection anchored to the expected CA (retried until available)
- **THEN** the controller manager holds a fresh leader lease before the swap phase proceeds

#### Scenario: Old-certificate window gate validates against the merged bundle
- **WHEN** the API server is restarted after the kubeconfig and manifest edits, before the IPA-signed serving certificate exists
- **THEN** the readiness gate validates the presented serving certificate against the merged CA bundle (kubeadm + IPA)
- **THEN** the gate passes whether the API presents the old or the new serving certificate

#### Scenario: New-certificate gate asserts the transition completed
- **WHEN** the API server is restarted to pick up the IPA-signed serving certificate
- **THEN** the readiness gate validates the presented serving certificate against the IPA CA only
- **THEN** the gate passes only when the running server presents the new certificate

#### Scenario: Gate failure surfaces a diagnostic and fails the run
- **WHEN** the readiness gate observes that the API server still presents the old (kubeadm) serving certificate after the restart window elapses
- **THEN** the task reports which certificate is presented, its issuer, and the expected issuer before failing the playbook

#### Scenario: Post-swap stabilization is a single validated gate
- **WHEN** the PKI swap phase confirms the cluster is stable after kubeconfig and URL re-pointing
- **THEN** a single TLS-validated healthz check anchored to the IPA CA confirms the API is healthy and presents the IPA-CA-anchored serving certificate

### Requirement: Node join validates the presented CA before joining
A node SHALL NOT execute `kubeadm join` until it has verified that the master's kube-apiserver serves a certificate chain rooted at the expected trust anchor. The check SHALL be a TLS-validated connection from the node to the API server address, anchored to the CA bundle the node is expected to trust after the PKI swap (the IPA CA). Join-time verification SHALL use the same join-time hash computation as the join command so that a mismatch between the presented chain and the join configuration fails before any cluster state is written.

#### Scenario: Node joins only against an IPA-anchored API
- **WHEN** a node reaches the join phase after the master's PKI swap has completed
- **THEN** the node validates a TLS connection to the API server anchored to the IPA CA before running `kubeadm join`
- **THEN** the join proceeds only when the presented serving certificate chains to the IPA CA

#### Scenario: Join is refused when the API still presents the old chain
- **WHEN** a node reaches the join phase but the master's API server still serves the pre-swap (kubeadm) serving certificate
- **THEN** the TLS validation anchored to the IPA CA fails and `kubeadm join` is not executed

### Requirement: Admin cert is verifiable as IPA-signed
A testinfra test SHALL verify that the admin certificate at `/home/kubecreds/kubeadm.crt` was issued by the IPA `kubernetes-ca`.

#### Scenario: Admin cert issuer check
- **WHEN** the test runs on the master host
- **THEN** the certificate's issuer matches the `kubernetes-ca` in IPA

### Requirement: kubectl can query the cluster with admin cert
A testinfra test SHALL verify that `kubectl` can successfully query the cluster.

#### Scenario: kubectl get nodes succeeds
- **WHEN** the test runs on the master host
- **THEN** `kubectl get nodes` returns at least one node

### Requirement: Stale kubeadm state cleanup runs during teardown
Stale kubeadm configuration files SHALL be cleaned during the reset phase, not during the install phase.

#### Scenario: Stale state cleaned on reset
- **WHEN** `reset_kube` is true
- **THEN** stale kubeadm config files (`admin.conf`, `controller-manager.conf`, `scheduler.conf`, `boottstrap-token.conf`, `kubelet.conf`, `pki/`) are removed before `kubeadm reset -f`

#### Scenario: No stale cleanup on fresh install
- **WHEN** `reset_kube` is false or undefined
- **THEN** no kubeadm state cleanup is performed in `kube-install.yml`

### Requirement: API server and controller-manager trust the IPA CA
The master SHALL point the API server and controller-manager at a client CA bundle
(`/etc/kubernetes/pki/ca-bundle.crt`) that contains both the `kubeclusteradm` (CA #2) and
`kubernetes-ca` (CA #1) CA certificates.

#### Scenario: Client CA bundle is the two-CA merged bundle
- **WHEN** the client CA is installed
- **THEN** `/etc/kubernetes/pki/ca-bundle.crt` contains the `kubeclusteradm` (CA #2) CA certificate followed by the `kubernetes-ca` (CA #1) CA certificate

#### Scenario: API server uses the client CA bundle
- **WHEN** the API server static pod is patched
- **THEN** `--client-ca-file` points at `/etc/kubernetes/pki/ca-bundle.crt`

#### Scenario: Controller-manager uses the client CA bundle as root CA
- **WHEN** the controller-manager static pod is patched
- **THEN** `--root-ca-file` points at `/etc/kubernetes/pki/ca-bundle.crt`

### Requirement: Scheduler trusts the IPA CA
The master SHALL point the scheduler at the two-CA client CA bundle.

#### Scenario: Scheduler root CA is the client CA bundle
- **WHEN** the scheduler static pod is patched
- **THEN** `--root-ca-file` points at `/etc/kubernetes/pki/ca-bundle.crt`

### Requirement: Retained kubeadm CA is preserved for CSR-based signing
The master SHALL retain the kubeadm CA certificate for CSR-based cluster signing, and the
kubeadm CA SHALL NOT be part of the client CA bundle.

#### Scenario: Retained kubeadm CA is present
- **WHEN** the PKI swap retains the kubeadm CA
- **THEN** `/etc/kubernetes/pki/ca.crt.kubeadm` contains the original kubeadm CA certificate

#### Scenario: Controller-manager cluster signing uses the retained kubeadm CA
- **WHEN** the controller-manager static pod is patched
- **THEN** `--cluster-signing-cert-file` points at `/etc/kubernetes/pki/ca.crt.kubeadm`

#### Scenario: Client CA bundle does not include the kubeadm CA
- **WHEN** the client CA bundle is built
- **THEN** it contains only the `kubeclusteradm` (CA #2) and `kubernetes-ca` (CA #1) CA certificates

### Requirement: Pre-existing Calico/Tigera workloads trust the post-swap CA
After the PKI swap replaces `/etc/kubernetes/pki/ca.crt` and restarts control-plane static pods, the system SHALL rolling-restart the pre-existing `calico-node` DaemonSet (`calico-system`) so each node's in-cluster `ca.crt` is re-materialized with the post-swap CA. The trigger SHALL fire only when the workload does not yet reflect the current post-swap CA; a re-converge with an unchanged CA SHALL be a no-op.

#### Scenario: calico-node pods refreshed after swap
- **WHEN** the PKI swap has completed and control-plane components report Ready
- **THEN** each node's `calico-node` pod is rolling-restarted so it mounts the post-swap in-cluster CA
- **THEN** a `calico-node` pod is present and Ready on every node (master and workers)

#### Scenario: Recovery is idempotent
- **WHEN** converge runs again and the `calico-node` pods already trust the post-swap CA
- **THEN** the recovery step does not fail or churn the workloads unnecessarily

#### Scenario: CA rotation re-triggers recovery
- **WHEN** the post-swap CA changes after a previous recovery already ran against an earlier CA
- **THEN** the `calico-node` workload is rolling-restarted again so it picks up the new CA

### Requirement: Converge waits for per-node CNI readiness after swap
After rolling-restarting the `calico-node` DaemonSet, the system SHALL wait until a `calico-node` pod is present and Ready on every node before the converge phase completes. This guarantees worker-node CNI is initialized so nodes reach `Ready`.

#### Scenario: calico-node deployed to all nodes
- **WHEN** the rolling restart has completed after the swap
- **THEN** a `calico-node` pod exists and is Ready on each node (master and workers) before converge completes

#### Scenario: CNI not ready in time
- **WHEN** a `calico-node` pod has not become Ready on some node within the readiness timeout
- **THEN** converge fails with an error naming the affected node(s)

### Requirement: kubeclusteradm CA (CA #2) is provisioned on the IPA server
The IPA server SHALL host a second CA named `kubeclusteradm` (CA #2) that signs client
certificates, mirroring the `kubernetes-ca` (CA #1) bootstrap.

#### Scenario: CA #2 is created
- **WHEN** the PKI bootstrap runs
- **THEN** a FreeIPA CA `CN=kubeclusteradm` exists on the IPA server

#### Scenario: CA #2 ACL allows all user principals
- **WHEN** the CA #2 ACL is created
- **THEN** it allows `usercat=all`

#### Scenario: CA #2 is linked to the client cert profiles
- **WHEN** the CA #2 ACL is linked to profiles
- **THEN** the global profiles `kubeAdministrators` (O=system:masters) and `kubernetesNodes` (O=system:nodes) are linked to the CA #2 ACL

#### Scenario: CA #2 has no IP-SAN DNS records
- **WHEN** the CA #2 bootstrap runs
- **THEN** no DNS A or PTR records are created for the `kubeclusteradm` CA (its self-signed CA certificate carries no IP SANs)

#### Scenario: CA #2 ACL contains all cluster hosts
- **WHEN** the CA #2 ACL host grants run (master-only, delegated to the IPA server)
- **THEN** the `kubeclusteradm` CA ACL contains every cluster host (the IPA server, the master, and all nodes), so host-principal renewals (front-proxy as `host/<master>`, node-client as `host/<node>`) are allowed despite `usercat=all` not covering host principals

### Requirement: Controller-manager and scheduler client certs are re-issued by the kubeclusteradm CA
The kubeadm-generated controller-manager and scheduler client certificates are signed by the
kubeadm CA (CA #0), which the two-CA client CA bundle does not include; the master SHALL
re-issue both client certificates from the `kubeclusteradm` (CA #2) CA so they are trusted by
the new client CA bundle. The exact `system:masters` subjects SHALL be reproduced with static
certificate profiles (`kubeControllerManager`, `kubeScheduler`) linked to the CA #2 ACL, since
the CSR's CN is constrained by the host-principal check and the profile rewrites the issued
subject. Each component's re-issue SHALL be independently gated on the issuer of the client
certificate embedded in its own conf, so neither component's gate result SHALL skip the other
component's re-issue.

#### Scenario: Static-subject profiles are linked to the CA #2 ACL
- **WHEN** the CA #2 ACL is linked to profiles
- **THEN** the global profiles `kubeControllerManager` (subject `CN=system:kube-controller-manager, O=system:masters`) and `kubeScheduler` (subject `CN=system:kube-scheduler, O=system:masters`) are linked to the CA #2 ACL

#### Scenario: Controller-manager client cert is CA #2-signed with the exact subject
- **WHEN** the controller-manager client certificate is re-issued
- **THEN** it is issued by the `kubeclusteradm` (CA #2) CA with the `kubeControllerManager` profile and subject `CN=system:kube-controller-manager, O=system:masters`

#### Scenario: Scheduler client cert is CA #2-signed with the exact subject
- **WHEN** the scheduler client certificate is re-issued
- **THEN** it is issued by the `kubeclusteradm` (CA #2) CA with the `kubeScheduler` profile and subject `CN=system:kube-scheduler, O=system:masters`

#### Scenario: Client credentials are embedded for the scheduler
- **WHEN** the re-issued client credentials are installed
- **THEN** `controller-manager.conf` and `scheduler.conf` carry the CA #2 client certificate and key (embedded as base64 `client-certificate-data` / `client-key-data` for the scheduler static pod, which mounts only its conf), and both static pods are restarted

#### Scenario: Re-issue is independently gated per component
- **WHEN** the re-issue gate for one component runs
- **THEN** it is decided from the issuer of the client certificate embedded in that component's own conf (`controller-manager.conf` / `scheduler.conf`), and neither component's gate result skips the other component's re-issue

#### Scenario: Partial failure is repaired on re-converge
- **WHEN** a re-converge runs and `controller-manager.conf` already carries a CA #2-signed client certificate but `scheduler.conf` still carries a CA #0-signed client certificate
- **THEN** the controller-manager re-issue is skipped and the scheduler re-issue runs

#### Scenario: Completed re-issue is skipped without churn
- **WHEN** a re-converge runs and a component's conf already carries a CA #2-signed client certificate
- **THEN** that component's key/CSR/cert are not regenerated, its conf is not re-embedded, and its static pod is not restarted

### Requirement: PKI swap verification runs after the admin credential re-issue
The `ipa-pki-swap` verification tasks (controller-manager lease gate, node Ready gate) and the
`kubeclusteradm` admin `kubectl get nodes` verification SHALL run after `admin-user.yml` has
re-issued the admin client cert from CA #2 and re-embedded it in `admin.conf`, because the new
client CA bundle no longer trusts the previous (CA #0-issued) admin cert.

#### Scenario: Swap gates authenticate with a CA #2 admin cert
- **WHEN** the PKI swap verifies cluster health
- **THEN** `main.yml` has run `admin-user.yml` (admin cert re-issue + `admin.conf` re-embed) before `ipa-pki-swap.yml`, so the gate tasks authenticate with a CA #2-issued admin cert

#### Scenario: Admin `kubectl` verification runs after the re-embed
- **WHEN** the `kubeclusteradm` admin credential is verified with `kubectl get nodes`
- **THEN** the verification runs at the end of `admin-user.yml`, after the CA #2 cert has been re-embedded in `admin.conf`

### Requirement: Master kubelet client cert is wired into kubelet.conf
The master SHALL point `/etc/kubernetes/kubelet.conf` at the CA #2-signed
`apiserver-kubelet-client.{crt,key}` so the master kubelet authenticates with a cert trusted by
the two-CA client CA bundle, and SHALL restart the kubelet after the PKI swap so the post-swap
trust anchor and client credentials take effect.

#### Scenario: kubelet.conf references the CA #2-signed client cert
- **WHEN** the kubelet client certificate is requested from CA #2
- **THEN** `/etc/kubernetes/kubelet.conf` `client-certificate` and `client-key` point at `/etc/kubernetes/pki/apiserver-kubelet-client.{crt,key}`

#### Scenario: Kubelet restarts after the swap
- **WHEN** the PKI swap completes on the master
- **THEN** the master's kubelet is restarted (gated on the `apiServerOverride` block change, so a re-converge does not churn it) and the master node reports Ready before the Calico data-plane recovery runs

### Requirement: The master kubelet unit does not bootstrap a client cert
The master kubelet unit SHALL NOT keep the kubeadm bootstrap mechanism (`--bootstrap-kubeconfig` from the
package drop-in), because with `rotateCertificates` enabled the kubelet bootstraps a client cert signed by
the original kubeadm CA — which the two-CA client bundle no longer trusts — leaving the master node
`NotReady` after the swap.

#### Scenario: Bootstrap drop-in removed and clean unit in place
- **WHEN** the master's kubelet client certificate is requested from CA #2
- **THEN** the package drop-in carrying `--bootstrap-kubeconfig` is removed and a clean drop-in runs the
  kubelet with `/etc/kubernetes/kubelet.conf` (IPA cert) only, no bootstrap, no rotation, and a pinned
  `--node-ip`

#### Scenario: Rotation disabled and stale store removed
- **WHEN** the bootstrap mechanism is removed
- **THEN** `rotateCertificates` is disabled in the kubelet `config.yaml` and the stale `/var/lib/kubelet/pki`
  store and the orphaned `bootstrap-kubelet.conf` are removed

#### Scenario: Kubelet restarts only when the unit or credentials changed
- **WHEN** the master's kubelet unit or client credentials were modified
- **THEN** the kubelet is restarted to pick up the new unit and credentials, and a re-converge where nothing
  changed does not restart it
