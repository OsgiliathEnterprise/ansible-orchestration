Orchestration
=========

* Galaxy: [![Ansible Galaxy](https://img.shields.io/badge/galaxy-tcharl.ansible_orchestration-660198.svg?style=flat)](https://galaxy.ansible.com/tcharl/ansible_users)
* Lint & requirements: ![Molecule](https://github.com/OsgiliathEnterprise/ansible-orchestration/workflows/Molecule/badge.svg)
* Tests: [![Build Status](https://travis-ci.com/OsgiliathEnterprise/ansible-orchestration.svg?branch=master)](https://travis-ci.com/OsgiliathEnterprise/ansible-orchestration)
* Chat: [![Join the chat at https://gitter.im/OsgiliathEnterprise/platform](https://badges.gitter.im/OsgiliathEnterprise/platform.svg)](https://gitter.im/OsgiliathEnterprise/platform?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)


Combines LVM, Docker, Libvirt and geerlinguy.kubernetes roles to create some VMs and configure kubernetes over it 

Requirements
------------



Role Variables
--------------

As an example, see the [Molecule test vars](./molecule/default/converge.yml)

Dependencies
------------

* See [requirements](./requirements.yml)

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

    - hosts: servers
      roles:
         - { role: tcharl.ansible-orchestration, x: 42 }

License
-------

[Apache-2](https://www.apache.org/licenses/LICENSE-2.0)

Author Information
------------------

* Twitter [@tcharl](https://twitter.com/Tcharl)
* Github [@tcharl](https://github.com/Tcharl)
* LinkedIn [Charlie Mordant](https://www.linkedin.com/in/charlie-mordant-51796a97/)
