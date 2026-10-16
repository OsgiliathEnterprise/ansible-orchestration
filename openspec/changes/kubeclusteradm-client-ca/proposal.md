# Why

The Kubernetes cluster currently trusts a single FreeIPA CA (`kubernetes-ca`) for both the API
server's **serving** certificate and all **client** certificates (front-proxy client, kubelet
client, per-node client, and the `kubeclusteradm` cluster-admin user). The merged client CA
(`ca-bundle.crt`) is the kubeadm CA + `kubernetes-ca`.

We want to separate the CA that signs the **serving** certificate (`CA #1 = kubernetes-ca`,
the cluster trust anchor) from the CA that signs **client** certificates (`CA #2 =
kubeclusteradm`). This is a key-separation / defense-in-depth measure: compromising the
client-signing CA no longer compromises the cluster trust anchor. The client CA becomes the
merged bundle of both CAs.

# What Changes

- Introduce a second FreeIPA CA `kubeclusteradm` (CA #2) on the IPA server, mirroring the
  existing `kubernetes-ca` (CA #1) bootstrap (CA object, CA ACL, profile links, DNS A+PTR).
- Move all **client** certificate requests from CA #1 to CA #2:
  - front-proxy client cert
  - kubelet client cert
  - per-node client cert (`system:node:<hostname>`)
  - `kubeclusteradm` cluster-admin user cert
- Keep the API server **serving** certificate on CA #1 (`kubernetes-ca`), so `ca.crt` (the
  cluster trust anchor) stays the `kubernetes-ca` CA.
- Rebuild the client CA bundle (`ca-bundle.crt`) as the merged `kubeclusteradm` (CA #2) +
  `kubernetes-ca` (CA #1) instead of kubeadm + `kubernetes-ca`. The kubeadm CA is retained
  only as `ca.crt.kubeadm` for `--cluster-signing-cert-file` (CSR-based signing).
- No changes to component flags or file layout beyond the bundle's composition.

# Capabilities

## New Capabilities

(none)

## Modified Capabilities

- `ipa-pki-bootstrap`: the PKI swap now provisions a second CA (`kubeclusteradm`, CA #2), signs
  client certs from it, keeps the serving cert on `kubernetes-ca` (CA #1), and rebuilds
  `ca-bundle.crt` as the two-CA bundle (CA #2 + CA #1).
- `ipa-kubectl-auth`: the `kubeclusteradm` admin cert is now signed by the `kubeclusteradm` CA
  (CA #2) instead of `kubernetes-ca`.
- `kube-node-join`: the per-node client cert is now signed by the `kubeclusteradm` CA (CA #2).
