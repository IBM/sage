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
from sage_scan.models import (
    Project,
    Playbook,
    TaskFile,
    Task,
)
import os
import time
import traceback
from celery import Celery
from ansible_risk_insight.models import Module as ARIModule
from ansible_risk_insight.risk_assessment_model import RAMClient


dp = SagePipeline(silent=True)


REDIS_SERVER_URL = os.getenv("REDIS_SERVER_URL", 'localhost')
REDIS_SERVER_PORT = int(os.getenv("REDIS_SERVER_PORT", '6379'))
REDIS_SERVER_DB = int(os.getenv("REDIS_SERVER_DB", '0'))

SINGLE_SCAN_TIMEOUT = int(os.getenv("SINGLE_SCAN_TIMEOUT", '450'))

CELERY_BROKER_URL = f"redis://{REDIS_SERVER_URL}:{REDIS_SERVER_PORT}/1"
CELERY_RESULT_BACKEND = f"redis://{REDIS_SERVER_URL}:{REDIS_SERVER_PORT}/2"


celery = Celery(__name__)
celery.conf.broker_url = CELERY_BROKER_URL
celery.conf.result_backend = CELERY_RESULT_BACKEND


ARI_KB_DATA_DIR = os.getenv("ARI_KB_DATA_DIR", "<PATH/TO/YOUR_ARI_KB_DATA_DIR>")

if ARI_KB_DATA_DIR.startswith("<PATH"):
    raise ValueError("Please set environment variable `ARI_KB_DATA_DIR` with your KB direcotry")


ram_client = RAMClient(root_dir=ARI_KB_DATA_DIR)


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
    module_list = []
    collection_list = []
    target_filepath = playbook_or_taskfile.filepath
    for obj in objects:
        if not isinstance(obj, Task):
            continue
        if obj.filepath != target_filepath:
            continue
        module_name = obj.get_annotation("module.fqcn", "")
        if module_name:
            module_list.append(module_name)
        collection_name = obj.get_annotation("module.collection_name", "")
        if not collection_name:
            continue
        if collection_name not in collection_list:
            collection_list.append(collection_name)
    collection_list = sorted(collection_list)
    playbook_or_taskfile.set_annotation("module.list", module_list)
    playbook_or_taskfile.set_annotation("module.count", len(module_list))
    playbook_or_taskfile.set_annotation("collection.list", collection_list)
    playbook_or_taskfile.set_annotation("collection.count", len(collection_list))
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
    project.set_annotation("collection.count", len(collection_list))
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


@celery.task(name='tasks.scan')
def scan(dir_path: str, source_type: str, repo_name: str, out_dir: str) -> dict:
    source = {
        "type": source_type,
        "repo_name": repo_name,
    }
    result = {
        "success": None,
        "error": None,
        "begin": time.time(),
        "end": None,
    }
    err = None
    try:
        _ = dp.run(
            target_dir=dir_path,
            output_dir=out_dir,
            source=source,
            process_fn=process_fn,
        )
    except Exception:
        err = traceback.format_exc()
    finally:
        success = False if err else True
        result["success"] = success
        if not success:
            result["error"] = err
        result["end"] = time.time()
    return result
