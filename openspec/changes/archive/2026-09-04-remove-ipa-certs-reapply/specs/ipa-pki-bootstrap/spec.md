## ADDED Requirements

### Requirement: API server serves traffic after PKI swap
After the static pods are restarted following the PKI certificate swap, the system SHALL verify that port 6443 accepts connections and that `kube-controller-manager` reports Ready before proceeding.

#### Scenario: API server ready after swap
- **WHEN** the role runs on a master and the API server static pod has been restarted with new certificates
- **THEN** port 6443 accepts TCP connections (retried until available)
- **THEN** `kubectl get pods -n kube-system` shows `kube-controller-manager` in Ready state

## REMOVED Requirements

### Requirement: ConfigMap is re-applied after API server stabilization
**Reason**: The cluster-info ConfigMap is no longer consumed by the join flow. Nodes join via direct copy of `admin.conf` (`kube-install-join-node.yml`), not token+CA-hash discovery, so nothing reads the CA from the ConfigMap. No task ever implemented this re-application; the requirement described behavior that was never realized and is now obsolete under the current join design.
**Migration**: None required. Post-swap API readiness is covered by the new "API server serves traffic after PKI swap" requirement, which matches the actual waits in `ipa-pki-swap.yml`. If ConfigMap-based discovery is ever reintroduced, a re-application requirement should be added at that time with an implementing task.
