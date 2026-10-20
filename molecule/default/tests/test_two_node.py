"""Tests that require at least two kube_node workers.

Run only under two-worker scenarios (default, parallels): the single-worker
KVM scenario excludes this file structurally — molecule/kvm/tests/ mirrors
the shared suite per-file without it (see the mirroring layout in AGENTS.md).
The guard below is a canary: if this file is ever run against an inventory
with fewer than two workers it fails fast with an actionable message.
"""
import os


def _worker_hosts():
    """Derive the workers from molecule's inventory: every kube_node member."""
    if "MOLECULE_INVENTORY_FILE" not in os.environ:
        return []  # conftest skips the run when outside molecule
    from testinfra.utils import ansible_runner

    return sorted(
        ansible_runner.AnsibleRunner(os.environ["MOLECULE_INVENTORY_FILE"]).get_hosts("kube_node")
    )


testinfra_hosts = _worker_hosts()


def test_two_workers_present():
    """Guard: this file's precondition is >= 2 kube_node workers in the inventory."""
    assert len(testinfra_hosts) >= 2, (
        f"test_two_node.py requires at least 2 kube_node workers; inventory has "
        f"{len(testinfra_hosts)}: {testinfra_hosts!r} — this file must not run "
        f"under a single-worker scenario (see the mirroring layout in AGENTS.md)"
    )
