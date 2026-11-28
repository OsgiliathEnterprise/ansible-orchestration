# Spec Delta

## MODIFIED Requirements

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
- **AND** the transient gate anchor, a run-scoped temporary file created only while the old-cert window is open, has been removed at its minted path regardless of its generated name

#### Scenario: Transient old-cert window during the swap
- **WHEN** a fresh cluster's API still presents the kubeadm-signed serving cert mid-swap
- **THEN** the readiness gate MAY trust the kubeadm CA only through the run-scoped temporary anchor while `ca.crt.kubeadm` exists, and must fall back to a bundle-only anchor once the retained file is absent

#### Scenario: Re-converge after retirement
- **WHEN** the role converges again with the kubeadm CA already retired
- **THEN** the backup, gate-anchor slurp and deletion tasks all report no change and none fails (the anchor mint task is skipped because the old-cert window is closed), and `ca.crt.kubeadm` is not re-created from the swapped-in IPA CA
