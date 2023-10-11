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
    parser.add_argument("-t", "--source-type", help='source type (e.g."GitHub-RHIBM")')
    parser.add_argument("-s", "--source-json", help='source json file path (e.g. "/tmp/RH_IBM_FT_data_GH_api.json")')
    parser.add_argument("-o", "--out-dir", help="output directory")
    parser.add_argument("-p", "--project-list", help="project list")
    parser.add_argument("--yml-inventory-only", action="store_true", help="yml inventory only mode")
    args = parser.parse_args()

    work_dir = args.out_dir
    src_type = args.source_type
    src_json = args.source_json
    project_list = args.project_list
    yml_inventory_mode = args.yml_inventory_only
    src_rb_dir = os.path.join(work_dir, "src_rb")
    path_list_dir = os.path.join(work_dir, "path_list")
    result_dir = os.path.join(work_dir, "results")

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(src_rb_dir, exist_ok=True)
    os.makedirs(path_list_dir, exist_ok=True)
    os.makedirs(result_dir, exist_ok=True)

    adir = os.path.join(src_rb_dir, src_type)
    if not os.path.exists(adir) or len(os.listdir(adir)) == 0:
        outfile = os.path.join(path_list_dir, f"path-list-{src_type}.txt")
        path_list = prepare_source_dir(adir, src_json)
        write_result(outfile, path_list)

    if src_json:
        with open(src_json, "r") as f:
            records = f.readlines()
        repo_names = set()
        for record in records:
            r = json.loads(record)
            if "repo_name" in r:
                repo_names.add(r.get("repo_name"))
            if "namespace_name" in r:
                repo_names.add(r.get("namespace_name"))

    if project_list:
        with open(project_list, "r") as f:
            repo_names = [s.rstrip() for s in f.readlines()]

    total = len(repo_names)
    count = 0

    out_scope = [
        "IBM/playbook-integrity-operator",
        "RedHatOfficial/ansible-role-rhv4-rhvh-stig",
        "confluent.platform",
        "bosh-io/releases-index"
    ]

    dp = SagePipeline()

    timer_path = "/tmp/custom-scan-all-timer.json"
    for repo_name in repo_names:
        if repo_name in out_scope:
            print(f"skip {repo_name} ({count}/{total})")
            count += 1
            continue

        start = time.time()
        tdir = os.path.join(src_rb_dir, src_type, repo_name)
        odir = os.path.join(result_dir, src_type, repo_name)
        if os.path.exists(os.path.join(odir, "ftdata.json")):
            count += 1
            continue

        # why needed?
        os.environ["SAGE_CONTENT_ANALYSIS_OUT_DIR"] = odir

        print(f"scanning {repo_name} ({count}/{total})")

        dp.run(
            target_dir=tdir,
            output_dir=odir,
            source={"type": src_type, "repo_name": repo_name},
            yml_inventory_only=yml_inventory_mode,
            process_fn=process_fn,
        )
        count += 1

        end = time.time()
        elapsed = end - start
        timer_record = {
            "repo_name": repo_name,
            "elapsed": elapsed,
        }
        with open(timer_path, "a+") as file:
            file.write(json.dumps(timer_record) + "\n")
        