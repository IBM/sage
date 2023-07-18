# Sage Project

Sage is a framework for Ansible repository scan to create graph/intermediate/high level representation of data that can be downstream converted to ftdata. The project includes practical examples for generating/processing task data such as 
- Creating training data specific to a customer repository ([link](./doc/custom-repo-scan.md))
- Adding enriched context to existing fine-tuning data set ([link](./doc/enrich-context.md))
- Creating training dataset for multi-task generation ([link](./doc/new-train-data.md))

## Sage Data Representation

Sage scan the project and create object tree which consists of Ansible specific nodes like
- collections (all external dependencies)
- modules (name, fqcn, spec)
- playbooks (name, comment, filename)
- plays (name, comment, calling tasks and roles)
- projects (including playbooks, roles, dependencies, metadata)
- roles (including taskfiles, role metadata, variables, default, etc)
- taskfiles (calling tasks)
- tasks (task spec, callling module)

Each node is represented by unique identifier, and links between the nodes are created by analayzing Ansible specific code semantics. For example, 
- call hierarlchy from playbook to role --> taskfile - task --> module
- variable assignment is inferred in a static-analytics fashion

The data is useful to compute rich context information beyond single. For example, 
- easy to find a pair of two tasks like
  - task A set a variable `x1` by set-fact or register
  - task B consumes `x1`
- easy to create enriched context like
  - task A is called in taskfile `debian.yml` in role R `ansible-rabbitmq` for `Ansible role to install/configure RabbitMQ`
  - a set of variables `x1...xn` are avaialble in task B

The data can be accessed by rules at runtime, and the data is exported as knowledge base file (ARI RAM file) for later use. 

```
{
  "py/object": "ansible_risk_insight.models.Role",
  "type": "role",
  "key": "role collection:debops.debops#role:debops.debops.ansible",
  "name": "ansible",
  "defined_in": "roles/ansible",
  "local_key": "role role:roles/ansible",
  "fqcn": "debops.debops.ansible",
  "metadata": {
    "collections": [
      "debops.debops"
    ],
    "dependencies": [],
    "galaxy_info": {
      "company": "DebOps",
      "author": "Maciej Delmanowski",
      "description": "Install Ansible on Debian/Ubuntu host using Ansible",
      "license": "GPL-3.0-only",
      "min_ansible_version": "2.4.0",
      "platforms": [
        {
          "name": "Debian",
          "versions": [
            "wheezy",
            "jessie",
            "stretch",
            "buster"
          ]
        },
        {
          "name": "Ubuntu",
          "versions": [
            "precise",
            "trusty",
            "xenial",
            "bionic"
          ]
        }
      ],
      "galaxy_tags": [
        "ansible"
      ]
    }
  },
  "collection": "debops.debops",
  "playbooks": [],
  "taskfiles": [
    "taskfile collection:debops.debops#taskfile:roles/ansible/tasks/main.yml"
  ],
  "handlers": [],
  "modules": [],
  "dependency": {
    "roles": [],
    "collections": [
      "debops.debops"
    ]
  },
  "requirements": {},
  "source": "",
  "annotations": {},
  "default_variables": {
    "ansible__deploy_type": "{{ \"upstream\" if (ansible_distribution_release in [ \"wheezy\", \"jessie\", \"precise\", \"trusty\", \"xenial\" ]) else \"system\" }}",
    "ansible__upstream_apt_key": "6125 E2A8 C77F 2818 FB7B D15B 93C4 A3FD 7BB9 C367",
    "ansible__upstream_apt_repository": "deb http://ppa.launchpad.net/ansible/ansible/ubuntu xenial main",
    "ansible__base_packages": [
      "{{ \"ansible\" if (ansible__deploy_type in [ \"system\", \"upstream\" ]) else [] }}"
    ],
    "ansible__packages": [],
    "ansible__bootstrap_version": "devel",
    "ansible__apt_preferences__dependent_list": [
      {
        "package": "ansible",
        "backports": [
          "wheezy",
          "jessie",
          "stretch",
          "buster"
        ],
        "reason": "Compatibility with upstream release",
        "by_role": "debops_ansible",
        "state": "{{ \"absent\" if (ansible__deploy_type == \"upstream\") else \"present\" }}"
      },
      {
        "package": "ansible",
        "pin": "release o=LP-PPA-ansible-ansible",
        "priority": "600",
        "by_role": "debops_ansible",
        "filename": "debops_ansible_upstream.pref",
        "reason": "Recent version from upstream PPA",
        "state": "{{ \"present\" if (ansible__deploy_type == \"upstream\") else \"absent\" }}"
      }
    ],
    "ansible__keyring__dependent_apt_keys": [
      {
        "id": "{{ ansible__upstream_apt_key }}",
        "repo": "{{ ansible__upstream_apt_repository }}",
        "state": "{{ \"present\" if (ansible__deploy_type == \"upstream\") else \"absent\" }}"
      }
    ]
  },
  "variables": {},
  "loop": {},
  "options": {}
}
```

## Installation

Run the following command after `git clone`.

```
$ pip install -e .
```

## Usage patterns

You can find some exmaples of usage in [patterns](./patterns/).

### Single repository scan

![custom-repo-scan](doc/images/custom-repo-scan.png)

1. clone repository (e.g. IBM/Ansible-OpenShift-Provisioning in GitHub-RHIBM)

```
cd /tmp
git clone git@github.com:IBM/Ansible-OpenShift-Provisioning.git
cd Ansible-OpenShift-Provisioning
```

2. configure ARI KB
```
export ARI_KB_DATA_DIR=/Users/mue/Downloads/ram-all-20230613/
```

