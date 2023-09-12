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
from dataclasses import dataclass
from sage_scan.models import (
    Task,
    Module,
    SageProject,
)
from sage_scan.process.annotations import MODULE_OBJECT_ANNOTATION_KEY
from ansible_risk_insight.models import (
    ExecutableType,
    Module as ARIModule,
    ActionGroupMetadata,
    VariableType,
)
from ansible_risk_insight.risk_assessment_model import RAMClient


SAGE_KB_DATA_DIR = os.getenv("SAGE_KB_DATA_DIR", None)

# alias
if not SAGE_KB_DATA_DIR:
    SAGE_KB_DATA_DIR = os.getenv("ARI_KB_DATA_DIR", None)


@dataclass
class KnowledgeBase(object):
    kb_client: RAMClient = None

    def __post_init__(self):
        if not self.kb_client:
            self.init_kb_client()

    def init_kb_client(self):
        if SAGE_KB_DATA_DIR is None:
            raise ValueError(f"Please specify an existing SAGE KB dir by an env param:\n$ export SAGE_KB_DATA_DIR=<PATH/TO/SAGE_KB_DATA_DIR>")

        if not os.path.exists(SAGE_KB_DATA_DIR):
            raise ValueError(f"the SAGE_KB_DATA_DIR does not exist: {SAGE_KB_DATA_DIR}")

        self.kb_client = RAMClient(root_dir=SAGE_KB_DATA_DIR)
        return

    def set_kb_client_from_ram_client(self, ram_client=None):
        if ram_client:
            self.kb_client = ram_client
        return

    def resolve_task(self, task: Task, set_module_object_annotation: bool=False):
        exec_type = task.executable_type
        include_types = [ExecutableType.ROLE_TYPE, ExecutableType.TASKFILE_TYPE]

        task = self.set_module_info(task, set_module_object_annotation)
        if exec_type in include_types:
            task = self.set_include_info(task)
        
        if exec_type == ExecutableType.MODULE_TYPE:
            if task.module_info and isinstance(task.module_info, dict):
                task.resolved_name = task.module_info.get("fqcn", "")
        elif exec_type == ExecutableType.ROLE_TYPE:
            if task.include_info and isinstance(task.include_info, dict):
                task.resolved_name = task.include_info.get("fqcn", "")
        elif exec_type == ExecutableType.TASKFILE_TYPE:
            if task.include_info and isinstance(task.include_info, dict):
                task.resolved_name = task.include_info.get("key", "")

        return task
    
    def set_module_info(self, task: Task, set_module_object_annotation: bool=False):
        if not isinstance(task, Task):
            raise ValueError(f"expect a task object, but {type(task)}")

        raw_module_name = task.module
        result = self.kb_client.search_module(name=raw_module_name)
        module = None
        if result and isinstance(result, list) and isinstance(result[0], dict):
            _module = result[0].get("object", None)
            if isinstance(_module, Module):
                module = _module
            elif isinstance(_module, ARIModule):
                module = Module.from_ari_obj(_module)
        if module:
            task.module_info = {
                "collection": module.collection,
                "short_name": module.name,
                "fqcn": module.fqcn,
                "key": module.key,
            }
            if set_module_object_annotation:
                task.set_annotation(MODULE_OBJECT_ANNOTATION_KEY, module)

        return task
    
    def set_include_info(self, task: Task):
        if not isinstance(task, Task):
            raise ValueError(f"expect a task object, but {type(task)}")

        exec_target = task.executable
        exec_type = task.executable_type
        include_info = {}
        if exec_type == ExecutableType.ROLE_TYPE:
            result = self.kb_client.search_role(name=exec_target)
            if not result:
                return task
            
            if not isinstance(result, list):
                return task
            
            if not isinstance(result[0], dict):
                return task
        
            role = result[0].get("object", None)
            if not role:
                return task
            
            include_info = {
                "type": "role",
                "fqcn": role.fqcn,
                "path": role.defined_in,
                "key": role.spec.key,
            }

        elif exec_type == ExecutableType.TASKFILE_TYPE:
            result = self.kb_client.search_taskfile(name=exec_target, is_key=True)
            if not result:
                return task
            
            if not isinstance(result, list):
                return task
            
            if not isinstance(result[0], dict):
                return task
        
            taskfile = result[0].get("object", None)
            if not taskfile:
                return task
            
            include_info = {
                "type": "taskfile",
                "path": taskfile.defined_in,
                "key": taskfile.key,
            }
        
        task.include_info = include_info
        return task


