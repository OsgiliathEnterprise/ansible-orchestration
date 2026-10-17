## Why

Every IPA-issued Kubernetes cluster certificate — worker node certs (`system:node:<host>`), the master admin cert (`kubeclusteradm` → `admin.conf`), and control-plane component certs (API server, front-proxy) — is issued once via `ipacert`, guarded by a `stat` check, and never refreshed. After their validity window (FreeIPA default ~90 days) they expire: worker nodes go NotReady, operator access via `admin.conf` breaks, and control-plane components lose valid client certs. There is no renewal mechanism anywhere in the role or monorepo today, so a long-running cluster silently degrades until someone re-converges by hand.

## What Changes

- Add a **continuous per-host timer** (systemd timer) on every host (master + all workers) that renews eligible certificates — renewal is self-healing and not tied to converge runs.
- Renewal uses **keytab-driven re-issue from the same key**: `ipa cert-request --ca=kubernetes-ca` authenticated with each host's own keytab (host keytab for node/apiserver/front-proxy certs, `kubeclusteradm` user keytab for the admin cert) — no admin password at runtime. Identity is preserved because the profile rewrites the CSR subject and the existing private key is reused.
  - Spike finding: FreeIPA has no native in-place renew command (`ipa-cert-renew` does not exist), and certmonger's IPA helper can only target the default CA `ipa`, so it cannot act on our custom `kubernetes-ca`. Re-issue from the same key is therefore the mechanism of record.
- Cover **all expiring cluster certs**: worker node certs, the master admin cert, and control-plane component certs — no cluster certificate is left to expire unattended.
- Renewal is **eligibility-gated** (renew only when remaining validity drops below a threshold), so ticks with nothing due are cheap no-ops.
- After a renewal, redeploy the renewed cert to its path and reload/restart the affected service so the running component actually uses it.

## Capabilities

### New Capabilities
- `kube-cert-renewal`: continuous, self-healing renewal of all IPA-issued Kubernetes cluster certificates via keytab-driven re-issue from the same key, driven by a per-host timer, with post-renewal deployment and service reload.

### Modified Capabilities
<!-- None: initial certificate issuance (ipa-pki-bootstrap / ipa-pki-infra) is unchanged; this change adds a continuous lifecycle layer on top of it. -->

## Impact

- New tasks: per-host systemd-timer provisioning, eligibility-gated `ipa cert-request --ca=kubernetes-ca` execution (keytab-authenticated), post-renewal cert deployment + service reload/restart.
- Profile/CA configuration: the node/admin/control-plane profiles must accept re-issue for each principal type via the CA ACL (`kubernetes-ca-acl`).
- Affects every host (master + all workers); no change to the initial issuance flow.
- Couples with `support-n-worker-nodes`: the timer and renewal loop over the full worker group, so this is designed group-aware from the start.
