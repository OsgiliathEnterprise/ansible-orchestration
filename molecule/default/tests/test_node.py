"""Role testing files using testinfra."""
testinfra_hosts = ["node1.osgiliath.test"]


def test_kubelet_active(host):
    with host.sudo():
        command = """service kubelet status | \
        grep -c 'active (running)'"""
        cmd = host.run(command)
    assert '1' in cmd.stdout
