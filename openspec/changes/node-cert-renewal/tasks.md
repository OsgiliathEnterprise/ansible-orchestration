## 1. Renewal viability spike (go/no-go gate)

- [ ] 1.1 Confirm the `kubernetes-ca` and node/admin/control-plane profiles permit renewal, then run native `ipa-cert-renew` against one worker's node cert and verify it renews in place (same subject/principal, later `notAfter`). **Gate — do not proceed past this group until it passes.** If native renew is unsupported, document the re-issue-via-ipacert fallback and adjust design D2/D4 before continuing.

## 2. Profile / CA renewal enablement

- [ ] 2.1 Ensure the node (`kubernetesNodes`), admin (`kubeAdministrators`), and control-plane profiles permit renewal and verify via `ipa certprofile-show` that each reflects renewal enabled.

## 3. Per-host timer provisioning

- [ ] 3.1 Add a task that installs a persistent systemd timer on every host (master + all workers) running native `ipa-cert-renew` for eligible certs, with per-host jitter to stagger reloads; verify the timer is active (`systemctl list-timers`) and set `Persistent=true`.

## 4. Post-renewal deployment + service reload

- [ ] 4.1 Worker: after a renew, redeploy `/etc/kubernetes/pki/node-client.{crt,key}` and reload kubelet; verify the node stays Ready and the kubelet presents the renewed cert.
- [ ] 4.2 Master admin: after a renew, update `kubeadm.crt` + `admin.conf` credentials; verify `kubectl` via `admin.conf` still authenticates with the renewed cert.
- [ ] 4.3 Control-plane: redeploy component certs and restart the affected static pod(s) (API server / front-proxy), gated/staggered; verify the API server remains healthy after restart.

## 5. Idempotency / no-churn

- [ ] 5.1 Verify a timer tick with no eligible cert performs no cert rewrite and no service restart (no-op); confirm repeated ticks do not churn healthy components.

## 6. End-to-end verification

- [ ] 6.1 Run the full cycle on a multi-worker cluster; verify timers are active on all hosts, then force/simulate an eligibility to confirm certs extend in place and services stay healthy (nodes Ready, `kubectl` via admin.conf working).
