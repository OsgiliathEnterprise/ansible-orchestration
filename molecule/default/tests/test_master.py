"""Role testing files using testinfra."""
import base64
import json
import os
import re

testinfra_hosts = ["master.osgiliath.test"]


def _all_containers_ready(pod):
    """True when the pod reports container statuses and every container is ready.

    An empty status (pod not started yet) counts as NOT ready."""
    cs = (pod.get("status") or {}).get("containerStatuses") or []
    return bool(cs) and all(c.get("ready") for c in cs)


def _not_ready_names(items):
    """Names of pods from a `kubectl get pods -o json` payload that are not fully ready."""
    return [p["metadata"]["name"] for p in items if not _all_containers_ready(p)]


def _worker_hosts():
    """Derive the worker hosts from molecule's inventory (all kube_node members)."""
    if "MOLECULE_INVENTORY_FILE" not in os.environ:
        return []  # conftest skips the run when outside molecule
    from testinfra.utils import ansible_runner

    return sorted(
        ansible_runner.AnsibleRunner(os.environ["MOLECULE_INVENTORY_FILE"]).get_hosts("kube_node")
    )


def test_kubernetes_ca_exists(host):
    with host.sudo():
        cmd = host.run(
            "echo '123ADMin' | kinit admin > /dev/null 2>&1 && "
            "ipa ca-find | grep -c ': kubernetes-ca'"
        )
    assert '1' in cmd.stdout


def test_kube_administrators_profile_exists(host):
    with host.sudo():
        cmd = host.run(
            "echo '123ADMin' | kinit admin > /dev/null 2>&1 && "
            "ipa certprofile-find | grep -c ': kubeAdministrators'"
        )
    assert '1' in cmd.stdout


def test_ca_acl_linked_to_kubernetes_ca(host):
    with host.sudo():
        cmd = host.run(
            "echo '123ADMin' | kinit admin > /dev/null 2>&1 && "
            "ipa caacl-show kubernetes-ca-acl | grep -ic 'kubernetes-ca'"
        )
    assert int(cmd.stdout) > 0


def test_api_server_port_is_opened(host):
    with host.sudo():
        command = """firewall-cmd --list-ports --zone=trusted | \
        grep -c '6443/tcp'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_etcd_port1_is_opened(host):
    with host.sudo():
        command = """firewall-cmd --list-ports --zone=trusted | \
        grep -c '2379/tcp'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_etcd_port2_is_opened(host):
    with host.sudo():
        command = """firewall-cmd --list-ports --zone=trusted | \
        grep -c '2380/tcp'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_scheduler_port1_is_opened(host):
    with host.sudo():
        command = """firewall-cmd --list-ports --zone=trusted | \
        grep -c '10250/tcp'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_kubelet_active(host):
    with host.sudo():
        command = """service kubelet status | \
        grep -c 'active (running)'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_kubeadm_public_key_exists(host):
    with host.sudo():
        command = """ls -lrt /home/kubecreds | \
        grep -c 'kubeadm.crt'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_tigera_operator_pods_running(host):
    """Wait for tigera-operator pods to be Running (may take time to pull images)."""
    import time
    command = r"""
    kubectl get pods -n tigera-operator --no-headers -o custom-columns=':status.phase' | \
    grep -c Running"""
    with host.sudo():
        for _ in range(12):
            cmd = host.run(command)
            if int(cmd.stdout) > 0:
                break
            time.sleep(15)
        assert int(cmd.stdout) > 0


# CNI and DNS health tests

def test_coredns_pods_ready(host):
    """Every coredns replica has all containers Ready. coredns is restarted after the calico
    install (kube-install.yml), so allow time for the rollout to settle."""
    import time
    command = "kubectl get pods -n kube-system -l k8s-app=kube-dns -o json"
    with host.sudo():
        total, bad = 0, None
        for _ in range(12):
            cmd = host.run(command)
            if cmd.rc == 0:
                items = json.loads(cmd.stdout).get("items", [])
                total, bad = len(items), _not_ready_names(items)
                if total > 0 and not bad:
                    break
            time.sleep(15)
    assert total > 0, "no coredns pods found in kube-system"
    assert not bad, f"coredns pod(s) not fully ready: {bad}"


