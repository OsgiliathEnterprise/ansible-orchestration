# Proposal

## Why

The controller-manager and scheduler client-cert re-issues are coupled in a single task file
(`tasks/ipa-controlplane-clients.yml`) under a single shared gate (the controller-manager
conf's embedded-cert issuer). The two components share no runtime state — separate
key/CSR/cert files, separate conf files, separate static pods, separate cert profiles — so the
coupling is gratuitous. It also creates a recovery gap: if the controller-manager swap
completes and the scheduler swap fails, a re-converge sees the controller-manager conf
already CA #2-signed, skips the whole block, and no task ever re-issues the scheduler
certificate — which the two-CA client CA bundle no longer trusts.

## What Changes

- Split `tasks/ipa-controlplane-clients.yml` into `tasks/ipa-controller-manager-client.yml`
  and `tasks/ipa-scheduler-client.yml`, each self-contained: a read-only gate on its own
  conf's embedded client-certificate issuer, then key/CSR/`ipacert` request/conf
  re-embed/static-pod restart, all gated on its own flag.
- `tasks/ipa-certs.yml` includes the two files (controller-manager first, then scheduler)
  in place of the single `ipa-controlplane-clients.yml` include.
- The scheduler gate uses the same extraction pattern as the controller-manager gate
  (embedded `client-certificate-data` in `scheduler.conf` — kubeadm embeds it because the
  scheduler static pod mounts only its conf), writing a distinct temp file.
- No change to profile creation (`ipa-kubernetes-ca.yml`), CA #2 profile links
  (`ipa-kubeclusteradm-ca.yml`), renewal (`kube-cert-renew.sh.j2`), or the `ipa-pki-swap`
  verification gates — those are already per-component independent.
- Role `AGENTS.md` L3 task-flow graph updated.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ipa-pki-bootstrap`: the "Controller-manager and scheduler client certs are re-issued by
  the kubeclusteradm CA" requirement gains per-component independent gating — each
  component's re-issue is gated on the issuer of the client certificate embedded in its own
  conf, so a partial failure of one component does not prevent that component from being
  re-issued on a later re-converge.

## Impact

- `tasks/ipa-controlplane-clients.yml` — removed (replaced by two files).
- `tasks/ipa-controller-manager-client.yml`, `tasks/ipa-scheduler-client.yml` — new.
- `tasks/ipa-certs.yml` — two `include_tasks` replace one.
- Role `AGENTS.md` — L3 graph update.
- `openspec/specs/ipa-pki-bootstrap/spec.md` — requirement scenarios updated via delta.
- No molecule test references the task-file names; verification is the standard
  destroy → converge → verify cycle plus lint.
