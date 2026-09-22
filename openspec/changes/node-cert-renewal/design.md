## Context

See proposal.md for motivation. All IPA-issued cluster certs are created once via `ipacert` and guarded by a `stat` check (`admin-user.yml`, `kube-node-cert.yml`, control-plane cert tasks), so they are never refreshed after first issuance. Profiles inherit FreeIPA's default validity (~90 days). No renewal, cron, or timer mechanism exists anywhere in the role or monorepo — this is greenfield; whatever we pick becomes the convention.

## Goals / Non-Goals

**Goals:**
- Continuous, self-healing renewal of every expiring cluster cert (worker + master admin + control-plane), independent of converge runs.
- In-place native renewal that preserves certificate identity.
- Post-renewal deployment + service reload so running components use the renewed cert.

**Non-Goals:**
- No change to the initial issuance flow (`ipa-pki-bootstrap` / `ipa-pki-infra` stay as-is).
- No central certificate-management service — a per-host timer is sufficient at this scale.
- No cross-cluster or multi-master HA renewal orchestration.

## Decisions

### D1: Trigger = continuous per-host systemd timer (not converge-driven)
Each host runs a persistent systemd timer that fires on schedule and triggers renewal. This makes renewal self-healing — it survives between converges, so a cert cannot silently expire just because no one re-converged.

- **Alternative considered:** converge-driven threshold (renew only when a converge runs and the cert is near expiry). Rejected — if no converge happens before expiry, the cert lapses; liveness would depend on operator action.
- **Interval:** daily tick with `Persistent=true` so missed runs catch up after reboot/downtime. `ipa-cert-renew` is itself a no-op when nothing is eligible, so frequent ticks are cheap (see D5).

### D2: Mechanism = native `ipa-cert-renew` (not re-issue via fresh CSR)
Use FreeIPA's native renewal so certs renew in place with their subject/principal preserved — no serial churn, minimal redeploy. Requires the profile/CA to permit renewal and each host to have an IPA client keytab (already true: hosts are IPA clients).

- **Alternative considered:** re-issue via `ipacert` with a fresh CSR. Rejected as primary — new serial each cycle, more redeploy complexity. Retained as documented fallback if native renew proves unsupported (see Open Questions / spike).
- **Coupling:** designed group-aware from the start — the timer + renewal loop over the full worker group plus master, so it composes with `support-n-worker-nodes` without a rewrite.

### D3: Scope = all expiring cluster certs
Renewal covers every finite-validity IPA-issued cert: worker node certs, the master admin cert, and control-plane component certs (API server, front-proxy). Each host's timer renews the certs that live on that host.

### D4: Post-renewal deploy + reload per cert type
After a renew succeeds, redeploy to path and reload/restart the affected service:
- **Worker:** `/etc/kubernetes/pki/node-client.{crt,key}` → kubelet reload (node stays Ready).
- **Master admin:** `kubeadm.crt` + `admin.conf` credentials → operator access restored.
- **Control-plane:** component cert paths → restart the affected static pod(s); API-server restart is the riskiest and is gated/staggered.

### D5: Idempotency / no churn
A timer tick acts only on certs actually eligible for renewal (FreeIPA's own eligibility policy). When nothing is due, the tick is a no-op — no cert rewrite, no service restart — so repeated ticks do not churn healthy components.

## Risks / Trade-offs

- [Native `ipa-cert-renew` may be unsupported by our CA/profile] → Run a viability spike first (task 1.1); if it fails, fall back to re-issue-via-ipacert and adjust D2/D4 accordingly.
- [Service restart causes brief node NotReady / API blip] → Stagger timer across hosts (jitter) so nodes don't all reload simultaneously; gate control-plane static-pod restarts carefully and prefer reload over full restart where possible.
- [Host reboot loses the schedule] → systemd timers persist on disk and `Persistent=true` catches up missed runs after boot.
- [Renewal requires IPA reachable from each host] → Hosts are already IPA clients (keytab present); if IDM is down, renewal defers but certs remain valid until their existing expiry — no immediate breakage.

## Migration Plan

Additive and non-disruptive: install the timer on existing hosts; a running cluster is unaffected until a cert actually becomes eligible. Rollback = disable/remove the timers (certs continue on their current validity). No data migration.

## Open Questions

- **Native-renew viability:** confirm `ipa-cert-renew` works against our CA/profiles (renewal enabled) — this is the go/no-go spike; if unsupported, adopt the re-issue fallback.
- **Timer interval + jitter values:** tune during implementation (default daily + per-host random offset).