def test_cluster_dns_resolves_via_coredns(host):
    """Functional check: querying CoreDNS at the kube-dns ClusterIP resolves the kubernetes
    service — proves DNS is actually serving answers, not just that its pods are up."""
    import time
    command = (
        'dig @$(kubectl get svc -n kube-system kube-dns -o jsonpath="{.spec.clusterIP}") '
        "kubernetes.default.svc.cluster.local +short"
    )
    with host.sudo():
        cmd = None
        for _ in range(12):
            cmd = host.run(command)
            if cmd.rc == 0 and any(re.match(r"\d+\.\d+\.\d+\.\d+", line) for line in cmd.stdout.splitlines()):
                break
            time.sleep(15)
    assert cmd is not None and cmd.rc == 0, f"dig failed: {cmd.stderr if cmd else 'no output'}"
    resolved = [line for line in cmd.stdout.splitlines() if re.match(r"\d+\.\d+\.\d+\.\d+", line)]
    assert resolved, (
        f"kubernetes.default.svc.cluster.local did not resolve via CoreDNS: {cmd.stdout!r}"
    )


def test_calico_pods_ready(host):
    """Core calico workloads (node/typha/kube-controllers) have every container Ready, and the
    calico-node DaemonSet has exactly one Ready pod per inventory node — 3/3 in the parallels
    scenario. No orphan pods, no missing nodes: the data plane is complete.

    Only core workloads are checked: calico-system also hosts non-calico pods in this setup."""
    import time
    if "MOLECULE_INVENTORY_FILE" not in os.environ:
        return  # conftest skips the run when outside molecule
    from testinfra.utils import ansible_runner

    runner = ansible_runner.AnsibleRunner(os.environ["MOLECULE_INVENTORY_FILE"])
    expected_nodes = len(runner.get_hosts("kube_master") + runner.get_hosts("kube_node"))
    pods_command = (
        'kubectl get pods -n calico-system '
        '-l "k8s-app in (calico-node,calico-typha,calico-kube-controllers)" -o json'
    )
    with host.sudo():
        total, bad, node_pods, ready_nodes = 0, None, [], 0
        for _ in range(12):
            cmd = host.run(pods_command)
            if cmd.rc == 0:
                items = json.loads(cmd.stdout).get("items", [])
                total = len(items)
                bad = _not_ready_names(items)
                node_pods = [p for p in items if p["metadata"]["name"].startswith("calico-node-")]
                ready_nodes = sum(1 for p in node_pods if _all_containers_ready(p))
                if total > 0 and not bad and len(node_pods) == expected_nodes and ready_nodes == expected_nodes:
                    break
            time.sleep(15)
    assert total > 0, "no core calico pods found in calico-system"
    assert not bad, f"calico pod(s) not fully ready: {bad}"
    assert len(node_pods) == expected_nodes, (
        f"expected {expected_nodes} calico-node pods, found {len(node_pods)}"
    )
    assert ready_nodes == expected_nodes, (
        f"only {ready_nodes}/{expected_nodes} calico-node pods are Ready"
    )


def test_kubectl_get_nodes_matches_inventory(host):
    """The cluster contains exactly master plus every worker from molecule's inventory —
    so adding a platform is a molecule.yml-only change."""
    if "MOLECULE_INVENTORY_FILE" not in os.environ:
        return  # conftest skips the run when outside molecule
    from testinfra.utils import ansible_runner

    runner = ansible_runner.AnsibleRunner(os.environ["MOLECULE_INVENTORY_FILE"])
    expected = sorted(runner.get_hosts("kube_master") + runner.get_hosts("kube_node"))
    command = "kubectl get nodes --no-headers | awk '{print $1}'"
    with host.sudo():
        cmd = host.run(command)
        actual = sorted(line for line in cmd.stdout.splitlines() if line.strip())
        assert actual == expected, f"cluster nodes {actual} != inventory hosts {expected}"


