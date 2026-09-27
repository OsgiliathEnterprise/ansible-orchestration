## Context

See proposal.md for motivation. All IPA-issued cluster certs are created once via `ipacert` and guarded by a `stat` check (`admin-user.yml`, `kube-node-cert.yml`, control-plane cert tasks), so they are never refreshed after first issuance. Profiles inherit FreeIPA's default validity (~90 days). No renewal, cron, or timer mechanism exists anywhere in the role or monorepo — this is greenfield; whatever we pick becomes the convention.

## Goals / Non-Goals

**Goals:**
- Continuous, self-healing renewal of every expiring cluster cert (worker + master admin + control-plane), independent of converge runs.
- Identity-preserving renewal (same subject/principal/key) without any admin password at runtime.
- Post-renewal deployment + service reload so running components use the renewed cert.

**Non-Goals:**
- No change to the initial issuance flow (`ipa-pki-bootstrap` / `ipa-pki-infra` stay as-is).
- No central certificate-management service — a per-host timer is sufficient at this scale.
- No cross-cluster or multi-master HA renewal orchestration.

## Decisions

### D1: Trigger = continuous per-host systemd timer (not converge-driven)
Each host runs a persistent systemd timer that fires on schedule and triggers renewal. This makes renewal self-healing — it survives between converges, so a cert cannot silently expire just because no one re-converged.

- **Alternative considered:** converge-driven threshold (renew only when a converge runs and the cert is near expiry). Rejected — if no converge happens before expiry, the cert lapses; liveness would depend on operator action.
- **Interval:** weekly tick with `RandomizedDelaySec` jitter to stagger reloads across hosts, plus `Persistent=true` so missed runs catch up after reboot/downtime. Ticks are cheap because renewal is eligibility-gated (see D5).

### D2: Mechanism = keytab-driven re-issue from the same key (not native renew)
Spike finding: FreeIPA has **no native in-place renew** (`ipa-cert-renew` does not exist), and certmonger's IPA helper can only target the default CA `ipa`, so it cannot act on our custom `kubernetes-ca` (ACL denial reproduced). The adopted mechanism re-issues each eligible cert via `ipa cert-request --ca=kubernetes-ca`, authenticated with a keytab — no admin password at runtime:
- **Worker node cert:** host keytab (`/etc/krb5.keytab`) → principal `host/<node>`, profile `kubernetesNodes` (profile rewrites the subject to `system:node:<node>`).
- **Control-plane certs (apiserver, front-proxy):** master host keytab → principals `HTTP/<master>` / `host/<master>`, profile `kubeAdministrators`.
- **Master admin cert:** `kubeclusteradm` user keytab (generated on the IDM at converge time) → principal `kubeclusteradm`, profile `kubeAdministrators`.

Identity is preserved because the CSR reuses the existing private key and the profile rewrites the subject — only the serial/validity change. Requires the CA ACL (`kubernetes-ca-acl`) to permit each principal type (hosts + user category all) — verified via `ipa caacl-show`.

- **Alternative considered:** certmonger tracking (`ipa-getcert start-tracking`). Rejected after spike — its IPA helper targets only the default CA, so renewal of `kubernetes-ca`-issued certs is denied by the ACL.
- **Coupling:** designed group-aware from the start — the timer + renewal loop over the full worker group plus master, so it composes with `support-n-worker-nodes` without a rewrite.

### D3: Scope = all expiring cluster certs
Renewal covers every finite-validity IPA-issued cert: worker node certs, the master admin cert, and control-plane component certs (API server, front-proxy). Each host's timer renews the certs that live on that host.

### D4: Post-renewal deploy + reload per cert type
After a renew succeeds, redeploy to path and reload/restart the affected service:
- **Worker:** `/etc/kubernetes/pki/node-client.{crt,key}` → kubelet reload (node stays Ready).
- **Master admin:** `kubeadm.crt` + `admin.conf` credentials → operator access restored.
- **Control-plane:** component cert paths → restart the affected static pod(s); API-server restart is the riskiest and is gated/staggered.

### D5: Idempotency / no churn
A timer tick acts only on certs actually eligible for renewal: a cert is eligible when its remaining validity drops below a threshold (default 30 days, configurable via `kube_cert_renew_threshold_days`). When nothing is due, the tick is a no-op — no cert rewrite, no service restart — so repeated ticks do not churn healthy components.

## Risks / Trade-offs

- [Re-issue changes the serial number each renewal] → Inherent to any X509 re-issue; identity (subject/principal/key) is preserved and only renewals near expiry trigger a new serial, so churn is minimal (~once per validity window).
- [Service restart causes brief node NotReady / API blip] → Stagger timer across hosts (jitter) so nodes don't all reload simultaneously; gate control-plane static-pod restarts carefully and prefer reload over full restart where possible.
- [Host reboot loses the schedule] → systemd timers persist on disk and `Persistent=true` catches up missed runs after boot.
- [Renewal requires IPA reachable from each host] → Hosts are already IPA clients (keytab present); if IDM is down, renewal defers but certs remain valid until their existing expiry — no immediate breakage.

## Migration Plan

Additive and non-disruptive: install the timer on existing hosts; a running cluster is unaffected until a cert actually becomes eligible. Rollback = disable/remove the timers (certs continue on their current validity). No data migration.

## Open Questions

- **Resolved (spike):** native renew does not exist and certmonger cannot target our custom CA — keytab-driven re-issue adopted (see D2).
- **Timer interval + jitter values:** weekly tick + 4h randomized delay chosen; tune if needed.
