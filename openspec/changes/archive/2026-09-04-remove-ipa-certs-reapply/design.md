## Context

See proposal.md for motivation. Verified facts:

- `ipa-certs-reapply.yml` is included only from `tasks/main.yml:60-63`; its sole task waits on port 6443, duplicating `ipa-pki-swap.yml:85-91`.
- No task in the role reads the cluster-info ConfigMap after the swap; node join (`kube-install-join-node.yml`) copies `admin.conf` directly.
- The comment at `tasks/kube-install.yml:74-78` lists `ipa-certs-reapply` as part of master post-processing and must be updated alongside the deletion.

## Goals / Non-Goals

**Goals:**
- Remove the misleading file, its include, and the spec requirement it was supposed to satisfy.
- Preserve spec coverage for the behavior that actually exists (post-swap API readiness in `ipa-pki-swap.yml`).

**Non-Goals:**
- No implementation of ConfigMap re-application (user decision: delete rather than implement).
- No changes to `ipa-pki-swap.yml` — its waits stay as-is; native-module improvements there belong to change `ipa-pki-swap-native-modules`.

## Decisions

**D1: Delete the file and its include, do not rename/repurpose.**
A standalone "stabilization wait" file adds nothing — `ipa-pki-swap.yml` already waits on port 6443 *and* polls controller-manager Ready. Renaming would preserve a redundant task; deletion removes it entirely (user-confirmed).
*Alternative considered:* rename to `api-server-stabilize.yml` and dedupe — rejected as it keeps a second, weaker wait in the flow.

**D2: Replace the removed requirement with a readiness requirement.**
Removing *"ConfigMap is re-applied after API server stabilization"* without replacement would silently drop spec coverage of post-swap readiness (currently only implicit). The delta therefore adds *"API server serves traffic after PKI swap"*, whose scenarios match `ipa-pki-swap.yml:85-105` exactly.
*Alternative considered:* pure removal — rejected; it leaves the spec unable to express that the flow must not proceed until the API is serving.

**D3: Comment edit applies on top of change `remove-dead-join-code`.**
Both changes touch the comment block at `kube-install.yml:74-78` (change 2 extends it, this change removes one list item). Implement `remove-dead-join-code` first; this change's edit then operates on the extended block.

## Risks / Trade-offs

- [ConfigMap re-application is actually needed by something overlooked] → Mitigation: grep confirms no task reads the ConfigMap post-swap and join uses direct copy; if token discovery is ever reintroduced, the requirement returns with an implementing task (noted in the delta's Migration).
- [`main.yml` syntax breaks when removing the include block] → Mitigation: `ansible-playbook --syntax-check` on the role's playbooks plus a full converge run.
- [Spec delta rejected by reviewer as scope creep (the ADDED requirement)] → It is flagged in the proposal; if unwanted, drop the ADDED section and keep only the REMOVED one — the change still validates.

## Migration Plan

Delete file → edit `main.yml` → update comment → write spec delta → converge + idempotence verification. Rollback = git restore of three files. Spec sync happens at archive time (delta applies to `openspec/specs/ipa-pki-bootstrap/spec.md`).

## Open Questions

None — delete-vs-replicate was confirmed with the user during exploration.
