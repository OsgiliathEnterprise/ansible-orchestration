# Proposal: principals-in-place

## Why

Kerberos ticketing and certificate negotiation in this role violate four invariants the role is supposed to hold: CAs are negotiated from idm (mostly true today), but **certificates are negotiated by whoever happens to hold an admin ticket, not by the node that will use them**; the kinit to fetch something from idm **for** a node runs on idm as admin instead of **on** that node; and tickets live in flat dotfiles under world-writable `/tmp` whose names encode the calling task file rather than the principal. Meanwhile the runtime renewal script (`templates/kube-cert-renew.sh.j2`) already implements the correct model — each host `kinit`s with its **own** host keytab and self-enrolls its **own** certificate. Provisioning should converge toward that steady state, not the other way around.

## What Changes

- **Node self-enrollment**: each worker generates its private key and CSR **locally** (community.crypto on the node — `python3-cryptography` is already installed on all hosts by `prereq.yml`) and self-enrolls its node client certificate with a ticket minted from **its own** `/etc/krb5.keytab` host principal. The master no longer mints node keys/CSRs, and the CSR/key are no longer shuttled master → control node → idm.
- **Master self-enrollment**: master-side component client certs (front-proxy, controller-manager, scheduler — already renewed this way by the runtime script) are provisioned authenticated with the **master's own host keytab ticket**, mirroring the runtime flow, instead of admin-password module calls running un-delegated on the master.
- **Ordering fix (enabler)**: the CA-ACL host grants (`kubernetes-ca-acl`, `kubeclusteradm-acl`) currently run late in `ipa-cert-renewal.yml` (master play) but are a precondition for node/master self-enrollment, which runs earlier. The grants move into the CA provisioning chain on idm, before any node join. `usercat=all` does not cover hosts, so without this a fresh converge cannot self-enroll — today the admin-ticket-on-idm workaround silently compensates.
- **Cache naming/placement convention**: provisioning scratch tickets move from `/tmp/.*.ccache` dotfiles (named after the calling task file) to `/run/krb5cc/<principal>.<purpose>.ccache` (tmpfs, root-only `0700` dir, still pre-cleared + `community.general.krb_ticket`).
- **Runtime credential hygiene**: the `kube-cert-renew` service gets `StateDirectory=kube-cert-renew` + `Environment=KRB5CCNAME=FILE:/var/lib/kube-cert-renew/ccache` so the timer never touches the ambient `/tmp/krb5cc_0`; the `kubeclusteradm` keytab on the IPA server moves from `/tmp/kubeclusteradm.keytab` to `/var/lib/kube-cert-renew/kubeclusteradm.keytab` (0600).
- **Realm-password confinement**: un-delegated `freeipa.ansible_freeipa` module calls that pass `ipaadmin_password` to the master are migrated to the existing scratch-ticket convention (delegated to idm, `env: KRB5CCNAME`), shrinking the set of machines that ever see the realm admin password to the control node and idm.
- **Dead-code removal**: the sacrificial host-keytab probe in `ipa-certs.yml` (registered, never consumed) is deleted or made honest.

Non-breaking for cluster operation: certificate subjects, CAs, profiles, and the two-CA trust model are unchanged; only *who negotiates* and *where credentials live* change.

## Capabilities

### New Capabilities

None — this change re-homes existing behavior under the four invariants.

### Modified Capabilities

- `kerberos-ticketing`: scratch-cache location/naming moves to `/run/krb5cc/<principal>.<purpose>.ccache`; certificate enrollment authenticates as the **owning host's own principal** (keytab ticket minted on that host) instead of an admin ticket on idm; CSR/key shuttling is eliminated; realm admin password is confined to control node + idm.
- `kube-node-join`: the worker node client certificate is generated **and** enrolled on the node itself with its own host keytab ticket against CA #2 (`kubeclusteradm`), replacing the current text that has the key/CSR "generated for that node" (in fact by the master) and the stale `ca=kubernetes-ca` claim.
- `ipa-pki-bootstrap`: CA-ACL host grants for the kube hosts become a pre-join step of the CA chain on idm (precondition for self-enrollment), not a late master-play task.
- `kube-cert-renewal`: the timer service authenticates into a unit-scoped credential cache under its `StateDirectory` instead of the ambient root ticket cache; the `kubeclusteradm` keytab lives in the unit state dir (0600), not `/tmp`.
- `ipa-kube-admin-credential`: keytab probe/verification paths follow the keytab off `/tmp` on the IPA server.

## Impact

- **Task files**: `tasks/kube-node-cert.yml` (rewritten), `tasks/kube-install-join-node.yml`, `tasks/ipa-certs.yml`, `tasks/ipa-kubernetes-ca.yml`, `tasks/ipa-kubeclusteradm-ca.yml`, `tasks/ipa-api-server.yml`, `tasks/ipa-front-proxy.yml`, `tasks/kube-apiserver-kubelet-client.yml`, `tasks/ipa-controller-manager-client.yml`, `tasks/ipa-scheduler-client.yml`, `tasks/ipa-kube-admin-credential.yml`, `tasks/admin-user.yml`, `tasks/ipa-cert-renewal.yml`, `tasks/ipa-ca-acl-host.yml`, `tasks/main.yml` (ordering).
- **Templates**: `templates/kube-cert-renew.service.j2`, `templates/kube-cert-renew.sh.j2` (cache env, keytab path).
- **Defaults**: new vars for the scratch-cache dir, cache naming, and the idm-side keytab dir.
- **Specs**: five capability deltas (above); archived via the usual `/opsx-archive` flow.
- **Verification**: `molecule/default/tests/` may gain assertions on cache paths/keytab mode; full `destroy → converge → verify` cycle on the host-OS scenario, then re-converge for idempotence.
- **Risk surface**: fresh-converge ordering (self-enrollment before ACL grant) is the main new failure mode and is closed by the ordering fix; no changes to FreeIPA server-side CA/profile definitions.