def test_admin_cert_issuer_is_kubernetes_ca(host):
    with host.sudo():
        cmd = host.run(
            "openssl x509 -in /home/kubecreds/kubeadm.crt -noout -issuer | "
            "grep -ic 'kubernetes-ca'"
        )
    assert int(cmd.stdout) > 0


def test_admin_cert_signed_by_kubernetes_ca(host):
    with host.sudo():
        cmd = host.run(
            "openssl x509 -in /home/kubecreds/kubeadm.crt -noout -issuer | "
            "grep -ic 'kubernetes-ca'"
        )
    assert int(cmd.stdout) > 0


def test_kubeconfig_certificate_authority_is_kubernetes_ca(host):
    with host.sudo():
        cmd = host.run(
            "grep -c 'certificate-authority: /etc/kubernetes/pki/ca.crt' "
            "/etc/kubernetes/admin.conf"
        )
    assert int(cmd.stdout) > 0


def test_kubeconfig_client_certificate_is_ipa_signed(host):
    with host.sudo():
        cmd = host.run(
            "grep -c 'client-certificate: /home/kubecreds/kubeadm.crt' "
            "/etc/kubernetes/admin.conf"
        )
    assert int(cmd.stdout) > 0


def test_kubectl_get_nodes_with_ipa_credentials(host):
    with host.sudo():
        cmd = host.run("kubectl get nodes --no-headers | wc -l")
    assert int(cmd.stdout) >= 1


def test_node_ready_via_master_admin_conf(host):
    """V2 end-state: master's admin.conf (post pki-swap, trusting the IPA CA) sees every
    worker node as Ready. Proves admin.conf is patched + API up + all nodes registered —
    the exact path the converge-time verification relies on."""
    import time

    workers = _worker_hosts()
    assert workers, "no kube_node hosts found in molecule inventory"
    command_tmpl = (
        "kubectl get node {worker} --kubeconfig /etc/kubernetes/admin.conf "
        "-o jsonpath='{{.status.conditions[?(@.type==\"Ready\")].status}}'"
    )
    with host.sudo():
        statuses = {}
        for _ in range(24):
            statuses = {
                worker: 'True' in host.run(command_tmpl.format(worker=worker)).stdout
                for worker in workers
            }
            if all(statuses.values()):
                break
            time.sleep(15)
        assert all(statuses.values()), (
            f"not all worker nodes Ready via master admin.conf (got {statuses!r})"
        )


# IPA PKI bootstrap tests

def test_ca_crt_exists_at_pki_path(host):
    f = host.file("/etc/kubernetes/pki/ca.crt")
    assert f.exists
    assert f.is_file


def test_apiserver_crt_and_key_exist_in_pki(host):
    assert host.file("/etc/kubernetes/pki/apiserver.crt").exists
    assert host.file("/etc/kubernetes/pki/apiserver.key").exists


def test_front_proxy_client_crt_and_key_exist_in_pki(host):
    assert host.file("/etc/kubernetes/pki/front-proxy-client.crt").exists
    assert host.file("/etc/kubernetes/pki/front-proxy-client.key").exists


def test_apiserver_kubelet_client_crt_exists_in_pki(host):
    assert host.file("/etc/kubernetes/pki/apiserver-kubelet-client.crt").exists


def test_sa_key_exists_in_pki(host):
    assert host.file("/etc/kubernetes/pki/sa.key").exists


def test_apiserver_crt_signed_by_kubernetes_ca(host):
    with host.sudo():
        cmd = host.run(
            "openssl x509 -in /etc/kubernetes/pki/apiserver.crt -noout -issuer | "
            "grep -ic 'kubernetes-ca'"
        )
    assert int(cmd.stdout) > 0


def test_apiserver_kubelet_client_crt_signed_by_kubernetes_ca(host):
    with host.sudo():
        cmd = host.run(
            "openssl x509 -in /etc/kubernetes/pki/apiserver-kubelet-client.crt -noout -issuer | "
            "grep -ic 'kubernetes-ca'"
        )
    assert int(cmd.stdout) > 0


