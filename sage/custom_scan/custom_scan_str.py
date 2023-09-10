import os

from sage.pipeline import SagePipeline


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

