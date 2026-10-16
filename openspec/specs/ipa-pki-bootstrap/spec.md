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
The system SHALL download the `kubernetes-ca` certificate and place it at `/etc/kubernetes/pki/ca.crt` on the Kubernetes master.

#### Scenario: CA certificate is downloaded
- **WHEN** the role runs
- **THEN** the `kubernetes-ca` certificate is written to `/etc/kubernetes/pki/ca.crt`
- **THEN** the file is owned by root with mode 0644

### Requirement: API server certificate is IPA-signed
The system SHALL generate a private key and CSR for the API server, request a certificate from the `kubernetes-ca` via the `freeipa.ansible_freeipa.ipacert` module, and place the signed certificate at `/etc/kubernetes/pki/apiserver.crt`.

#### Scenario: API server cert is requested and placed
- **WHEN** the role runs and `apiserver.crt` does not exist
- **THEN** a private key is generated at `/etc/kubernetes/pki/apiserver.key`
- **THEN** a CSR is generated with CN matching `apiserver.kubernetes.<company_domain>` and SANs including the master hostname, master IP, and any `kube_alt_names`
- **THEN** the certificate is requested via `ipacert` module with `principal=HTTP/apiserver.kubernetes.<company_domain>`, `ca=kubernetes-ca`
- **THEN** the signed certificate is placed at `/etc/kubernetes/pki/apiserver.crt`

#### Scenario: API server cert already exists
- **WHEN** the role runs and `apiserver.crt` already exists
- **THEN** no new certificate request is performed and the task reports no change

### Requirement: Front-proxy client certificate is IPA-signed
The system SHALL generate a private key and CSR for the front-proxy client, request a certificate from the `kubernetes-ca` via the `ipacert` module, and place the signed certificate at `/etc/kubernetes/pki/front-proxy-client.crt`.

#### Scenario: Front-proxy cert is requested and placed
- **WHEN** the role runs and `front-proxy-client.crt` does not exist
- **THEN** a private key is generated at `/etc/kubernetes/pki/front-proxy-client.key`
- **THEN** a CSR is generated with CN matching the master hostname
- **THEN** the certificate is requested via `ipacert` module with `ca=kubernetes-ca`
- **THEN** the signed certificate is placed at `/etc/kubernetes/pki/front-proxy-client.crt`

### Requirement: Kubelet client certificate is IPA-signed
The system SHALL generate a private key and CSR for the kubelet client, request a certificate from the `kubernetes-ca` via the `ipacert` module with the `kubeAdministrators` profile, and place the signed certificate at `/etc/kubernetes/pki/apiserver-kubelet-client.crt`.

#### Scenario: Kubelet client cert is requested and placed
- **WHEN** the role runs and `apiserver-kubelet-client.crt` does not exist
- **THEN** a private key is generated at `/etc/kubernetes/pki/apiserver-kubelet-client.key`
- **THEN** a CSR is generated with `O=system:masters` and CN matching the master hostname
- **THEN** the certificate is requested via `ipacert` module with `ca=kubernetes-ca`, `profile_id=kubeAdministrators`
- **THEN** the signed certificate is placed at `/etc/kubernetes/pki/apiserver-kubelet-client.crt`

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

### Requirement: Controller-manager and scheduler configs trust IPA CA
After the PKI swap, the controller-manager and scheduler static pod manifests SHALL be patched so client authentication trusts both CAs (the merged bundle) while cluster certificate signing continues with the retained kubeadm CA.

#### Scenario: Component configs are patched
- **WHEN** the role runs on a master after the CA swap
- **THEN** the controller-manager manifest's `--client-ca-file` references `/etc/kubernetes/pki/ca-bundle.crt` (kubeadm + IPA CAs)
- **THEN** the controller-manager manifest's `--cluster-signing-cert-file` references `/etc/kubernetes/pki/ca.crt.kubeadm` (retained kubeadm CA for cluster cert signing)
- **THEN** the controller-manager manifest's `--root-ca-file` references `/etc/kubernetes/pki/ca-bundle.crt`
- **THEN** if present, the scheduler manifest's `--root-ca-file` references `/etc/kubernetes/pki/ca-bundle.crt`

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
