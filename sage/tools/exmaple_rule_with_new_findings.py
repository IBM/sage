import os
import argparse
import json
from sage.process.models import load_objects
from sage.process.utils import get_tasks, get_annotation
from sage.models import Task, Playbook, TaskFile
from sage.utils import load_new_fidnings
from ansible_risk_insight.models import MutableContent
from ansible_risk_insight.risk_assessment_model import RAMClient


def gen_ftdata(task: Task, parent: Playbook | TaskFile):
    record = {
        "license": "",
        "license_check": "",
        "source": "",
        "path": "",
        "repo_name": "",
        "type": "",
        "prompt": "",
        "input_script": "",
        "metrics": {},
        "output_script": "",
        "token_count": 0,
        "op_token_count": 0,
        "sample_type": 0,
        "context_len": 0,
        "module_name": "",

        # "id": "0.0.0-2",
        # "prompt_key": "updateaptcache",
        # "ari_new_context": "- name: Converge\n  hosts: all\n  become: true\n  pre_tasks: null\n",
        # "is_context_updated": False,
        # "scan_type": "project",
        "ari_task_key": "",
        # "scan_path": "/Users/pingel/git_repos/github.ibm.com/ansible-risk-insight/sage/input/galaxy/github.com/geerlingguy/ansible-role-fathom"
    }
    record["source"] = task.source.get("type", "")
    record["repo_name"] = task.source.get("repo_name", "")
    record["path"] = task.filepath
    _type = ""
    if isinstance(parent, Playbook):
        _type = "playbook"
    elif isinstance(parent, TaskFile):
        _type = "task"
    record["type"] = _type

    task_name = task.name
    yaml_lines = task.yaml_lines

    prompt = ""
    output_script = yaml_lines
    if task_name:
        parts = yaml_lines.split(task_name)
        prompt = parts[0] + task_name
        output_script = parts[1].lstrip(" ").lstrip("\n")

    record["prompt"] = prompt
    record["output_script"] = output_script

    parent_yaml = parent.yaml_lines
    task_line_num = task.line_num_in_file[0]
    input_script = "\n".join(parent_yaml.splitlines()[:task_line_num])
    record["input_script"] = input_script
    record["module_name"] = task.module_info.get("fqcn", "")
    record["ari_task_key"] = task.key
    return record


def main():
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--file", help='input json file')
    parser.add_argument("-o", "--output", help='output json file')
    args = parser.parse_args()

    fpath = args.file

    sage_objects = load_objects(fpath)
    projects = sage_objects.projects()
    project = projects.filter(source_type="GitHub-RHIBM", repo_name="IBM/Ansible-OpenShift-Provisioning")
    playbooks = project.playbooks
    # TODO: determine how to handle roles / taskfiles
    roles = project.roles
    taskfiles = project.taskfiles

    record_lines = []
    for p in playbooks:
        tasks = get_tasks(root=p, project=project)
        for t in tasks:
            record = gen_ftdata(task=t, parent=p)
            record_lines.append(json.dumps(record) + "\n")

    for tf in taskfiles:
        tasks = get_tasks(root=tf, project=project)
        for t in tasks:
            record = gen_ftdata(task=t, parent=tf)
            record_lines.append(json.dumps(record) + "\n")

    output_path = args.output
    if output_path:
        with open(output_path, "w") as file:
            file.write("".join(record_lines))    


if __name__ == "__main__":
    main()