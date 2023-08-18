Orchestration
=========

* Galaxy: [![Ansible Galaxy](https://img.shields.io/badge/galaxy-tcharl.ansible_orchestration-660198.svg?style=flat)](https://galaxy.ansible.com/tcharl/ansible_orchestration)
* Lint & requirements: ![Molecule](https://github.com/OsgiliathEnterprise/ansible-orchestration/workflows/Molecule/badge.svg)
* Tests: [![Build Status](https://travis-ci.com/OsgiliathEnterprise/ansible-orchestration.svg?branch=master)](https://travis-ci.com/OsgiliathEnterprise/ansible-orchestration)
* Chat: [![Join the chat at https://gitter.im/OsgiliathEnterprise/platform](https://badges.gitter.im/OsgiliathEnterprise/platform.svg)](https://gitter.im/OsgiliathEnterprise/platform?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)


Combines Firewalld, hostname, kubevirt-csi, docker, helm, istio configuration and geerlinguy.kubernetes roles to configure a kubernetes with good security and reasonable defaults (firewall storage and network rules).

Basically, it will configure X master nodes and Y workers.
You can transform this Kube into a stateful one with the help of the tcharl.ansible_volume role:you'll just have to mount the same NFS mounpoint on all your node and configure the kubevirt-csi driver to get kube storage.

```
mountpoints:
  - remote: /var/shared/csi
    local: /net
    csi_mount: Yes
```

This role will also generate a Kubernetes cluster admin client certificate keypair  available on the master's '/home/kubecreds' machine folder 

Requirements
------------

If you are on VMs, these ones should be in a 'Bridge' network mode, NAT or HostOnly will not work (BGP policies will consider IPs to come from the host, which leads to buggy behavior). If you really need NAT, consider tweaking calico BGPPeer configuration (and please contribute back to this role if you find a smart way to do so). 

Bridge configuration is subnetworked/28 by default: the ip adresses of your node should ideally follow each other

Role Variables
--------------

As an example, see the [Molecule test vars](./molecule/default/converge.yml) and the [default variables](./defaults/main.yml)

Example of attributes for a node part of the kube_master role
```
kubernetes_allow_pods_on_master: False
hostname: "master.{{ company_domain }}"
hostname_reboot: false
kube_firewall_zone: 'public'
kube_alt_names:
  - "kubeadm.osgiliath.net"
```

Example of attributes for a node part of the kube_node role
```
hostname: "node.{{ company_domain }}
hostname_reboot: false
kube_firewall_zone: 'public'
```
Dependencies
------------

* See [requirements](./requirements.yml)
* See [collection requirements](./requirements-collections.yml)

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

    - hosts:
       - kube_master
      roles:
         - { role: tcharl.ansible_orchestration }
    - hosts:
       - kube_node
      roles:
         - { role: tcharl.ansible_orchestration }

License
-------

[Apache-2](https://www.apache.org/licenses/LICENSE-2.0)

Author Information
------------------

* Twitter [@tcharl](https://twitter.com/Tcharl)
* Github [@tcharl](https://github.com/Tcharl)
* LinkedIn [Charlie Mordant](https://www.linkedin.com/in/charlie-mordant-51796a97/)
