# Adding enriched context to existing fine-tuning data set

Currently context has the dump of content before the prompt. It is sensitive to new lines, identification. It could be sometimes a playbook, sometime a taskfile in a role. 

For example, let's see the block [here](https://github.com/pulse-mind/ansible-rabbitmq/blob/master/tasks/debian.yml#L45-L52).

```yaml
- name: debian | installing RabbitMQ server
  apt:
    name:
      - rabbitmq-server{{ (rabbitmq_debian_version_defined and rabbitmq_debian_version is defined) | ternary(['=',rabbitmq_debian_version] | join(''),'') }}
    state: present
  become: true
  register: result
  until: result is successful
```
In this case, prompt is `- name: debian | installing RabbitMQ server` then expected Wisdom AI to produce this block. Current context is the [content](https://github.com/pulse-mind/ansible-rabbitmq/blob/master/tasks/debian.yml#L1-L43) above the prompt. 

<img width="560" alt="context-before" src="https://user-images.githubusercontent.com/26372857/223874775-6d25e979-fce8-4bbe-9517-4854808f0577.png">

In the new approach by Sage, the context is like [this](./sample-enriched-context.yml#L1-L43). The project content is parsed as Ansible content (not just as YAML) and analyzed to extract essential infromation as context from there. This includes

<img width="743" alt="context-after" src="https://user-images.githubusercontent.com/26372857/223874792-d3959db8-fa67-4570-998f-0bf1db5d9a39.png">

- all the relevent call path information is added into the context. For example, if the task is called from role A, `import_role` task is inserted to represent the role A information from role metadata. if the task file including the task is called from import_task, the name of task calling the import_task module is added as "import_task". 
- all variables and assigned values available at the beginning of the file. this provides better understanding what variables can be used in the suggestion.
- modified context does not violate Ansible format. This is required for avoiding unexpected side-effect to the model training. 
- easy to add more info such as comments or trim unnecessary parts to reduce the num of tokens. 

```yaml
- name: define variables
  ansible.builtin.set_fact:
    rabbitmq_config: []
    rabbitmq_config_ha: false
    rabbitmq_config_service: false
    rabbitmq_config_file: etc/rabbitmq/rabbitmq.config.j2
    rabbitmq_config_env_file: etc/rabbitmq/rabbitmq-env.conf.j2
    rabbitmq_env_config: {}
    rabbitmq_debian_repo: 'deb https://dl.bintray.com/rabbitmq/debian {{ ansible_distribution_release
      }} main #bintray'
    rabbitmq_debian_repo_key: https://bintray.com/user/downloadSubjectPublicKey?username=rabbitmq
    rabbitmq_debian_erlang_from_rabbit: true
    rabbitmq_debian_version_defined: true
    rabbitmq_debian_version: 3.8.11-1
    rabbitmq_enable_clustering: false
    rabbitmq_master: None
    rabbitmq_erlang_cookie_file: /var/lib/rabbitmq/.erlang.cookie
    rabbitmq_listen_port: 5672
    rabbitmq_listeners: []
    rabbitmq_ssl_enable: false
    rabbitmq_ssl_port: 5671
    rabbitmq_ssl_listeners: []
    rabitmq_ssl_options: {}
    rabbitmq_redhat_repo_key: https://github.com/rabbitmq/signing-keys/releases/download/2.0/rabbitmq-release-signing-key.asc
    rabbitmq_redhat_package: rabbitmq-server-{{ rabbitmq_redhat_version }}-1.el{{
      ansible_distribution_major_version }}.noarch.rpm
    rabbitmq_redhat_url: https://dl.bintray.com/rabbitmq/rpm/rabbitmq-server/v3.8.x/el/{{
      ansible_distribution_major_version }}/noarch
    rabbitmq_redhat_version: 3.8.11
    rabbitmq_extra_vhosts: []
    rabbitmq_users:
    - name: rabbitmqadmin
      password: rabbitmqadmin
      vhost: /
      configure_priv: .*
      read_priv: .*
      write_priv: .*
      tags: administrator
    result: '{{ result }}'
- name: Ansible role to install/configure RabbitMQ
  ansible.builtin.import_role:
    name: ansible-rabbitmq
- name: import tasks
  ansible.builtin.import_tasks:
    file: tasks/main.yml
- name: import tasks
  ansible.builtin.import_tasks:
    file: tasks/debian.yml
- name: debian | Adding Pre-Reqs
  apt:
    name:
    - gnupg2
    - apt-transport-https
    state: present
    update_cache: true
  become: true
  register: result
  until: result is successful
- name: debian | adding RabbitMQ public GPG key to the apt repo
  apt_key:
    url: '{{ rabbitmq_debian_repo_key }}'
    state: present
  become: true
  register: result
  until: result is successful
- name: debian | adding RabbitMQ repo
  apt_repository:
    repo: '{{ rabbitmq_debian_repo }}'
    state: present
  become: true
  register: result
  until: result is successful
- name: debian | add Rabbitmq erlang repo key
  apt_key:
    url: https://bintray.com/user/downloadSubjectPublicKey?username=rabbitmq-erlang
    state: present
  become: true
  register: result
  until: result is successful
  when: rabbitmq_debian_erlang_from_rabbit
- name: debian | add Rabbitmq erlang repo
  apt_repository:
    repo: deb https://dl.bintray.com/rabbitmq-erlang/debian {{ ansible_distribution_release
      }} erlang
    state: present
  become: true
  when: rabbitmq_debian_erlang_from_rabbit
```

For creating the enriched context, original source files in a parent project need to be scanned. Sage can be used for the processing. 

![enrich-context](./images/enrich-context.png)

- c1: find `source` value from original ftdata, then identify source json line file. For example, `source` is `GitHub-RHIBM` and source json file is `RH_IBM_FT_data_GH_api.json` on CCC. 
- c2: recover source directory from source json file by 
  ```
  python patterns/enrich_context/tools/split_ftdata.py \
    -f ~/ftdata/5.5.2/awft_v5.5.2_train.json \
    -d /tmp/ftdata/5.5.2  
  ```
  For example, The source directroy for repo `IBM/Ansible-OpenShift-Provisioning` in `GitHub-RHIBM` source is created in `/tmp/batch/src_rb/GitHub-RHIBM/IBM/Ansible-OpenShift-Provisioning`
- c3-c5: Do Sage Ansible Repository Scanning (see b1-b3 in single repository scan), then the following data is created. 
  ```
  /tmp/batch/results/GitHub-RHIBM/IBM/Ansible-OpenShift-Provisioning
  ├── ftdata.json # newly computed data including new context
  ├── scan_result.json
  └── yml_inventory.json
  ```
- c6: Compare new data and original ftdata, find mached task, then insert new context value. 
