# Proposal

## Why

The role's transient download shuttles run out of fixed folders and fixed-name files — `/run/ipa-ca-fetch` (`kube_idm_ca_fetch_dir`), the per-node `/tmp/kube-node-ca*.crt` fetches on the shared idm host, `/tmp/kube-api-gate-anchor.crt`, `/tmp/kube-admin-enroll.{csr,crt}`, `/tmp/ipa_*_ca_profile.cfg`, `/tmp/helm-*.tar.gz` + `/tmp/linux-<arch>/`. These fixed paths were a trade made during the steady-state idempotence work specifically to avoid `ansible.builtin.tempfile`'s always-changed create/delete pair (documented in `tasks/certs/ipa-certs.yml`, `defaults/main.yml`, `tasks/kube-install.yml`). The trade has three costs: the two CA downloads re-execute on **every** converge under a blanket `changed_when: false` (masked change reporting on file-writing tasks, against the monorepo idempotency policy), concurrent joins would collide on identical fixed paths on the shared idm host, and shuttle artifacts linger after runs (the profile `.cfg` scratch files are never removed at all). A tempfile is acceptable when it is minted only inside a block gated on real drift/state: a steady-state reconverge never invokes it, and every invocation of it is a real change — truthful by construction.

## What Changes

- Add a read-only drift gate to `tasks/certs/ipa-certs.yml` comparing the fingerprints of the IPA-published CAs (CA #1 `kubernetes-ca`, CA #2 `kubeclusteradm`) against the master's installed copies; the fetch-and-shuttle block (tempfile, two `ipa ca-show` downloads, slurps, master-side installs) runs only when a copy is missing or its fingerprint drifted.
- Replace the fixed fetch folder `kube_idm_ca_fetch_dir` (`/run/ipa-ca-fetch`) with a per-run root-only `ansible.builtin.tempfile` directory on idm, minted inside the gated block and removed after the slurps; drop the two blanket `changed_when: false` on the `ipa ca-show` downloads (they now run only on drift, so they report truthfully); delete the default variable and add an idempotent legacy sweep of `/run/ipa-ca-fetch` (precedent: the `/tmp/kubeclusteradm.keytab` sweep in `tasks/certs/ipa-cert-renewal.yml`).
- Convert the remaining fixed-name temporary download/staging files to per-run tempfiles, each minted only inside a block that is already gated and skipped at steady state:
  - `tasks/kube-install-join-node.yml`: the two CA fetches on the shared idm host (kills the concurrent-join name collision) and the node-local `/tmp/kube-node-ca-expected.crt` comparison file.
  - `tasks/admin-user.yml`: the `/tmp/kube-admin-enroll.{csr,crt}` CSR-staging/enrollment pair on idm.
  - `tasks/certs/ipa-ca-profile.yml`: the profile-import scratch `.cfg` becomes an include-owned tempfile inside the profile-missing block; the `ipa_ca_profile_file` include input and its four `/tmp/ipa_*_ca_profile.cfg` passings in `tasks/certs/ipa-kubernetes-ca.yml` are removed (today these files are never cleaned on idm).
  - `tasks/certs/ipa-certs.yml` + `tasks/certs/ipa-pki-swap.yml`: the transient gate anchor `/tmp/kube-api-gate-anchor.crt` becomes a registered run-scoped tempfile consumed by the healthz gate and deleted by name-at-registration at end of swap.
  - `tasks/drain-and-reset.yml`: the helm tarball `/tmp/helm-*.tar.gz` and its `/tmp/linux-<arch>/` extraction folder move into a tempdir created only when helm is absent (the block's existing `stat` gate).
- Update the verify assertion that hardcodes the fixed anchor name (`molecule/default/tests/test_master.py`) to a prefix-based no-residue check, and the spec text in `ipa-pki-bootstrap` that names the fixed anchor path.
- Out of scope (recorded, not blocking): `/run/kube-nfs-pv/pv.yml` (rendered PV manifest, not a download); `kube-install.yml`'s `calico_conf_dir` (content-idempotent rendered-template copy into a durable kubernetes home — a fixed folder, not a download shuttle; follow-up candidate); the `/tmp/kubeclusteradm.keytab` legacy-sweep task (kept; already an honest idempotent `state: absent`); in-shell `mktemp` uses inside `command:`/`shell:` scripts (legitimate shell scratch).

## Capabilities

### New Capabilities

- `transient-shuttle-hygiene`: every transient download/staging shuttle uses per-run unique tempfile paths, minted only inside gated blocks that are skipped at steady state (zero tempfile tasks on a no-op reconverge); the CA fetch shuttle runs only on fingerprint drift; shuttles leave no residue in `/tmp` or `/run` after converge; concurrent delegated fetches on the shared idm host cannot collide.

### Modified Capabilities

- `ipa-pki-bootstrap`: the "Kubeadm self-signed CA fully retired after the swap" requirement hardcodes the transient gate anchor as `/tmp/kube-api-gate-anchor.crt`; after this change the anchor is a run-scoped tempfile — deletion and trust-window wording become name-independent.

## Impact

- **Code**: `tasks/certs/ipa-certs.yml`, `tasks/kube-install-join-node.yml`, `tasks/admin-user.yml`, `tasks/certs/ipa-ca-profile.yml`, `tasks/certs/ipa-kubernetes-ca.yml` (call sites), `tasks/certs/ipa-pki-swap.yml`, `tasks/drain-and-reset.yml`, `defaults/main.yml`, `molecule/default/tests/test_master.py`.
- **Variable surface**: role default `kube_idm_ca_fetch_dir` is removed (its only consumer was the CA-fetch block); the `ipa_ca_profile_file` input of the `ipa-ca-profile.yml` include is removed (internal scratch, no external caller). Neither is used by molecule inventories, scenarios, or sibling roles.
- **Change reporting**: two downloads lose blanket `changed_when: false`; they run only on drift, so steady-state reconverge still reports zero changed tasks. The read-only fingerprint probe keeps `changed_when: false` with the AGENTS-required comment.
- **Verification**: full molecule cycle `destroy → converge-monorepo → verify-monorepo` plus reconverge for idempotence on the host-OS-matched scenario (macOS→`parallels`), per the role's standing gate; the reconverge must show the CA-fetch block and all tempfile tasks skipped with zero changed.
