## ADDED Requirements

### Requirement: Master kubelet x509 client authentication trusts the merged CA bundle
The master's kubelet configuration SHALL authenticate API-server-proxied client
certificates against the merged CA bundle (`/etc/kubernetes/pki/ca-bundle.crt`,
`kubeclusteradm` CA #2 + `kubernetes-ca` CA #1), so that the `apiserver-kubelet-client`
certificate re-issued under CA #2 by the PKI swap is accepted.

#### Scenario: clientCAFile points at the bundle
- **WHEN** the IPA PKI swap completes on the master
- **THEN** `/var/lib/kubelet/config.yaml` sets `authentication.x509.clientCAFile` to `/etc/kubernetes/pki/ca-bundle.crt`
- **THEN** the kubelet has been restarted after the patch changed the file

#### Scenario: proxied subresources authenticate
- **WHEN** the API server proxies `kubectl exec`, `kubectl logs`, or `kubectl port-forward` to the master's kubelet using the CA #2-issued `apiserver-kubelet-client` certificate
- **THEN** the kubelet accepts the request instead of answering `401 Unauthorized`

#### Scenario: Re-converge does not churn the kubelet
- **WHEN** the role converges again with the bundle already referenced by `clientCAFile`
- **THEN** the patch task reports no change and kubelet is not restarted

### Requirement: Kubeadm self-signed CA fully retired after the swap
Once the IPA PKI swap completes, the master SHALL hold no persistent trace of the kubeadm
self-signed CA: the retained certificate (`/etc/kubernetes/pki/ca.crt.kubeadm`) and its
private key (`/etc/kubernetes/pki/ca.key`) are removed, kube-controller-manager no longer
signs CSRs under it, and no component trusts it. The steady-state trust surface is exactly
the two IPA-issued CAs.

#### Scenario: CSR cluster signing disabled in the KCM manifest
- **WHEN** the swap patches `/etc/kubernetes/manifests/kube-controller-manager.yaml`
- **THEN** the `--cluster-signing-cert-file` and `--cluster-signing-key-file` flags carry no reference to `ca.crt.kubeadm` or `ca.key` (emptied, so the CSR signers stay disabled)

#### Scenario: Kubeadm CA artifacts deleted at end of swap
- **WHEN** the swap completes on the master
- **THEN** `/etc/kubernetes/pki/ca.crt.kubeadm` and `/etc/kubernetes/pki/ca.key` do not exist
- **AND** the transient gate anchor `/tmp/kube-api-gate-anchor.crt` has been removed

#### Scenario: Transient old-cert window during the swap
- **WHEN** a fresh cluster's API still presents the kubeadm-signed serving cert mid-swap
- **THEN** the readiness gate MAY trust the kubeadm CA only through the `/tmp` anchor while `ca.crt.kubeadm` exists, and must fall back to a bundle-only anchor once the retained file is absent

#### Scenario: Re-converge after retirement
- **WHEN** the role converges again with the kubeadm CA already retired
- **THEN** the backup, gate-anchor slurp and deletion tasks all report no change and none fails, and `ca.crt.kubeadm` is not re-created from the swapped-in IPA CA