3. do custom scan for the repository
```
python patterns/custom_scan/custom_scan.py \
  -d /tmp/Ansible-OpenShift-Provisioning \
  -o /tmp/test/sage_dir
```

output is below
```
/tmp/test
└── sage_dir
    ├── ftdata.json  # ftdata
    ├── scan_result.json  # object data scanned by ARI
    └── yml_inventory.json  # inventory file including all YAML files
```

4. add new context to existing ftdata
```
python patterns/enrich_context/tools/add_enrich_context.py \
  --sage-dir /tmp/test/sage_dir \
  --ftdata ~/ftdata/5.5.2/awft_v5.5.2_train.json \
  --out-dir /tmp/test/tmp_dir \
  -t GitHub-RHIBM \
  -r IBM/Ansible-OpenShift-Provisioning
```

output is below
```
/tmp/test
├── tmp_dir
│   ├── modified_ftdata.json # updated records
│   └── only_org_ftdata.json # unchanged records
└── sage_dir
    ├── ftdata-modified.json # updated ftdata (including both updated and unchanged)
    ├── ftdata.json
    ├── scan_result.json
    └── yml_inventory.json
```

### Batch scan with source json file

![enrich-context](doc/images/enrich-context.png)

1. Do custom scan for all GitHub-RHIBM source with source json file.
```
python patterns/custom_scan/custom_scan_all.py \
  -t GitHub-RHIBM \
  -s /tmp/RH_IBM_FT_data_GH_api.json \
  -o /tmp/batch
```

The output structure is blow.
```
/tmp/batch
├── path_list
│   └── path-list-GitHub-RHIBM.txt  #path list loaded from source json file
├── results  #scanned results under here
│   └── GitHub-RHIBM
│       ├── IBM
│       ├── IBM-Blockchain-Archive
│       ├── IBM-Cloud
│       ├── IBM-ICP-CoC
│       ├── IBM-ICP4D
│       ├── IBM-Security
│       └── RedHatOfficial
└── src_rb  # source directory recreated from source json file
    └── GitHub-RHIBM
        ├── IBM
        ├── IBM-Blockchain-Archive
        ├── IBM-Cloud
        ├── IBM-ICP-CoC
        ├── IBM-ICP4D
        ├── IBM-Security
        └── RedHatOfficial

```

In `src_rb` dir, each repository file structure is reconstructed like below.
```
/tmp/batch/src_rb/GitHub-RHIBM/IBM/Ansible-OpenShift-Provisioning
├── inventories
│   └── default
├── mkdocs.yaml
├── playbooks
│   ├── 0_setup.yaml
│   ├── 1_create_lpar.yaml
│   ├── 2_create_kvm_host.yaml
│   ├── 3_setup_kvm_host.yaml
│   ├── 4_create_bastion.yaml
│   ├── 5_setup_bastion.yaml
│   ├── 6_create_nodes.yaml
│   ├── 7_ocp_verification.yaml
│   ├── site.yaml
│   └── test.yaml
└── roles
    ├── approve_certs
    ├── attach_subscription
    ├── check_dns
    ├── check_nodes
    ├── configure_storage
    ├── create_bastion
    ├── create_bootstrap
    ├── create_compute_nodes
    ├── create_control_nodes
    ├── create_kvm_host
    ├── create_lpar
    ├── dns
    ├── get_ocp
    ├── haproxy
    ├── httpd
    ├── install_packages
    ├── macvtap
    ├── prep_kvm_guests
    ├── reset_files
    ├── robertdebock.epel
    ├── robertdebock.openvpn
    ├── set_firewall
    ├── set_inventory
    ├── ssh_agent
    ├── ssh_copy_id
    ├── ssh_key_gen
    ├── ssh_ocp_key_gen
    ├── update_cfgs
    ├── wait_for_bootstrap
    ├── wait_for_cluster_operators
    └── wait_for_install_complete
```

2. Before processing large ftdata, it needs to be splitted per repo_name and source.
```
python patterns/enrich_context/tools/split_ftdata.py \
  -f ~/ftdata/5.5.2/awft_v5.5.2_train.json \
  -d /tmp/ftdata/5.5.2
```

After running the command above, the ftdata is stored in a directory per repository.
```
/tmp/ftdata/5.5.2/GitHub-RHIBM/IBM
├── Ansible-OpenShift-Provisioning
├── Simplify-Mainframe-application-deployments-using-Ansible
├── ansible-automation-for-lmt
├── ansible-for-i
├── ansible-for-i-usecases
├── ansible-kubernetes-ha-cluster
....
```

3. Run batch processing to add new context to existing ftdata
```
python patterns/enrich_context/tools/add_enrich_context_all.py \
  --sage-dir /tmp/batch/results \
  --ftdata-dir /tmp/ftdata/5.5.2 \
  --out-dir /tmp/batch/tmp \
  -t GitHub-RHIBM
```

Intenrally, ftdata generated at b2 is mapped with original ftdata by using similarity matching, and then relevant task is updated.
```
/tmp/batch/tmp/GitHub-RHIBM/IBM/Ansible-OpenShift-Provisioning
├── modified_ftdata.json   # only updated tasks included
└── only_org_ftdata.json   # unchanged tasks included
```

Then, the new ftdata file is created. The data is identical to original ftdata except additiona new context value. 
```
/tmp/batch/results/GitHub-RHIBM/IBM/Ansible-OpenShift-Provisioning
├── ftdata-modified.json  # new ftdata (new context added)
├── ftdata.json
├── scan_result.json
└── yml_inventory.json
```
