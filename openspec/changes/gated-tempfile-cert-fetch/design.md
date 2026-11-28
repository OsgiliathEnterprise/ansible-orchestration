# Design

## Context

See proposal.md - Why. The current state that shapes the approach:

- `tasks/certs/ipa-certs.yml` unconditionally, on every converge: creates the fixed root-only dir `{{ kube_idm_ca_fetch_dir }}` (`/run/ipa-ca-fetch`, `defaults/main.yml:117-120`) on idm, runs two `ipa ca-show --certificate-out=` downloads under blanket `changed_when: false`, slurps both files, and installs them on master via content-idempotent `copy`. Nothing ever removes the shuttle files; the dir self-clears only on reboot.
- Downstream consumers (`verify ca.crt.new fingerprint`, the bundle `slurp`s, the anchor build) all read the **installed** master-side copies, not the idm shuttle — so the fetch only matters when the installed copies are absent or differ from the published CAs.
- The idm-host fetches in `tasks/kube-install-join-node.yml` (`/tmp/kube-node-ca.crt`, `/tmp/kube-node-ca-clusteradm.crt`) and the staging pair in `tasks/admin-user.yml` (`/tmp/kube-admin-enroll.{csr,crt}`) run inside blocks already gated on real state (`not kube_node_joined.stat.exists`, `not kube_admin_cert_stat.stat.exists`) — steady state skips them; only their fixed names are the problem (collision on the shared idm host + residue).
- `tasks/certs/ipa-ca-profile.yml` writes `{{ ipa_ca_profile_file }}` (four fixed `/tmp/ipa_*_ca_profile.cfg` names passed by `ipa-kubernetes-ca.yml`) inside its already-gated `rc == 2` profile-missing block and never deletes it.
- The gate anchor `/tmp/kube-api-gate-anchor.crt` is built only when `kube_gate_anchor_needed` is true, consumed by the healthz `uri` `ca_path`, deleted at end of swap (`tasks/certs/ipa-pki-swap.yml`), and asserted absent by `molecule/default/tests/test_master.py:348` on its fixed name.
- `tasks/drain-and-reset.yml` downloads the helm tarball and extracts it under fixed `/tmp` names inside its existing `when: not _helm_bin_stat.stat.exists` gate, leaving residue.
- The role's standing policy (monorepo AGENTS.md): blanket `changed_when: false` only on provably read-only tasks (documented); prefer native modules (`community.crypto.x509_certificate_info` for cert fields, `ansible.builtin.tempfile` over shell `mktemp`); `ansible.builtin.tempfile` always reports changed — which is exactly why the previous idempotence work replaced tempfiles with fixed paths.

## Goals / Non-Goals

**Goals:**

- Per-run unique paths for every temporary download/staging artifact; no fixed shuttle folders or fixed shuttle file names.
- Tempfile tasks appear only inside gated blocks that skip at steady state, so a no-op reconverge executes zero tempfile tasks (the "only when necessary" rule — see `transient-shuttle-hygiene` spec).
- The CA fetch shuttle runs only on fingerprint drift; its downloads report change truthfully.
- No residue after a successful converge, on idm or the kube hosts; legacy fixed-path artifacts swept to a no-change steady state.
- Concurrent delegated fetches on the shared idm host cannot collide.

**Non-Goals:**

- No change to the Kerberos ticketing conventions (`_krb_ticket.yml`, scratch caches under `kube_scratch_cache_dir` stay — ticket caches are credentials with a stable naming convention, not download shuttles).
- No change to the CA bundle semantics, anchor trust-window logic, gate budgets, or failure-diagnosis messages' meaning (only their paths become registered).
- Out of scope, recorded: `/run/kube-nfs-pv/pv.yml` (rendered manifest, not a download), `kube-install.yml` `calico_conf_dir` (fixed folder but a durable content-idempotent template copy, not a download), the `/tmp/kubeclusteradm.keytab` legacy-sweep task (kept), in-shell `mktemp` inside existing `command:`/`shell:` scripts.

## Decisions

### D1: Drift gate = read-only fingerprint comparison, reusing the existing normalization idiom

