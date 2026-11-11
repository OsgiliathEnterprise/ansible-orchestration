# Design

## Context

`tasks/` is a flat directory of 42 files; 21 of them form the certificate/PKI domain (CA provisioning primitives, the `ipa-certs.yml` orchestration tree, node cert enrollment, PKI swap + Calico recovery, renewal timers). The include graph was mapped during exploration:

- Root callers into the cert domain: `tasks/main.yml` (6 includes), `tasks/kube-install-join-node.yml` (→ `kube-node-cert.yml`).
- Cert-domain files call two root-local shared helpers: `_krb_ticket.yml` (~10 call sites inside cert files) and `_probe-kubeclusteradm-keytab.yml` (2 call sites).
- `_krb_ticket.yml` is also called by non-cert files (`delete-ipa-cleanup.yml`, `kube-install-join-node.yml`, `admin-user.yml`); `_probe-kubeclusteradm-keytab.yml`'s two callers (`ipa-cert-renewal.yml`, `ipa-kube-admin-credential.yml`) are both cert-domain.

Constraints:
- Pinned toolchain: `ansible==14.0.0` (ansible-core 2.19).
- `import_tasks` resolves at parse time (catchable by `--syntax-check`); `include_tasks` resolves at run time (only a full converge exercises it). `main.yml` mixes both.
- Both spec files that cite task files (`ipa-pki-bootstrap`, `ipa-kube-admin-credential`) cite **bare file names**, never `tasks/`-prefixed paths — and no file is renamed, so spec citations survive the move.
- `.gitignore` covers `.ansible/`, which contains a **stale copied install** of the role (`ansible-galaxy`-style tree from a standalone run); monorepo tox envs resolve roles from the source tree via `ANSIBLE_COLLECTIONS_PATH={toxinidir}/../community-collections`, but a standalone run could silently converge the stale copy.
- The documented "committed gate" `tests/static_gate.py` never existed in git history (verified with `git log --all --follow`). The real verification proof is the molecule suite on the host-OS-matched scenario (macOS→`parallels`, Linux→`kvm`, Windows→`default`), with `verify` mandatory.

## Goals / Non-Goals

**Goals:**
- The cert domain is one discoverable folder (`tasks/certs/`) whose files are exactly the cert-domain set; the folder boundary is stable under the invariant below.
- The move is behavior-zero: identical task order, identical task names, identical semantics; git rename detection preserved.
- Documentation states the true verification mechanism (molecule cycle), not the phantom static gate.

