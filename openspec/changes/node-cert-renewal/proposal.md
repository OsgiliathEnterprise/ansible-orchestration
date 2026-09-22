## Why

Every IPA-issued Kubernetes cluster certificate — worker node certs (`system:node:<host>`), the master admin cert (`kubeclusteradm` → `admin.conf`), and control-plane component certs (API server, front-proxy) — is issued once via `ipacert`, guarded by a `stat` check, and never refreshed. After their validity window (FreeIPA default ~90 days) they expire: worker nodes go NotReady, operator access via `admin.conf` breaks, and control-plane components lose valid client certs. There is no renewal mechanism anywhere in the role or monorepo today, so a long-running cluster silently degrades until someone re-converges by hand.

## What Changes

- Add a **continuous per-host timer** (systemd timer) on every host (master + all workers) that runs native `ipa-cert-renew` for eligible certificates — renewal is self-healing and not tied to converge runs.
- Use the **native FreeIPA renewal mechanism** (`ipa-cert-renew`) rather than re-issuing via a fresh CSR, so certs renew in place with their identity preserved.
- Cover **all expiring cluster certs**: worker node certs, the master admin cert, and control-plane component certs — no cluster certificate is left to expire unattended.
- Enable renewal on the relevant profiles/CA so `ipa-cert-renew` can act.
- After a renewal, redeploy the renewed cert to its path and reload/restart the affected service so the running component actually uses it.

## Capabilities

### New Capabilities
- `kube-cert-renewal`: continuous, self-healing renewal of all IPA-issued Kubernetes cluster certificates via native FreeIPA renewal driven by a per-host timer, with post-renewal deployment and service reload.

### Modified Capabilities
<!-- None: initial certificate issuance (ipa-pki-bootstrap / ipa-pki-infra) is unchanged; this change adds a continuous lifecycle layer on top of it. -->

## Impact

- New tasks: per-host systemd-timer provisioning, native `ipa-cert-renew` execution, post-renewal cert deployment + service reload/restart.
- Profile/CA configuration: renewal must be permitted for the node/admin/control-plane profiles.
- Affects every host (master + all workers); no change to the initial issuance flow.
- Couples with `support-n-worker-nodes`: the timer and renewal loop over the full worker group, so this is designed group-aware from the start.
