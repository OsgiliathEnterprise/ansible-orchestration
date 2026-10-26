"""Offline guard tests for the rescue (failure-report) block of tasks/calico-ca-recovery.yml.

The rescue block runs only when the calico-node rolling restart does not complete within
``kubernetes_rollout_wait_timeout``; reaching it against a live cluster takes minutes, so these
tests extract the rescue from the task file (never copy-paste it — the templates are parsed
straight out of the YAML, which is what guards them) and run the extracted tasks against
fixture data on ``localhost`` with no cluster, no kubeconfig, and no ``kubernetes.core``
module calls (the four ``k8s_info`` collection tasks are replaced by ``set_fact`` fixtures of
the same shape their ``register``ed results would have).

The extracted tasks run inside a ``block``/``rescue`` wrapper: the outer rescue dumps the
accumulated facts (``ready_node_names``, ``not_ready_pods``, ``calico_pod_evidence``,
``calico_ds_state``) and the ``ansible_failed_result`` of whatever failed inside the block
into a JSON file, then re-fails so the play exits non-zero. The tests assert on the exact
``fail``-task message rather than on console output (which the callback may wrap or escape).

Run from the role root with the role's venv:

    .venv/bin/pytest tests/test_calico_recovery_rescue.py

If the venv lacks ``ansible-playbook`` the tests fail with a clear error instead of
``FileNotFoundError``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROLE = Path(__file__).resolve().parent.parent
TASK_FILE = ROLE / "tasks" / "calico-ca-recovery.yml"
ANSIBLE_PLAYBOOK = Path(sys.executable).parent / "ansible-playbook"


def _rescue_tasks():
    """The rescue list of the calico-node rolling restart task, in file order."""
    doc = yaml.safe_load(TASK_FILE.read_text())
    for task in doc:
        if "rescue" in task:
            return task["rescue"]
    raise AssertionError(
        "no task with a rescue block found in %s; the calico-node rolling restart "
        "task must keep its block/rescue structure" % TASK_FILE
    )


def _build_play(dump_path, fixtures, phase="rollout"):
    """Extracted rescue as a localhost play; k8s_info tasks replaced by set_fact fixtures.

    ``phase`` mirrors the ``calico_recovery_phase`` fact the (non-extracted) block sets once
    the all-nodes Ready gate has passed: ``"rollout"`` for a patch/rollout timeout, or
    ``None`` for a gate timeout where the fact was never set and the failure message falls
    back to its default.
    """
    vars_ = {"guard_dump_path": str(dump_path)}
    if phase is not None:
        vars_["calico_recovery_phase"] = phase
    tasks = []
    for task in _rescue_tasks():
        if "kubernetes.core.k8s_info" in task:
            register = task["register"]
            if register not in fixtures:
                raise AssertionError("no fixture for registered variable %r" % register)
            tasks.append(
                {
                    "name": "%s (fixture)" % task.get("name", "k8s_info"),
                    "ansible.builtin.set_fact": {register: fixtures[register]},
                }
            )
            continue
        task = dict(task)
        task.pop("become", None)  # no sudo on the test host
        tasks.append(task)
    return {
        "name": "calico-ca-recovery rescue guard",
        "hosts": "localhost",
        "connection": "local",
        "gather_facts": False,
        "vars": vars_,
        "tasks": [
            {
                "name": "guard | run extracted rescue",
                "block": tasks,
                "rescue": [
                    {
                        "name": "guard | dump extracted-rescue state",
                        "ansible.builtin.copy": {
                            # Jinja dict-literal keys must be quoted strings: a bare
                            # identifier is a variable reference, which would use the
                            # (list) fact value as an unhashable key.
                            "content": (
                                "{{ {'ready_node_names': ready_node_names | default([]),"
                                " 'not_ready_pods': not_ready_pods | default([]),"
                                " 'calico_pod_evidence': calico_pod_evidence | default([]),"
                                " 'calico_ds_state': calico_ds_state | default({}),"
                                " 'failed_result': ansible_failed_result | default({})}"
                                " | to_nice_json }}"
                            ),
                            "dest": "{{ guard_dump_path }}",
                        },
                    },
                    {
                        "name": "guard | re-fail with extracted-rescue result",
                        "ansible.builtin.fail": {
                            "msg": (
                                "guard | extracted rescue failed:"
                                " {{ (ansible_failed_result.msg"
                                " | default('<no fail task ran; check for template/"
                                "undefined errors>')) | to_json }}"
                            ),
                        },
                    },
                ],
            }
        ],
    }


def _pod(name, node, ready, message=None):
    condition = {"type": "Ready", "status": "True" if ready else "False"}
    if message:
        condition["message"] = message
    return {
        "metadata": {"name": name},
        "spec": {"nodeName": node},
        "status": {"phase": "Running", "conditions": [condition]},
    }


def _nodes(*names):
    return {"resources": [{"metadata": {"name": name}} for name in names]}


# node1's pod is Ready; node2/node3 pods are not (node2 has a Ready-condition message and
# two events, node3 has neither — exercises the <no Ready condition> and <none> fallbacks).
STALL_FIXTURES = {
    "calico_pods": {
        "resources": [
            _pod("calico-node-alpha", "node1.osgiliath.test", True),
            _pod("calico-node-beta", "node2.osgiliath.test", False, "CNI init failed: stale CA"),
            _pod("calico-node-gamma", "node3.osgiliath.test", False),
        ]
    },
    "cluster_nodes": _nodes(
        "node1.osgiliath.test", "node2.osgiliath.test", "node3.osgiliath.test"
    ),
    "calico_ds_info": {
        "resources": [
            {
                "metadata": {"generation": 5},
                "status": {
                    "observedGeneration": 4,
                    "desiredNumberScheduled": 3,
                    "updatedNumberScheduled": 1,
                    "numberReady": 1,
                },
            }
        ]
    },
    "calico_events": {
        "resources": [
            {
                "involvedObject": {"name": "calico-node-beta"},
                "reason": "Pulled",
                "message": "pulled image",
                "lastTimestamp": "2026-01-01T00:00:00Z",
            },
            {
                "involvedObject": {"name": "calico-node-beta"},
                "reason": "Failed",
                "message": "CNI failed: stale CA",
                "lastTimestamp": "2026-01-01T00:10:00Z",
            },
        ]
    },
}

ALL_READY_FIXTURES = {
    "calico_pods": {
        "resources": [
            _pod("calico-node-alpha", "node1.osgiliath.test", True),
            _pod("calico-node-beta", "node2.osgiliath.test", True),
            _pod("calico-node-gamma", "node3.osgiliath.test", True),
        ]
    },
    "cluster_nodes": STALL_FIXTURES["cluster_nodes"],
    "calico_ds_info": STALL_FIXTURES["calico_ds_info"],
    "calico_events": {"resources": []},
}


def _require_playbook():
    if not ANSIBLE_PLAYBOOK.exists():
        pytest.fail(
            "ansible-playbook not found at %s; run this test inside the role venv"
            " (.venv/bin/pytest tests/test_calico_recovery_rescue.py)" % ANSIBLE_PLAYBOOK
        )


def _run_play(tmp_path, fixtures, phase="rollout"):
    """Run the extracted rescue; return (completed process, dumped state dict or None)."""
    _require_playbook()
    dump = tmp_path / "rescue_state.json"
    play_file = tmp_path / "guard_play.yml"
    play_file.write_text(yaml.safe_dump([_build_play(dump, fixtures, phase)], sort_keys=False))
    env = dict(os.environ)
    env.update(
        {
            # Keep the fatal line intact so nothing is lost to console wrapping.
            "COLUMNS": "10000",
            "ANSIBLE_LOCALHOST_WARNING": "False",
            "ANSIBLE_INVENTORY_UNPARSED_WARNING": "False",
            "ANSIBLE_DEPRECATION_WARNINGS": "False",
        }
    )
    proc = subprocess.run(
        [str(ANSIBLE_PLAYBOOK), "-i", "localhost,", str(play_file)],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROLE,
        timeout=120,
    )
    state = json.loads(dump.read_text()) if dump.exists() else None
    if state is None:
        pytest.fail(
            "extracted-rescue dump missing; the play crashed before the outer rescue:\n"
            "%s\n%s" % (proc.stdout, proc.stderr)
        )
    return proc, state


def test_playbook_available():
    """The guard suite needs ansible-playbook next to the test interpreter."""
    _require_playbook()


def test_rescue_failure_message(tmp_path):
    """Stall fixture: the fail task names the rollout phase and only the nodes lacking a
    Ready calico-node pod."""
    proc, state = _run_play(tmp_path, STALL_FIXTURES)
    assert proc.returncode != 0, "the extracted rescue must end in a failure"
    msg = state["failed_result"].get("msg", "")
    assert "CA recovery did not complete (phase: rollout)" in msg


def test_rescue_gate_phase_message(tmp_path):
    """Gate timeout: the phase fact was never set, so the failure message names the
    all-nodes Ready gate phase and still carries the evidence contract."""
    proc, state = _run_play(tmp_path, STALL_FIXTURES, phase=None)
    assert proc.returncode != 0, "the extracted rescue must end in a failure"
    msg = state["failed_result"].get("msg", "")
    assert "CA recovery did not complete (phase: all-nodes Ready gate)" in msg
    assert "node2.osgiliath.test" in msg
    assert "node3.osgiliath.test" in msg
    assert "node1.osgiliath.test" not in msg
    # Only the nodes without a Ready pod are named — never the Ready ones.
    assert "node2.osgiliath.test" in msg
    assert "node3.osgiliath.test" in msg
    assert "node1.osgiliath.test" not in msg
    # Cluster order is preserved (not the set-based reordering of a difference filter).
    assert msg.index("node2.osgiliath.test") < msg.index("node3.osgiliath.test")


def test_rescue_daemonset_state(tmp_path):
    """Stall fixture: the DaemonSet generation state is extracted into the message."""
    _, state = _run_play(tmp_path, STALL_FIXTURES)
    msg = state["failed_result"].get("msg", "")
    assert "generation=5" in msg
    assert "observedGeneration=4" in msg
    assert "desired=3" in msg
    assert "updated=1" in msg
    assert "ready=1" in msg


def test_rescue_per_pod_evidence(tmp_path):
    """Stall fixture: one evidence line per non-Ready pod, most recent event first."""
    _, state = _run_play(tmp_path, STALL_FIXTURES)
    msg = state["failed_result"].get("msg", "")
    # beta: two events — the most recent (00:10, Failed) must win over Pulled (00:00).
    assert "last event: Failed CNI failed: stale CA" in msg
    assert "last event: Pulled" not in msg
    # gamma: no events at all — the <none> fallback must show, not an error.
    assert "last event: <none>" in msg
    assert state["ready_node_names"] == ["node1.osgiliath.test"]
    assert [p["metadata"]["name"] for p in state["not_ready_pods"]] == [
        "calico-node-beta",
        "calico-node-gamma",
    ]
    assert len(state["calico_pod_evidence"]) == 2
    # Single-template set_fact values are auto-unwrapped to their native type (int here).
    assert str(state["calico_ds_state"]["generation"]) == "5"


def test_rescue_all_ready_fallback(tmp_path):
    """All pods Ready: the fail still fires (the timeout happened) but names no node."""
    proc, state = _run_play(tmp_path, ALL_READY_FIXTURES)
    assert proc.returncode != 0
    msg = state["failed_result"].get("msg", "")
    assert "<all nodes covered; check calico-node pod status>" in msg
    assert "<all pods Ready or unscheduled>" in msg
    assert state["calico_pod_evidence"] == []


def test_no_template_or_undefined_errors(tmp_path):
    """Regression: the historical failure was a Jinja parse error ("expected ')', got ']')
    that masked the failure report. Any template/undefined error inside the extracted
    rescue must surface as such, not as the recovery failure message."""
    _, state = _run_play(tmp_path, STALL_FIXTURES)
    msg = str(state["failed_result"].get("msg", "")).lower()
    assert "ca recovery did not complete" in msg
    for marker in ("expected token", "template error", "is undefined", "no attribute"):
        assert marker not in msg, "template/undefined error leaked into the failure message: %s" % marker
