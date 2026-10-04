# Design

## Context

- The role orchestrates FreeIPA + Kubernetes across 3 VMs (molecule `parallels` scenario). Nine cluster operations are currently shell/`kubectl` tasks in six task files.
- Installed toolchain (verified): `kubernetes.core` v6.6.0 (`~/.ansible/collections`), ansible-core 2.21 (`.tox/converge-monorepo`).
- The role **already uses native k8s modules with explicit `kubeconfig:` + `context:`** (`persistent-volume.yml`, `admin-user.yml`) — the pattern is proven on the master in production converge runs.
- `prereq.yml` pip-installs the `kubernetes` Python client on **all hosts** (master and nodes) before any k8s module can run — node-side native usage is dependency-covered.
- Two task files carry false "documented exception" comments claiming no native module accepts an arbitrary kubeconfig path; verified false in v6.6.0 (`args_common.py:69` declares `kubeconfig` as shared `raw` param; `client.py:117-121` loads a file path via `load_kube_config`).

## Goals / Non-Goals

**Goals:**
- Replace all nine shell/kubectl cluster operations with native `kubernetes.core` modules, reusing existing variables (`{{ kube_config_path }}`, `context: kubernetes-admin@kubernetes`).
- Make calico CA-recovery idempotent by construction (fingerprint-gated trigger) per the `ipa-pki-bootstrap` spec.
- Turn the coredns restart into a deterministic hard gate with explicit credentials.
- Preserve each task's existing failure semantics except where explicitly upgraded (coredns).

**Non-Goals:**
- No changes to other roles, the testinfra verifier, or molecule scenario topology.
- No new Python dependencies (`prereq.yml` already covers all hosts).
- `openssl verify -CAfile` chain validation in `ipa-certs.yml` stays shell (legitimate exception — no native module performs chain validation).

## Decisions

**D1 — Native modules accept arbitrary kubeconfig paths.** Verified interface: `kubeconfig` is a shared `raw` param across all k8s_* modules; string values are loaded as file paths. All replacements pass `kubeconfig: "{{ kube_config_path }}"` + `context: kubernetes-admin@kubernetes`, matching the existing `persistent-volume.yml` pattern. *Alternatives rejected:* keeping shell (fragile awk parsing, swallowed failures); exporting `KUBECONFIG` env (implicit, breaks under become/delegate combinations).

**D2 — Rollout restart = strategic-merge annotation patch.** `k8s` with `state: present` on an existing object defaults to strategic merge; a partial spec touching only `spec.template.metadata.annotations['kubectl.kubernetes.io/restartedAt']` is exactly what `kubectl rollout restart` does internally. *Alternatives rejected:* read-modify-write of the full definition (race-prone); keeping `kubectl`.

