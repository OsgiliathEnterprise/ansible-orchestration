## ADDED Requirements

### Requirement: Profile readiness gate has a dedicated join-scale budget
The node's `kubernetesNodes` profile readiness gate SHALL wait on a dedicated budget (its own retry/delay variables) instead of the generic readiness pair, so scenarios can size it to the master's profile-creation pace on constrained runners without inflating the other gates. On budget exhaustion the failure SHALL name the missing signal and the master-side producer task, and SHALL capture the actual profile list from FreeIPA as evidence.

#### Scenario: Slow master does not spuriously fail the gate
- **WHEN** the master's provisioning runs slower than the local pace (e.g. the CI runner's constrained CPU/RAM) and the profile is created after the generic 40×5 s budget would have elapsed but within the join-scale ceiling
- **THEN** the node passes the gate and proceeds to join

#### Scenario: Profile gate timeout fails with a named diagnosis
- **WHEN** the profile gate exhausts its join-scale budget
- **THEN** the failure output names the missing signal (`kubernetesNodes` profile) and the master-side producer (`tasks/certs/ipa-kubernetes-ca.yml`)
- **THEN** the output includes the `ipa certprofile-find` result captured from the IPA server, so "absent" vs "pattern mismatch" is decidable from the log alone

### Requirement: Node CA material fetches tolerate transient FreeIPA failures
The worker node's fetches of its trust material from FreeIPA (the CA #1 `kubernetes-ca` and CA #2 `kubeclusteradm` certificates) SHALL retry transient failures within a bounded budget, consistent with the retry discipline of the node's other IPA-dependent gates. A persistent failure SHALL fail with a message naming the CA, never masked by retries into a late join timeout.

#### Scenario: Transient IPA API failure during CA fetch
- **WHEN** an `ipa ca-show` retrieval fails on its first attempt because the IPA API is briefly unavailable
- **THEN** the fetch is retried within the bounded budget and the join proceeds once it succeeds
- **THEN** the retry attempts are visible in the task output (retries/delay configured on the task)

#### Scenario: Missing CA fails with a named diagnosis
- **WHEN** a CA retrieval exhausts its retry budget or returns an empty/invalid certificate
- **THEN** the task fails with a message naming the CA (`kubernetes-ca` or `kubeclusteradm`) and the IPA server it was fetched from
- **THEN** the join block does not continue into later gates with missing or partial trust material

### Requirement: Join failure produces a structured per-phase diagnosis
When any phase of the node join block fails, the role SHALL fail with a diagnosis naming the failed phase and the upstream dependency it was waiting on. The generic message *"Node join failed - kubelet not active. Check kubelet logs above."* SHALL NOT be the only output of a failed join, and journal evidence SHALL be bounded to the join block's own execution window rather than a blind tail.

#### Scenario: API gate timeout names the upstream dependency
- **WHEN** the node's API readiness gate (HTTPS healthz against the IPA-signed serving certificate) exhausts its budget
- **THEN** the failure output names the phase (`api-readiness`), the dependency (the master's API server serving the FreeIPA-signed certificate via `tasks/certs/ipa-certs.yml`), and the last probe result
- **THEN** the output includes the kubelet journal captured since the join block started

#### Scenario: Master cert-phase non-completion names the unmet dependency
- **WHEN** the master has not completed its cert phase by the time the node's gate budgets expire (failure inside the phase, or simply slower provisioning than the budget)
- **THEN** the node's failure output explicitly lists "master completed cert phase" among the checked upstream conditions and names it as unmet, instead of only reporting `kubelet not active`

#### Scenario: CI captures post-mortem artifacts on failure
- **WHEN** the kvm molecule converge fails on a node
- **THEN** the CI log contains, for the failing host: `journalctl -u kubelet` since block start, `crictl pods` and `crictl ps` output, the gate probe outputs, `ipa-getcert list`, and the presence/absence of the host and `kubeclusteradm` keytabs

### Requirement: Master bring-up API calls feeding join readiness tolerate transient failures
The master bring-up task that patches cluster state the node join gates depend on (the post-calico coredns restart) SHALL tolerate transient API-server failures within a bounded retry budget, instead of aborting the master chain on the first timeout. Budget exhaustion SHALL fail with a diagnosis naming the phase and the upstream cause.

#### Scenario: Transient 504 during calico bring-up
- **WHEN** the freshly initialized API server answers the coredns restart call or its rollout poll with a 504 because of calico bring-up load on a constrained runner
- **THEN** the operation is retried within the bounded budget and master provisioning continues once it succeeds
- **THEN** the master reaches `kubernetesNodes` profile creation within the node join gate's budget

#### Scenario: Rollout wait accepts only the restarted rollout and fits the join gate budget
- **WHEN** the coredns restart is applied and the rollout wait evaluates readiness
- **THEN** the wait is a resilient poll gated on `observedGeneration >= generation` and `readyReplicas >= replicas`, so it is not satisfied by the pre-patch ReplicaSet
- **THEN** the combined apply and wait budget stays within the node join profile-gate ceiling, so a master still waiting on coredns cannot itself starve the gate it feeds

#### Scenario: Persistent API unavailability fails with a named diagnosis
- **WHEN** the coredns patch apply or the rollout wait exhausts its budget without success
- **THEN** the failure names the phase (annotation apply vs rollout wait), the last API observation, and the upstream cause (calico bring-up / API-server health)
- **THEN** the failure is not an anonymous until-loop exhaustion and the run does not proceed with broken cluster DNS

### Requirement: Coredns restart is gated on this node's CNI readiness using supported module parameters
Before the post-calico coredns restart, the master SHALL wait, within a bounded budget, for its own `calico-node` pod to be Ready, so the restart is not launched into a node whose CNI has not initialized. The readiness query SHALL use only parameters supported by the pinned `kubernetes.core` collection, and its failure output SHALL include the module's own error when the query itself failed.

#### Scenario: Cold image pull delays CNI on a constrained runner
- **WHEN** the calico-node image pull (including the tigera-operator cold pull) takes minutes on a cold CI runner before the pod becomes Ready
- **THEN** the gate waits up to its configured ceiling and the coredns restart proceeds once this node's calico-node is Ready
- **THEN** healthy or warm runs pass the gate as soon as the pod is Ready (ceiling, not floor)

#### Scenario: Broken readiness query self-reports instead of polling empty
- **WHEN** the readiness query fails at the module level (e.g. unsupported parameter names) instead of returning pods
- **THEN** the named fail output carries the module error alongside the pod/phases/container-state evidence, making the query bug distinguishable from a genuine CNI failure in the log alone

#### Scenario: Gate query matches where the operator actually places calico-node
- **WHEN** the gate evaluates this node's calico-node pod
- **THEN** the query is scoped to the namespace the tigera-operator deploys calico-node into (`calico-system`) with label and `spec.nodeName` selectors via the collection-supported plural parameters, and a kube-system-scoped or unsupported-parameter query is a guard-detected regression
- **THEN** the combined calico-gate and rollout-wait budgets stay within the node join profile-gate ceiling, so the master's pre-profile waits cannot starve the gate they feed