Before the fetch block in `tasks/certs/ipa-certs.yml`:

- Installed side: a `stat` pair over `{{ kubernetes_certificates_path }}ca.crt.new` and `...ca.crt.kubeclusteradm` (a missing file means "drifted" without a probe failure), then one read-only `openssl x509 -noout -fingerprint -sha256` shell per installed copy. (`community.crypto.x509_certificate_info` exposes certificate *fields*, not fingerprints, so the "prefer native" table cannot apply to the fingerprint comparison itself; the openssl idiom is the one already proven by the existing `verify ca.crt.new fingerprint` task.)
- Published side: one idm-delegated read-only shell per CA. `ipa ca-show` emits PEM **only** via `--certificate-out` — plain and `--raw` stdout print a labelled base64 DER attribute that `openssl x509` cannot parse ("Could not find certificate from <stdin>") — so the probe exports with `--certificate-out` to a shell-local `mktemp` scratch (0600, `trap`-removed on exit) and fingerprints that file through the **same** `openssl x509 -noout -fingerprint -sha256 | tr -d ':' | tr '[:upper:]' '[:lower:]'` normalization the existing `verify ca.crt.new fingerprint` task uses, so both sides produce identical strings. The CLI's entry-attribute stdout (printed even with `--certificate-out`) is silenced (`>/dev/null`) so the registered stdout holds **only** the fingerprint — un-suppressed, the attribute dump made the comparison never match and the fetch block ran on every converge. `changed_when: false` with the AGENTS-required comment (read-only against IPA state; the scratch is ephemeral, same class as the in-shell mktemp usages already accepted in the role).
- `set_fact kube_ca_fetch_needed: true` when either CA is missing or fingerprints differ. A probe task that fails (rc != 0) **fails the task** — it must not silently mean "fetch": a broken probe would defeat the gate. (Fail-open would reintroduce unconditional fetches.)
- *Alternative considered:* fetch-then-compare (download every time, gate only the install). Rejected: keeps the downloads — the thing being fixed — on every converge.
- *Alternative considered:* piping `ipa ca-show` stdout (plain or `--raw`) through openssl. Rejected after the first converge proved it unworkable: stdout is a labelled base64 DER attribute dump, not PEM/DER, and label- or whitespace-stripping pre-filters are fragile against CLI output formatting; `--certificate-out` is the CLI's only real PEM path.

### D2: Gated shuttle with one idm tempdir (D1 block, `when: kube_ca_fetch_needed | bool`)

Inside the gated block: one `ansible.builtin.tempfile` (`state: directory`, root, delegated to idm; the module takes no `mode` — `mkdtemp` creates it root-owned 0700 by default) registered; the two `ipa ca-show --certificate-out=<tmp>/...` shells (keep `set -o pipefail`, keep `env: KRB5CCNAME` ticket hygiene — **drop the blanket `changed_when: false`**: the block runs only on drift, so changed-on-run is truthful); both `slurp` tasks; the two master-side install `copy: content=` tasks; and a final `file: state: absent` on the registered tempdir. Fetching both CAs whenever either drifted (rather than per-CA fetches) keeps the block a single unit and is free — `ipa ca-show` is cheap and the installs are content-idempotent.
- *Why one directory and not two `tempfile` files?* One create/delete pair, both artifacts always used together, and per-run uniqueness covers both files.
- *Why is `tempfile` reporting changed acceptable?* Inside a drift-gated block, running *is* a real transition; there is no steady-state exposure (spec scenario "No-op reconverge mints no tempfiles").

### D3: Legacy `/run/ipa-ca-fetch` sweep lives next to its former consumer

