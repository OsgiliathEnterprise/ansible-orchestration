"""Role testing files using testinfra."""
testinfra_hosts = ["master.osgiliath.test"]


def test_api_server_port_is_opened(host):
    with host.sudo():
        command = """firewall-cmd --list-ports --zone=public | \
        grep -c '6443/tcp'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_etcd_port1_is_opened(host):
    with host.sudo():
        command = """firewall-cmd --list-ports --zone=public | \
        grep -c '2379/tcp'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_etcd_port2_is_opened(host):
    with host.sudo():
        command = """firewall-cmd --list-ports --zone=public | \
        grep -c '2380/tcp'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_scheduler_port1_is_opened(host):
    with host.sudo():
        command = """firewall-cmd --list-ports --zone=public | \
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


def test_calico_system_pods_running(host):
    command = r"""
    kubectl get pods -n calico-system | \
    grep Running | \
    wc -l"""
    with host.sudo():
        cmd = host.run(command)
        assert int(cmd.stdout) > 0


def test_calico_operator_pods_running(host):
    command = r"""
    kubectl get pods -n tigera-operator | \
    grep Running | \
    wc -l"""
    with host.sudo():
        cmd = host.run(command)
        assert int(cmd.stdout) > 0


def test_volume_is_create(host):
    command = r"""
    kubectl get pv | \
    egrep -c 'net-artefactrepo.*RWX.*Available.*local-storage'"""
    with host.sudo():
        cmd = host.run(command)
        assert int(cmd.stdout) > 0
