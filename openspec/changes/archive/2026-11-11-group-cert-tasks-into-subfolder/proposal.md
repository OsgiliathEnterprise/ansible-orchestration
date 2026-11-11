# Proposal

## Why

The certificate/PKI machinery — 21 of 42 task files (CA provisioning, service/node cert enrollment, PKI swap, renewal) — sits flat in `tasks/` interleaved with install, delete, firewall and NFS files, so the cert domain has no discoverable boundary. Compounding this, both the role `AGENTS.md` and the monorepo `ansible/roles/AGENTS.md` claim a committed static gate (`tests/static_gate.py`) is the standing hygiene guard, but that file never existed in the role's git history: agents are being pointed at a phantom verifier instead of the real one (the molecule suite).

## What Changes

- Move the 21 certificate-domain task files into `tasks/certs/` via `git mv` — file names preserved, no renames, content unchanged except `include_tasks`/`import_tasks` paths.
- Update every include/import to the new paths:
  - `tasks/main.yml`: the six cert-domain includes (`ipa-certs.yml`, `kube-install-join-node.yml`'s cert call stays caller-side, `ipa-kube-admin-credential.yml`, `ipa-pki-swap.yml`, `ipa-cert-renewal.yml`) gain the `certs/` prefix.
  - `tasks/kube-install-join-node.yml` → `certs/kube-node-cert.yml`.
  - `certs/*` files calling the root-shared helper: `_krb_ticket.yml` → `../_krb_ticket.yml`.
  - Files whose callers all move into `certs/` move with them (`_ipa-ca-acl-grants.yml`, `_probe-kubeclusteradm-keytab.yml`, `calico-ca-recovery.yml`), keeping their mutual includes same-folder.
- Boundary decisions (settled during exploration):
  - `ipa-kube-admin-credential.yml` **moves** into `certs/` — the `kubeclusteradm` identity exists to serve cert enrollment/renewal (CSR CN resolves to it; `ipa-cert-renewal.yml` exports its keytab).
  - `admin-user.yml` **stays at root** — it is the user-facing flow (produces the operator's working `admin.conf`, ends with `kubectl get nodes`).
  - `_krb_ticket.yml` **stays at root** — shared by cert and non-cert flows (`delete-ipa-cleanup.yml`, `kube-install-join-node.yml`, `admin-user.yml`).
- Documentation truth pass:
  - Replace the phantom `tests/static_gate.py` "committed gate" claims (role `AGENTS.md`, and the "No dead code" practice in `ansible/roles/AGENTS.md`) with the honest verification proof: a full molecule cycle — `destroy → converge-monorepo → verify-monorepo` (+ reconverge for idempotence) — on the host-OS-matched scenario (macOS→`parallels`, Linux→`kvm`, Windows→`default`).
  - Regenerate the role `AGENTS.md` L3 task-flow graph with `certs/` paths.
  - Update `tasks/` path citations in prose/comments: `defaults/main.yml`, `molecule/kvm/converge.yml`, `molecule/parallels-sequential/converge.yml`.

No behavior, variable, handler, template, or molecule-test-logic changes. Pure `git mv` + include-path rewrites + docs.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — this is a pure refactor with no spec-level behavior change. The existing specs (`ipa-pki-bootstrap`, `ipa-kube-admin-credential`) cite the moved files by bare file name (e.g. `ipa-cert-renewal.yml`), never by `tasks/`-prefixed path, and file names are preserved, so all spec citations remain valid. `skip_specs: true` is set in `.openspec.yaml`.

## Impact

- `tasks/` tree: 21 files moved into `tasks/certs/`; include paths rewritten in `tasks/main.yml`, `tasks/kube-install-join-node.yml`, and the moved files' own includes to root-local helpers.
- Docs: role `AGENTS.md` (L3 graph + static-gate paragraph), `ansible/roles/AGENTS.md` ("No dead code" guard), `defaults/main.yml` and molecule converge comments.
- Runtime behavior: none intended — the move must be behavior-zero, proven by a full molecule cycle (converge green, verify green: nodes Ready, per-pod evidence, PV mounts; reconverge idempotent).
- Git history: preserved for all moved files via `git mv` / `git log --follow`.