One `file: state: absent` (delegated to idm, root) at the top of the fetch section of `ipa-certs.yml`, documented like the `/tmp/kubeclusteradm.keytab` sweep precedent (`tasks/certs/ipa-cert-renewal.yml:164-173`): `state: absent` is idempotent by construction, so a real removal reports changed and steady state reports ok — no suppression. Delete the `kube_idm_ca_fetch_dir` default and its `defaults/main.yml` comment block (grep confirms its only consumers are `ipa-certs.yml`; no molecule/scenario/sibling-role usage).
- *Alternative considered:* the `tasks/requirements.yml` superseded-artifact sweep (which sweeps old ccache names). Rejected: requirements.yml runs on play targets + delegated idm for the ticket dir; this artifact belongs to exactly one code path — keeping the sweep where the code lived makes the ownership reviewable.

### D4: Node-join fetches — per-run tempdir on idm, read-only query keeps documented `changed_when: false`

Inside the existing `not kube_node_joined` block of `tasks/kube-install-join-node.yml`: `tempfile` (directory, 0700, delegated to idm) at the top of the fetch sub-flow; both `ipa ca-show` fetches target `<tmp>/ca.crt` / `<tmp>/ca-clusteradm.crt`; slurps read from those paths; a `file: state: absent` removes the registered tempdir after the last slurp. Keep `changed_when: false` **with the documenting comment** on these two fetches: they are retry-loop readiness queries (`until: rc == 0`, `failed_when: false` + named `CA_FETCH_TIMEOUT` fail task), strictly read-only against IPA, writing only into the run-owned ephemeral dir (same class as the scratch ticket caches). The join block itself reports the real transition. Update the two `CA_FETCH_TIMEOUT` fail messages to name the registered path instead of the fixed name. Each joining node gets its own tempdir — the concurrent-join collision disappears.
- Node-local `diff -q` comparison file: `tempfile` (state: file) on the node registered; the expected-content `copy` writes to `.path`; the diff shell is unchanged; the cleanup task removes the registered path.
- *Alternative considered:* comparing base64 content in Jinja and dropping the diff file entirely. Rejected: the retry loop must re-read the **installed** file each pass (a concurrent remap is the race it guards); keeping `diff -q` on a temp path is the minimal delta.

### D5: Admin enrollment staging — include-local tempdir on idm

Inside the existing `not kube_admin_cert_stat.stat.exists`-gated flow of `tasks/admin-user.yml`: `tempfile` (directory, 0700, delegated to idm) registered; stage the CSR at `<tmp>/enroll.csr`; `ipacert` `csr_file: <tmp>/enroll.csr` / `certificate_out: <tmp>/enroll.crt`; slurp the cert; the existing "clean up staged temp files" task becomes `file: state: absent` on the registered tempdir, guarded by the registered fact being defined (steady state: never minted, never deleted, zero changed).

### D6: Profile import scratch owned by `ipa-ca-profile.yml`

Drop the `ipa_ca_profile_file` include input and the four `/tmp/ipa_*_ca_profile.cfg` passings in `tasks/certs/ipa-kubernetes-ca.yml` (the include is consumed only there). Inside the existing `rc == 2` profile-missing block: `tempfile` (state: file, `prefix: profile-<id>-`, `suffix: .cfg`, delegated to idm) registered; `certprofile-show --out <tmp>`; `lineinfile` on `<tmp>`; `certprofile-import --file <tmp>`; then `file: state: absent` on the registered path. Block is already gated on profile-absence, so the scratch is minted only when needed and — unlike today — never lingers on idm.

### D7: Gate anchor becomes a registered run-scoped tempfile

In `tasks/certs/ipa-certs.yml`, inside the existing `when: kube_gate_anchor_needed | bool` build task's flow: `tempfile` (state: file, `prefix: kube-api-gate-anchor-`, `suffix: .crt`) registered as `kube_gate_anchor_tmp`; the `copy: content=` writes to `.path`; the healthz `uri` consumes `ca_path: "{{ kube_gate_anchor_tmp.path if kube_gate_anchor_tmp is not skipped and kube_gate_anchor_tmp.path is defined else kubernetes_certificates_path + 'ca-bundle.crt' }}"` — the old-cert-window fallback semantics are unchanged, only the path source. In `tasks/certs/ipa-pki-swap.yml`, the end-of-swap loop drops the fixed `/tmp/kube-api-gate-anchor.crt` item and deletes the registered `kube_gate_anchor_tmp.path` when defined (the fact survives across `include_tasks` in the same master play; on repair paths that reach the swap without the anchor flow, the guard makes it a no-op). Update `molecule/default/tests/test_master.py:348` from the fixed-path assert to a prefix no-residue assert (`/tmp` must contain no entry starting with `kube-api-gate-anchor-`).
- *Alternative considered:* keep the fixed name since the build is already gated. Rejected: the user's request is precisely about fixed names, and the prefix keeps the residue assertion as strong as before.