def test_front_proxy_client_crt_signed_by_kubernetes_ca(host):
    with host.sudo():
        cmd = host.run(
            "openssl x509 -in /etc/kubernetes/pki/front-proxy-client.crt -noout -issuer | "
            "grep -ic 'kubernetes-ca'"
        )
    assert int(cmd.stdout) > 0


def test_kubernetes_ca_signed_by_ipa_root_ca(host):
    """Verify kubernetes-ca chains back to the IPA root CA.

    On an IPA client, /etc/ipa/ca.crt is installed by the enrollment process
    and contains the IPA Dogtag CA certificates (root + any intermediates).
    We use that instead of fetching over HTTP — port 8443 may not be reachable
    from inside the VM network.
    """
    ipa_ca = host.file("/etc/ipa/ca.crt")
    assert ipa_ca.exists, "/etc/ipa/ca.crt should exist on an IPA client"
    with host.sudo():
        cmd = host.run(
            "openssl verify -CAfile /etc/ipa/ca.crt /etc/kubernetes/pki/ca.crt"
        )
    assert 'OK' in cmd.stdout


def test_controller_manager_conf_references_ipa_ca(host):
    cfg = host.file("/etc/kubernetes/controller-manager.conf")
    assert cfg.exists
    assert "certificate-authority: /etc/kubernetes/pki/ca.crt" in cfg.content.decode()


def test_scheduler_conf_embeds_ipa_ca(host):
    # The scheduler's static pod does not mount /etc/kubernetes/pki, so a file reference to
    # ca.crt would crash it at boot ("unable to read certificate-authority"); its kubeconfig
    # must carry the IPA CA embedded instead.
    cfg = host.file("/etc/kubernetes/scheduler.conf")
    assert cfg.exists
    match = re.search(r"certificate-authority-data:\s*(\S+)", cfg.content.decode())
    assert match, "scheduler.conf must embed certificate-authority-data (static pod lacks pki mount)"
    embedded = base64.b64decode(match.group(1)).decode().strip()
    ca_crt = host.file("/etc/kubernetes/pki/ca.crt").content.decode().strip()
    assert embedded == ca_crt, "embedded CA must match /etc/kubernetes/pki/ca.crt (IPA CA)"


def test_kubeadm_init_succeeded_clean_pki(host):
    with host.sudo():
        cmd = host.run("kubectl cluster-info | grep -c 'Kubernetes control plane'")
    assert int(cmd.stdout) > 0


def test_api_server_static_pod_running_after_swap(host):
    with host.sudo():
        cmd = host.run(
            "crictl ps --name kube-apiserver --state RUNNING | "
            "grep -c kube-apiserver"
        )
    assert int(cmd.stdout) > 0


# Unattended certificate renewal tests

def test_cert_renewal_script_installed(host):
    f = host.file("/usr/local/sbin/kube-cert-renew.sh")
    assert f.exists
    assert f.is_file


def test_cert_renewal_timer_enabled_and_active(host):
    with host.sudo():
        enabled = host.run("systemctl is-enabled kube-cert-renew.timer").stdout
        active = host.run("systemctl is-active kube-cert-renew.timer").stdout
    assert 'enabled' in enabled
    assert 'active' in active


def test_kubeclusteradm_keytab_installed(host):
    """The user keytab used to renew the cluster-admin client certificate without a password."""
    with host.sudo():
        f = host.file("/home/kubecreds/kubeclusteradm.keytab")
        assert f.exists
        cmd = host.run("klist -kt /home/kubecreds/kubeclusteradm.keytab | grep -c kubeclusteradm")
    assert int(cmd.stdout) > 0


def test_master_host_in_it_specialist_role(host):
    """Write access on the apiserver SAN principals comes from this role grant.

    `ipa role-show` without --all does not list members; --all is required to see
    the `Member hosts:` attribute (same as caacl-show in test_ca_acl_grants_all_kube_hosts).

    The grep pattern must use double quotes: testinfra wraps the whole command in
    another single-quoted layer for `sudo /bin/sh -c`, so single-quoted
    `'$(hostname)'` would reach the inner shell unexpanded and match literally."""
    with host.sudo():
        cmd = host.run(
            "echo '123ADMin' | kinit admin > /dev/null 2>&1 && "
            "ipa role-show --all 'IT Specialist' | grep -c \"Member hosts:.*$(hostname)\""
        )
    assert int(cmd.stdout) > 0


