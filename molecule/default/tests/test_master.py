"""Role testing files using testinfra."""
testinfra_hosts = ["master.osgiliath.test"]


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


def test_kubectl_get_nodes_equals_two(host):
    command = r"""
    kubectl get nodes --no-headers | \
    wc -l"""
    with host.sudo():
        cmd = host.run(command)
        assert int(cmd.stdout) == 2


def test_admin_cert_issuer_is_kubernetes_ca(host):
    with host.sudo():
        cmd = host.run(
            "openssl x509 -in /home/kubecreds/kubeadm.crt -noout -issuer | "
            "grep -ic 'kubernetes-ca'"
        )
    assert int(cmd.stdout) > 0


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


def test_controller_manager_conf_references_ipa_ca(host):
    cfg = host.file("/etc/kubernetes/controller-manager.conf")
    assert cfg.exists
    assert "certificate-authority: /etc/kubernetes/pki/ca.crt" in cfg.content.decode()


def test_scheduler_conf_references_ipa_ca(host):
    cfg = host.file("/etc/kubernetes/scheduler.conf")
    assert cfg.exists
    assert "certificate-authority: /etc/kubernetes/pki/ca.crt" in cfg.content.decode()


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


def test_volume_is_create(host):
    """Wait for PV to transition from Pending to Available."""
    import time
    command = r"""
    kubectl get pv | \
    egrep -c 'nfs.*artefactrepo.*RWX.*Available.*nfs-storage'"""
    with host.sudo():
        for _ in range(100):
            cmd = host.run(command)
            if int(cmd.stdout) > 0:
                break
            time.sleep(5)
        assert int(cmd.stdout) > 0
