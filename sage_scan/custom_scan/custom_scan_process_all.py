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

from sage_scan.pipeline import SagePipeline
import os
import traceback
import json
import time
import argparse
from sage_scan.models import Task, Playbook, TaskFile, Project
from sage_scan.tools.src_rebuilder import write_result, prepare_source_dir
from ansible_risk_insight.risk_assessment_model import RAMClient
from ansible_risk_insight.models import (
    Module as ARIModule,
)



ARI_KB_DIR = os.getenv("ARI_KB_DIR", "<PATH/TO/YOUR_ARI_KB_DIR>")

if ARI_KB_DIR.startswith("<PATH"):
    raise ValueError("Please set environment variable `ARI_KB_DIR` with your KB direcotry")


ram_client = RAMClient(root_dir=ARI_KB_DIR)


def get_module_name_from_task(task: Task, use_ram=True):
    module_name = ""
    if task.module_info and isinstance(task.module_info, dict):
        module_name = task.module_info.get("fqcn", "")
    if task.annotations:
        if not module_name:
            module_name = task.annotations.get("module.correct_fqcn", "")
        if not module_name:
            module_name = task.annotations.get("correct_fqcn", "")
    if not module_name:
        if use_ram and "." not in task.module:
            matched = ram_client.search_module(task.module)
            if matched and isinstance(matched[0], dict):
                module = matched[0].get("object", None)
                if isinstance(module, ARIModule):
                    module_name = module.fqcn
    if not module_name:
        module_name = task.module
    
    module_short_name = module_name
    if "." in module_short_name:
        module_short_name = module_short_name.split(".")[-1]

    return module_name, module_short_name


def process_task(task: Task):
    module_name, _ = get_module_name_from_task(task=task, use_ram=True)
    if module_name and "." in module_name:
        parts = module_name.split(".")
        collection_name = parts[0] + "." + parts[1]
        task.set_annotation("module.fqcn", module_name)
        task.set_annotation("module.collection_name", collection_name)
    return task


def process_playbook_or_taskfile(playbook_or_taskfile: Playbook|TaskFile, objects: list):
    collection_list = []
    target_filepath = playbook_or_taskfile.filepath
    for obj in objects:
        if not isinstance(obj, Task):
            continue
        if obj.filepath != target_filepath:
            continue
        collection_name = obj.get_annotation("module.collection_name", "")
        if not collection_name:
            continue
        if collection_name not in collection_list:
            collection_list.append(collection_name)
    collection_list = sorted(collection_list)
    playbook_or_taskfile.set_annotation("collection.list", collection_list)
    return playbook_or_taskfile


def process_project(project: Project, objects: list):
    collection_list = []
    for obj in objects:
        if not isinstance(obj, Task):
            continue
        collection_name = obj.get_annotation("module.collection_name", "")
        if not collection_name:
            continue
        if collection_name not in collection_list:
            collection_list.append(collection_name)
    collection_list = sorted(collection_list)
    project.set_annotation("collection.list", collection_list)
    return project


def process_fn(objects):
    # first process tasks
    for i, obj in enumerate(objects):
        if not isinstance(obj, Task):
            continue
        objects[i] = process_task(task=objects[i])

    # then process playbook / taskfile using task info
    for i, obj in enumerate(objects):
        if not isinstance(obj, (Playbook, TaskFile)):
            continue
        objects[i] = process_playbook_or_taskfile(playbook_or_taskfile=objects[i], objects=objects)

    # eventually process project (normally there is only one project in `objects`)
    for i, obj in enumerate(objects):
        if not isinstance(obj, Project):
            continue
        objects[i] = process_project(project=objects[i], objects=objects)

    return objects


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TODO")
    # parser.add_argument("-t", "--source-type", help='source type (e.g."GitHub-RHIBM")')
    # parser.add_argument("-s", "--source-json", help='source json file path (e.g. "/tmp/RH_IBM_FT_data_GH_api.json")')
    parser.add_argument("-f", "--file", help='path to a list of source.json filepaths')
    parser.add_argument("-d", "--base-dir", help="source json base directory")
    parser.add_argument("-o", "--out-dir", help="output directory")
    parser.add_argument("-e", "--error-log", help='error log file')
    # parser.add_argument("-t", "--timeout", default="120", help='timeout seconds for each project')
    args = parser.parse_args()

    src_json_list_file = args.file
    src_json_base_dir = args.base_dir
    src_json_list = []
    with open(src_json_list_file, "r") as file:
        for line in file:
            relative_path = line.strip()
            parts = relative_path.split("/")
            src_type = parts[0]
            repo_name = "/".join(parts[1:-1]) if len(parts) > 2 else parts[1]
            path = os.path.join(src_json_base_dir, relative_path)
            src_json_list.append((src_type, repo_name, path))

    work_dir = args.out_dir
    src_rb_dir = os.path.join(work_dir, "src_rb")
    path_list_dir = os.path.join(work_dir, "path_list")
    result_dir = os.path.join(work_dir, "results")
    err_file = args.error_log

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(src_rb_dir, exist_ok=True)
    os.makedirs(path_list_dir, exist_ok=True)
    os.makedirs(result_dir, exist_ok=True)

    dp = SagePipeline(silent=True)
    out_scope = [
        "IBM/playbook-integrity-operator",
        "RedHatOfficial/ansible-role-rhv4-rhvh-stig",
        "confluent.platform",
        "bosh-io/releases-index"
    ]

    total = len(src_json_list)

    for i, (src_type, repo_name, src_json) in enumerate(src_json_list):
        if repo_name in out_scope:
            print(f"skip {repo_name} ({i+1}/{total})")
            continue

        adir = os.path.join(src_rb_dir, src_type)
        tdir = os.path.join(src_rb_dir, src_type, repo_name)
        odir = os.path.join(result_dir, src_type, repo_name)

        print(f"scanning {repo_name} ({i+1}/{total})")

        err = None
        try:
            prepare_source_dir(root_dir=adir, src_json=src_json)
            dp.run(
                target_dir=tdir,
                output_dir=odir,
                source={"type": src_type, "repo_name": repo_name},
                process_fn=process_fn,
            )
        except Exception:
            err = traceback.format_exc()

        if err and err_file:
            with open(err_file, "a") as efile:
                efile.write(f"{repo_name} ({i+1}/{total})\n")
                efile.write(err + "\n")
                efile.write("-" * 90 + "\n")