def test_ca_acl_grants_all_kube_hosts(host):
    """Spec scenario 'CA ACL permits each principal type': after convergence the CA ACL grants
    every kube host — renewal authenticates as the host principal, which `user category: all`
    does not cover (without these grants forced renewal is denied by the ACL)."""
    if "MOLECULE_INVENTORY_FILE" not in os.environ:
        return  # conftest skips the run when outside molecule
    from testinfra.utils import ansible_runner

    runner = ansible_runner.AnsibleRunner(os.environ["MOLECULE_INVENTORY_FILE"])
    expected = sorted(runner.get_hosts("kube_master") + runner.get_hosts("kube_node"))
    with host.sudo():
        cmd = host.run(
            "echo '123ADMin' | kinit admin > /dev/null 2>&1 && "
            "ipa caacl-show kubernetes-ca-acl --all"
        )
    # `ipa caacl-show --all` lists granted hosts under a `Hosts:` attribute (not "Member hosts:").
    member_lines = [line for line in cmd.stdout.splitlines() if "Hosts:" in line]
    members_blob = " ".join(member_lines)
    missing = [h for h in expected if h not in members_blob]
    assert not missing, f"kubernetes-ca-acl is missing host grants: {missing}"


def test_cert_renewal_noop_tick_does_not_churn(host):
    """A tick with nothing eligible must not rewrite certs or restart services (no-churn)."""
    serial_cmd = "openssl x509 -in /etc/kubernetes/pki/apiserver.crt -noout -serial"
    enter_cmd = "systemctl show kubelet -p ActiveEnterTimestamp"
    with host.sudo():
        serial_before = host.run(serial_cmd).stdout
        enter_before = host.run(enter_cmd).stdout
        cmd = host.run("RENEW_THRESHOLD_DAYS=1 /usr/local/sbin/kube-cert-renew.sh")
        assert cmd.rc == 0, f"renewal script failed: {cmd.stderr}"
        serial_after = host.run(serial_cmd).stdout
        enter_after = host.run(enter_cmd).stdout
    assert serial_before == serial_after, "no-op tick must not rewrite the apiserver cert"
    assert enter_before == enter_after, "no-op tick must not restart services"


def test_pv_has_nfs_volume_source(host):
    """Wait for PV to exist and be accessible before checking volume source."""
    import time
    command = r'''
    kubectl get pv -o json | python3 -c 'import sys, json; data=json.load(sys.stdin); pvs=[p for p in data["items"] if "artefactrepo" in p["metadata"]["name"]]; print(json.dumps(pvs))'
    '''
    with host.sudo():
        import json
        pvs = []
        for _ in range(12):
            cmd = host.run(command)
            try:
                stdout = cmd.stdout.strip()
                if stdout and stdout != '[]':
                    pvs = json.loads(stdout)
                    if len(pvs) > 0:
                        break
            except (json.JSONDecodeError, KeyError):
                pass
            time.sleep(5)
        assert len(pvs) > 0, "No PV found with artefactrepo"
        pv = pvs[0]
        assert 'nfs' in pv['spec'], "PV should have nfs volume source"
        assert 'server' in pv['spec']['nfs'], "PV should have nfs.server"
        assert 'path' in pv['spec']['nfs'], "PV should have nfs.path"


def test_volume_is_create(host):
    """Wait for PV to transition from Pending to Available."""
    import time
    command = r"""
    kubectl get pv | \
    egrep -c 'nfs.*artefactrepo.*RWX.*Available.*nfs-storage'"""
    with host.sudo():
        for _ in range(130):
            cmd = host.run(command)
            if int(cmd.stdout) > 0:
                break
            time.sleep(5)
        assert int(cmd.stdout) > 0
