"""Role testing files using testinfra."""
import os
import time


def _worker_hosts():
    """Derive the hosts to test from molecule's inventory: every kube_node member, so
    adding a worker platform is a molecule.yml-only change (no test edits needed)."""
    if "MOLECULE_INVENTORY_FILE" not in os.environ:
        return []  # conftest skips the run when outside molecule
    from testinfra.utils import ansible_runner

    return sorted(
        ansible_runner.AnsibleRunner(os.environ["MOLECULE_INVENTORY_FILE"]).get_hosts("kube_node")
    )


testinfra_hosts = _worker_hosts()


def test_kubelet_active(host):
    with host.sudo():
        command = """service kubelet status | \
        grep -c 'active (running)'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


# --- Per-node identity: the worker joins with its own FreeIPA-issued client cert,
# not a copy of the control-plane admin credential. ---

def test_node_client_cert_exists(host):
    f = host.file("/etc/kubernetes/pki/node-client.crt")
    assert f.exists
    assert f.is_file


def test_node_client_key_exists(host):
    f = host.file("/etc/kubernetes/pki/node-client.key")
    assert f.exists
    assert f.is_file


def test_node_client_cert_has_node_identity(host):
    """The client cert subject is a node identity (CN=system:node:<host>), not admin."""
    with host.sudo():
        cmd = host.run(
            "openssl x509 -in /etc/kubernetes/pki/node-client.crt -noout -subject"
        )
    assert 'system:node' in cmd.stdout


def test_node_client_cert_signed_by_kubernetes_ca(host):
    with host.sudo():
        cmd = host.run(
            "openssl x509 -in /etc/kubernetes/pki/node-client.crt -noout -issuer | "
            "grep -ic 'kubernetes-ca'"
        )
    assert int(cmd.stdout) > 0


def test_node_kubelet_conf_uses_per_node_identity(host):
    """kubelet.conf points at the node's own cert/key, not a shared admin credential."""
    with host.sudo():
        cmd = host.run(
            "grep -c 'client-certificate: /etc/kubernetes/pki/node-client.crt' "
            "/etc/kubernetes/kubelet.conf"
        )
    assert int(cmd.stdout) > 0


def test_node_ca_chains_to_ipa_root(host):
    """The node's trust anchor is the FreeIPA kubernetes-ca, chaining to the IPA root.

    On an IPA client /etc/ipa/ca.crt holds the Dogtag CA chain; we verify against it
    rather than fetching over HTTP (port 8443 may be unreachable inside the VM net).
    """
    ipa_ca = host.file("/etc/ipa/ca.crt")
    assert ipa_ca.exists, "/etc/ipa/ca.crt should exist on an IPA client"
    with host.sudo():
        cmd = host.run(
            "openssl verify -CAfile /etc/ipa/ca.crt /etc/kubernetes/pki/ca.crt"
        )
    assert 'OK' in cmd.stdout


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


def test_cert_renewal_noop_tick_does_not_churn(host):
    """A tick with nothing eligible must not rewrite the cert or restart kubelet (no-churn)."""
    serial_cmd = "openssl x509 -in /etc/kubernetes/pki/node-client.crt -noout -serial"
    enter_cmd = "systemctl show kubelet -p ActiveEnterTimestamp"
    with host.sudo():
        serial_before = host.run(serial_cmd).stdout
        enter_before = host.run(enter_cmd).stdout
        cmd = host.run("RENEW_THRESHOLD_DAYS=1 /usr/local/sbin/kube-cert-renew.sh")
        assert cmd.rc == 0, f"renewal script failed: {cmd.stderr}"
        serial_after = host.run(serial_cmd).stdout
        enter_after = host.run(enter_cmd).stdout
    assert serial_before == serial_after, "no-op tick must not rewrite the node client cert"
    assert enter_before == enter_after, "no-op tick must not restart kubelet"


def test_cert_renewal_forced_eligibility_extends_node_client(host):
    """Force eligibility: the full renewal path re-issues from the existing key and reloads
    kubelet. Placed last on purpose — it restarts kubelet (brief NotReady window)."""
    serial_cmd = "openssl x509 -in /etc/kubernetes/pki/node-client.crt -noout -serial"
    with host.sudo():
        serial_before = host.run(serial_cmd).stdout
        cmd = host.run("RENEW_THRESHOLD_DAYS=3650 /usr/local/sbin/kube-cert-renew.sh")
        assert cmd.rc == 0, f"forced renewal failed: {cmd.stderr}"
        serial_after = host.run(serial_cmd).stdout
        # kubelet restart is async from the script's point of view; poll for readiness.
        kubelet_active = ""
        for _ in range(30):
            kubelet_active = host.run("systemctl is-active kubelet").stdout
            if 'active' in kubelet_active:
                break
            time.sleep(2)
    assert serial_before != serial_after, "forced eligibility must re-issue the node client cert"
    assert 'active' in kubelet_active