**D3 — Annotation value strategy (trigger semantics).**
- *calico-ca-recovery*: fingerprint of the current post-swap CA — `slurp` `/etc/kubernetes/pki/ca.crt` on the master, `| hash('sha256')` truncated to 16 chars (`hash` filter verified working in this core). Value is stable per CA → re-converge with unchanged CA is a no-op (spec: "Recovery is idempotent"); a new CA fires the restart. *Alternatives rejected:* per-run timestamp (churns every converge — violates the spec's idempotency scenario); fixed marker string (misses a second CA rotation within one cluster lifetime).
- *coredns*: version-tied constant `calico-{{ calico_cni_version }}` → no-op on re-converge at unchanged CNI; fires on fresh install (no prior annotation) and on CNI upgrade.

**D4 — Rollout completion = native `wait: true` + `wait_timeout`.** Verified in `runner.py:204-210`: the wait runs after **both** create and update (patch) paths; `waiter.py` predicates `daemonset_ready`/`deployment_ready` check exactly the fields `kubectl rollout status` uses (`numberReady == desiredNumberScheduled`, `updatedNumberScheduled == desired`, `observedGeneration` match). New variable `kubernetes_rollout_wait_timeout` (default 300). *Alternatives rejected:* manual `k8s_info` polling with `until` (re-implements what `wait` does); dense per-pod coverage DSL for the wait itself (count-based predicate is equivalent for well-behaved DaemonSets and matches kubectl's own semantics).

**D5 — Node-naming CNI failure via block/rescue.** A failed `until`/timeout task aborts the play before any follow-up diagnostic can run, so the calico patch+wait is wrapped in a `block`; the `rescue` queries pods (`k8s_info`, namespace `calico-system`) and nodes natively and fails with an explicit list of nodes lacking a ready `calico-node` pod (name-prefix match). This satisfies the spec scenario "CNI not ready in time" (error names affected node(s)) — which the current shell loop also does not satisfy.

**D6 — Lease freshness gate.** `k8s_info` on `coordination.k8s.io/v1` Lease `kube-controller-manager` (`kube-system`), `until` age < 90 computed with `lookup('pipe', 'date +%s')` (fresh clock per retry) and `to_datetime`/`strftime('%s')`. Verified: ansible-core 2.21 has **no `now` lookup** (absent from all builtins); `ansible_date_time.epoch` rejected because it is gathered at play start — stale across retries, could let a genuinely stale lease pass the gate.

**D7 — Scheduler readiness gate.** `k8s_info` kind=Pod, namespace `kube-system`, `label_selectors: ['component=kube-scheduler']`, `until` all container statuses ready. v6.x option names are **plural lists** (`label_selectors`/`field_selectors`) — verified against the installed collection, not older docs.

**D8 — Post-swap connectivity verification.** `k8s_cluster_info` (returns `.apis`/`.connection`/`.version` — no `.resources` key; `until` on `version.server`). Each call site keeps its existing failure semantics (best-effort stays best-effort via `failed_when: false` where the original had it).

**D9 — Admin credential injection.** Native `kubeconfig` module (v6.5+): merge a user entry into `/etc/kubernetes/admin.conf` referencing the IPA-signed cert/key by path — same file references `kubectl config set-credentials` wrote, hash-idempotent, PyYAML-only. Drops the `failed_when: false` + `changed_when: False` hacks.

**D10 — Join verification.** `k8s_info` kind=Node, `name={{ inventory_hostname }}`, `kubeconfig=/etc/kubernetes/kubelet.conf`, `until resources | length > 0` (retries/delay preserve the original 40×5s timing). Runs on the node; python client already installed via `prereq.yml`. Preserves the spec "Join verification is independent of master post-processing" (same per-node identity, no admin.conf dependency).

**D11 — Coredns hard gate fixes a latent bug.** The original runs bare `kubectl` with no resolvable kubeconfig at that point in the flow (no `KUBECONFIG` env anywhere in the role; `/root/.kube/config` does not exist until later), and `failed_when: false` swallowed every error — likely a silent no-op on fresh installs. Explicit `kubeconfig:` + `context:` makes it deterministic, and the task now fails converge on timeout instead of best-effort (deliberate semantic upgrade).

## Risks / Trade-offs

- [Coredns behavior change] Fresh installs will actually get the restart, and a stuck rollout now fails converge → Mitigation: that is the task's stated intent; molecule destroy→converge→verify exercises it end-to-end.
- [`wait_timeout` sizing] 300s may be tight on slow Parallels VMs (5GB RAM) → Mitigation: variable is scenario-tunable; timeout failure names the deployment.
- [Strategic merge of a partial spec] Patch touches only template annotations; verified default `merge_type` falls back strategic-merge→merge if unsupported → low risk.
- [`slurp` + hash fingerprint] CA file must be readable by the task user → Mitigation: `become: true`, already used throughout this flow.
- [Option-name drift across collection versions] `label_selectors` plural verified against installed v6.6.0, not docs → re-check if the collection is upgraded.
- [Node-side python client] Verified present via `prereq.yml` pip install on all hosts; a host that skips prereq now fails loudly in `k8s_info` instead of silently falling back to shell.

## Migration Plan

Single change, no state migration: annotation values are new keys added to existing objects (additive); old shell tasks are removed in the same commit. Rollback = revert the commit; leftover annotations on cluster objects are harmless. Verification: molecule `destroy → converge → verify` on the `parallels` scenario, plus a second converge for idempotency spot-checks (coredns no-op at unchanged CNI version; calico recovery no-op at unchanged CA).
