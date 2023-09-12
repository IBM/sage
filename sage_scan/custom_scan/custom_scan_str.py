# -*- mode:python; coding:utf-8 -*-

# Copyright (c) 2023 IBM Corp. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

from sage_scan.pipeline import SagePipeline


EXAMPLE = '''
---
- name: AWS EC2 Cloud Operations
  hosts: localhost
  gather_facts: false

  vars:
    image_id: ami-016eb5d644c333ccb
    key_name: app-keypair
    security_groups:
      - ansibull-sg

  tasks:
    - name: Create a key pair in us-east-2 called app-keypair
      ec2_key:
        name: app-keypair
        region: us-east-2
      register: ec2_key

    - name: Create a t3.medium instance called app-instance-01
      ec2_instance:
        key_name: "{{ key_name }}"
        name: app-instance-01
        image_id: "{{ image_id }}"
        instance_type: t3.medium
        vpc_subnet_id: "{{ vpc_subnet_id }}"
        security_group: "{{ security_group }}"
        network:
          assign_public_ip: true
        tags:
          Environment: Testing
      register: ec2
'''


def main():
    input_yaml = EXAMPLE

    sp = SagePipeline()

    # process the input playbook by SagePipeline
    project = sp.run(
        raw_yaml=input_yaml,
    )

    # Here you can do anything with `project` which is a SageProject object (=pipeline output)


if __name__ == '__main__':
    main()