### D8: Helm shuttle becomes a gated tempdir

In `tasks/drain-and-reset.yml`, inside the existing `when: not _helm_bin_stat.stat.exists` set: `tempfile` (directory) registered `_helm_tmp` (same `when`); `get_url` dest `<_helm_tmp.path>/helm.tar.gz`; `unarchive` `dest: <_helm_tmp.path>`; `copy` `src: <_helm_tmp.path>/linux-<arch>/helm`; then `file: state: absent` on the registered dir (same gate + defined-guard). Steady state (helm present): every task skipped, zero changed, no `/tmp/helm-*` or `/tmp/linux-*/` residue.

### D9: Change-reporting policy for the new task shapes

- `ansible.builtin.tempfile` / cleanup `file: state: absent` on registered temp paths: no `changed_when` overrides — module-native, and they only execute inside gates that mean "real work".
- Read-only `ipa` query tasks (published-fingerprint probes; node-join fetch retry loops; existing profile-exists check): `changed_when: false` **with a one-line comment** stating the read-only justification (AGENTS requirement).
- The two drift-gated `ipa-certs.yml` downloads: no `changed_when` (shell's own changed) — truthful because D1's gate makes run == drift.
- Every `ipa`/`ipacert` consumer keeps its `env: KRB5CCNAME` ticket hygiene unchanged.

## Risks / Trade-offs

- [Fingerprint string mismatch between probe and installed-file comparison (formatting)] → Both sides use the identical `openssl ... | tr -d ':' | tr '[:upper:]' '[:lower:]'` normalization already proven in the `verify ca.crt.new fingerprint` task; molecule verify is the gate.
- [Probe shell can fail for reasons other than drift (e.g. `ipa ca-show` error mid-CA-creation)] → The probe fails the task with a named message; it never silently opens the fetch gate (fail-open would restore the always-fetch behavior this change removes).
- [Registered anchor fact undefined on repair paths (`steady-state-idempotence` "Repair paths bypass gates")] → The swap-side deletion guards on the registered fact being defined; no fixed path remains, so a skipped build leaves nothing to sweep.
- [Mid-block failure leaks a tempdir on idm/master] → The next converge mints a fresh path (no correctness dependency); leaked dirs are root-only 0700 under `/tmp`/`/run` and clear on reboot; acceptable for a volatile dev/test estate and cheaper than a `block/rescue` around every shuttle.
- [`kube_idm_ca_fetch_dir` removed while an inventory still overrides it] → Harmless unused-variable warning; grep shows no inventory/scenario/sibling usage.
- [Prefix-based residue test could pass despite a leaked differently-named artifact] → The prefix is role-specific and the tempfiles are always minted with that prefix; any leaked file matches and fails the assert.
- [Extra task count (probes) on every converge] → Two read-only delegated commands; negligible vs. the two downloads + directory task they replace on every converge today.

## Migration Plan

Purely internal task reshaping plus one default removal; rollback is a straight revert of the touched files. Existing VMs converge cleanly: the D3 sweep removes `/run/ipa-ca-fetch`, and the legacy keytab sweep already covers the old `/tmp` keytab. Verification: full molecule cycle `destroy → converge-monorepo → verify-monorepo` plus reconverge for idempotence on the host-OS-matched scenario (macOS → `parallels`), with `verify` green as the gate; the reconverge must show the CA-fetch block skipped (fingerprints matched) and zero tempfile tasks executed.

## Open Questions

None. (Probe failure semantics, per-CA vs joint fetch, and the registered-fact guards are resolved above; the testinfra prefix assertion form is pinned in D7.)
