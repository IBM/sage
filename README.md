# sage-data-pipeline

This project is a data pipeline framework and practical examples for generating/processing task data like the fine-tuning data for various purposes.

The pipeline framework utilizes Ansible Risk Insight to parse Ansible content in YAML files (or prompt string in an existing FT data) and to apply configured rules for processing data depending on use-cases.

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

![custom-repo-scan](doc/images/enrich-context.png)

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