**Non-Goals:**
- No renames of any task file (naming cleanups like `admin-user.yml`'s misnomer are deferred; bare-name spec citations and `git log --follow` both depend on name stability).
- No task content changes beyond include/import path strings.
- No change to defaults variables, handlers, templates, `files/` scripts (including `kube-cert-renew.sh`, which references no task path), or molecule test logic.
- No recreation of `tests/static_gate.py` — the molecule suite is the proof; the docs are corrected to say so.

## Decisions

### D1 — One folder `tasks/certs/`, 21 files, no nesting
A single folder rather than `certs/` + `certs/ca/` (CA primitives): 21 files is one folder's worth, and the five CA primitives each have exactly two callers, both cert files — a second level adds indirection without discoverability gain. Alternative considered and rejected: splitting into `certs/` + `ca/` + `renewal/` (over-partitioning for this size).

### D2 — Folder membership by purpose, with a helper-moves-with-callers invariant
Membership reflects the domain a file serves, not its artifact type:

- `ipa-kube-admin-credential.yml` **moves** — the `kubeclusteradm` Kerberos identity exists to serve cert enrollment/renewal (the CSR CN resolves to it; `ipa-cert-renewal.yml` exports its keytab), even though it contains zero certificate code.
- `admin-user.yml` **stays at root** — it is the user-facing flow (produces the operator's working `admin.conf`, ends with `kubectl get nodes`), despite being mostly cert mechanics.
- Shared helpers follow this invariant: **a helper moves into `certs/` iff every caller is in `certs/`**. Result: `_ipa-ca-acl-grants.yml`, `_probe-kubeclusteradm-keytab.yml`, `calico-ca-recovery.yml` move (all callers cert-domain); `_krb_ticket.yml` stays (callers in `delete-ipa-cleanup.yml`, `kube-install-join-node.yml`, `admin-user.yml` outside the domain).

Alternative considered: artifact-type split (X.509 files in `certs/`, Kerberos files elsewhere) — rejected because it scatters the cert story across two credential systems and leaves `ipa-cert-renewal.yml`'s keytab probe cross-boundary for no benefit.

### D3 — Explicit `../` spelling for cross-boundary includes
After the move there are exactly two crossing edge classes:

- Root → folder: `main.yml`'s six cert includes and `kube-install-join-node.yml` → `certs/kube-node-cert.yml` use `certs/<file>.yml`.
- Folder → root: cert files → `_krb_ticket.yml` use `../_krb_ticket.yml`.

ansible-core resolves role task includes relative to the including file's directory with a role-`tasks/`-root fallback; both spellings would likely work, but the explicit `../` makes every cross-boundary edge greppable and reviewable (a `grep -rn "\.\./" tasks/certs/` enumerates the whole outbound seam). Same-folder includes are left untouched.

### D4 — Verification proof is the molecule cycle, stated in both AGENTS.md files
Replace the `tests/static_gate.py` claims with: full cycle `destroy → converge-monorepo → verify-monorepo` (+ reconverge for idempotence) on the host-OS-matched scenario; `verify` green (all nodes Ready, per-pod evidence, PV mounts) is the gate. Hygiene rules (no orphans, ticketing conventions) remain binding as *review* criteria enforced by that cycle — not by a script. Fixes land in the role `AGENTS.md` ("Committed gate" paragraph, L3 graph) and `ansible/roles/AGENTS.md` ("No dead code" example).

### D5 — Purge the stale `.ansible/collections` copy as part of the change
Delete the gitignored `.ansible/collections/ansible_collections/tcharl/ansible_orchestration/` copy before verification so no run can reference the pre-move tree; the monorepo tox path (`ANSIBLE_COLLECTIONS_PATH` → `community-collections`, roles from source) is unaffected.

### D6 — Fresh-clone create flakiness is an environment issue, not a refactor regression
Three fresh `destroy → create` runs on this macOS host failed identically at the vagrant-parallels provider's boot wait (`Timed out while waiting for the machine to boot`, ~390s) even though the guests booted, got DHCP addresses (`prlctl exec` confirmed), and accepted SSH — the provider never learned the guest IP (`prlctl list` shows `IP_ADDR: -`), so Vagrant's IP probe timed out. Because `create.yml` writes the driver's `instance_config.yml` only `when: server is changed`, the failed creates left it `{}` and prepare then failed UNREACHABLE (hostname-only inventory). Verification therefore ran against the four already-booted VMs with `instance_config.yml` populated by hand (list of `instance/address/user/port/identity_file` from `vagrant ssh-config`); create itself is orthogonal to a tasks-file move. Caveat of the live-VM path: those VMs were booted with `vagrant up --no-provision`, so Vagrant's hostname provisioning never ran and the clients kept the base-box hostname `client.osgiliath.test` — all three then tried to join IPA under that one name (prepare failed: `host with name "client.osgiliath.test" already exists`). Remediation before converge: `ipa-client-install --uninstall -U` + `hostnamectl set-hostname <fqdn>` on each client, `ipa host-del client.osgiliath.test` on the IPA server. Follow-up (separate from this change): investigate parallels provider IP reporting (or raise `config.vm.boot_timeout`) before requiring a fresh-clone full cycle.

## Risks / Trade-offs

- [Typo'd include path in an `include_tasks` (runtime-resolved) survives `--syntax-check`] → Full converge on the host-OS scenario executes every cert include (the cert phase is unconditional for masters, node-cert path for workers); plus a scripted post-move audit: every `include_tasks`/`import_tasks` target in `tasks/**/*.yml` resolves to an existing file.
- [Ansible's role-tasks-root fallback masks a wrong relative path, so the run passes while the include is accidentally fragile] → The `../` spelling (D3) plus the resolution audit removes reliance on fallback behavior.
- [Stale `.ansible/collections` copy converges instead of the moved source] → D5 purge before verification; risk only affects standalone runs (monorepo tox resolves from source).
- [Prose path citations rot elsewhere (comments in `defaults/main.yml`, molecule converge files)] → Exact inventory exists from exploration (3 files, comment lines only); updated in the doc pass; a closing `grep -rn "tasks/<moved-file>" --include="*.yml" --include="*.md"` over the role (excluding `openspec/changes/archive/`) must come back empty.
- [Git rename detection lost if a moved file's content changes too much] → Each moved file changes only its include lines (≤ ~10 lines); rename detection (`git log --follow`, `--stat -M`) verified in the audit task.
- [Trade-off accepted] `admin-user.yml` stays at root although ~90% of its content is cert mechanics — deliberate: it is the operator-facing artifact producer, and moving it would split the `admin.conf` story across the boundary while making root's `main.yml` entry asymmetric.

## Migration Plan

1. `git mv` the 21 files into `tasks/certs/` (one commit-level move, no renames).
2. Rewrite include/import paths per D3 (`main.yml`, `kube-install-join-node.yml`, cert files' `_krb_ticket.yml` calls).
3. Doc pass per D4 + comment/path citations (`defaults/main.yml`, both molecule `converge.yml` files, role + monorepo AGENTS.md).
4. `rm -rf .ansible/collections/ansible_collections/tcharl/ansible_orchestration` (D5).
5. `ansible-playbook --syntax-check` on the converge playbook (catches parse-time `import_tasks` breakage).
6. Full molecule cycle on the host-OS scenario; `verify` mandatory; reconverge for idempotence.
7. Rollback: single `git revert` — pure move + docs, no VM-side state, no data migration.

## Open Questions

None — boundary calls, include spelling, and the verification mechanism are all settled above.
