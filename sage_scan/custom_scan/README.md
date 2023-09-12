# Custom Scan with SagePipeline

## Running custom scan

1. Install this project
    ```
    $ git clone https://github.ibm.com/ansible-risk-insight/sage.git
    $ cd sage
    $ pip install -e .
    ```

2. Run the following command

    #### 2 arguments in the command below
    
    - `PATH/TO/PROJECT` ... Path to your target project to be processed with the pipeline. The directory can be an ansible project(repository), collection or role.
      - If you want to input a single playbook/taskfile, you can specify a directory which contains the file here.
    
    - `OUTPUT_DIR` ... Path to the output directory. This will be created if it does not exist.

    ```
    $ python sage_scan/custom_scan/custom_scan.py -d <PATH/TO/PROJECT> -o <OUTPUT_DIR>
    ```

3. Confirm the output files

    The following 5 output files should be created in the specfied output directory.

    ```
    $ ls -l <OUTPUT_DIR>
    total 120
    -rw-r--r--  1 hiro  wheel  10720  7 21 17:26 findings.json
    -rw-r--r--  1 hiro  wheel   2864  7 21 17:26 ftdata.json
    -rw-r--r--  1 hiro  wheel  30664  7 21 17:26 result.json
    -rw-r--r--  1 hiro  wheel   6050  7 21 17:26 scan_result.json
    -rw-r--r--  1 hiro  wheel    292  7 21 17:26 yml_inventory.json
    ```

    - `findings.json` ... All the Ansible contents scanned by ARI are stored as ARI objects per its type such as `playbooks`, `taskfiles`, `roles` and `tasks`.
    - `ftdata.json` ... Each line is task data JSON which is scanned by ARI. It is in the same format as FT Data and it has the same attributes such as `input_script` and `prompt`. Some additional field like `ari_new_context` or `ari_task_key` are added by the custom rule.
    - `result.json` ... This file is for all useful data as scan results by the pipeline. It contains the following 3 data; `inventory` is yml_inventory data described below, `ftdata` is the ftdata above, `objects` is call tree data for every single callable unit (playbook/taskfile/role).
    - `scan_result.json` ... Each line is a task object JSON. All the scanned tasks are saved as ARI's Task object here.
    - `yml_inventory.json` ... All the found YAML files are recorded as a JSON string in each line. The pipeline adds some metadata about the file such as the file type like `playbook` and `taskfile` and the role info if the file is inside a role.


## Usage of a result file from the pipeline

1. YAML inventory

    You can see `inventory` to check all the found YAML files and how they are processed by sage.
    The actual inventory data is something like this.

    ```bash
    $ cat /sample_output/result.json | jq .inventory
    [
        {
            "filepath": "sample_project/roles/sample_role/tasks/main.yaml",
            "path_from_root": "roles/sample_role/tasks/main.yaml",
            "label": "taskfile",
            "project_info": {
                "name": "sample_project",
                "path": "path/to/sample_project"
            },
            "role_info": {
                "name": "sample_role",
                "path": "path/to/sample_project/roles/sample_role",
                "is_external_dependency": false
            },
            "in_project": true,
            "in_role": true,
            "task_scanned": true,
            "scanned_as": "project"
        },
        ...
    ```
    The example file above is labeled as a `taskfile` which is inside a role. You can get some details about it by `role_info` attribute.

2. Fine-Tuning Data

    `ftdata` is a list of every single task found in the specified project.
    The data format is same as the original fine-tuning data, but it has several additional attributes such as `ari_new_context`.

    ```bash
    $ cat /sample_output/result.json | jq .ftdata
    {
        "license": "",
        "license_check": "",
        "source": "",
        "path": "roles/sample_role/tasks/main.yaml",
        "repo_name": "",
        "type": "taskfile",
        "prompt": "- name: find absolute path to project.",
        "input_script": "---\n\n- name: Find inventory directory from ansible.cfg\n  tags: set_inventory\n  shell: cat {{ ansible_config_file }} | grep 'inventory=' | cut -f2 -d\"=\"\n  register: find_inventory\n",
        "metrics": {},
        "output_script": "- name: Find absolute path to project.\n  tags: set_inventory\n  shell: |\n    set -o pipefail\n    ansible_config=\"{{ ansible_config_file }}\"\n    echo \"${ansible_config%/*}/\"\n  register: find_project\n",
        "token_count": 0,
        "op_token_count": 0,
        "sample_type": 0,
        "context_len": 484,
        "module_name": "ansible.builtin.shell",
        "id": "0.0.0.0.1-4",
        "prompt_key": "findabsolutepathtoproject",
        "ari_new_context": "- name: define variables\n  ansible.builtin.set_fact:\n    find_inventory: '{{ find_inventory }}'\n- name: import role\n  ansible.builtin.import_role:\n    name: sample_role\n- name: import tasks\n  ansible.builtin.import_tasks:\n    file: roles/sample_role/tasks/main.yaml\n- name: Find inventory directory from ansible.cfg\n  tags: set_inventory\n  shell: cat {{ ansible_config_file }} | grep 'inventory=' | cut -f2 -d\"=\"\n  register: find_inventory\n",
        "is_context_updated": true,
        "scan_type": "project",
        "ari_task_key": "task role:sample_role#taskfile:roles/sample_role/tasks/main.yaml#task:[1]",
        "scan_path": "sample_project"
    },
    ...
    ```

3. Objects (Call Trees)

    `objects` are detail data of the task call tree. Each element is a call tree in the execution order and it is starting from callable unit in Ansible like playbook, role, and taskfile. You can use this data in order to traverse all the tasks found in the project and to add some data dependeing on your requirements.

    We have [an example script](../../sage_scan/tools/show_all_fqcn_from_result.py) which traverses all tasks and convert module short name to FQCN.
    You can learn how to use the `objects` data from the example.

    ```bash
    $ python sage_scan/tools/show_all_fqcn_from_result.py -f /sample_output/result.json
    SHORT_NAME    FQCN
    ------------  -----------------------
    debug         ansible.builtin.debug
    ufw           community.general.ufw
    ec2_instance  amazon.aws.ec2_instance
    ```




