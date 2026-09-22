"""Role testing files using testinfra."""
testinfra_hosts = ["node1.osgiliath.test"]


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
