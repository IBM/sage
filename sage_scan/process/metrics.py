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

from dataclasses import dataclass, field
import json

from sage_scan.models import (
    SageProject,
    Collection,
    Role,
    Playbook,
    Play,
    TaskFile,
    Task,
)
from sage_scan.process.utils import (
    get_used_vars,
)


@dataclass
class DataMetrics(object):
    # each metric value should be initialized with None
    # to clarify which value is computed or not
    num_of_tasks: int = None
    num_of_tasks_with_include_tasks: int = None
    num_of_tasks_with_include_role: int = None
    num_of_tasks_with_include_vars: int = None

    num_of_plays: int = None
    num_of_plays_with_vars: int = None
    num_of_plays_with_roles: int = None
    num_of_plays_with_import_playbook: int = None

    num_of_used_vars_defined_outside: int = None

    is_self_contained: bool = None


@dataclass
class PlaybookData(object):
    object: Playbook = None
    project: SageProject = None

    # attributes below are automatically set by __post_init__() 

    # parent if any
    collection: Collection = None
    role: Role = None

    # children / include targets
    playbooks: list = field(default_factory=list)
    plays: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    taskfiles: list = field(default_factory=list)
    tasks: list = field(default_factory=list)

    call_seq: list = field(default_factory=list)

    metrics: DataMetrics = field(default_factory=DataMetrics)

    def __post_init__(self):
        if not self.object:
            return
        
        if not self.project:
            return
        
        if self.object.collection:
            for coll in self.project.collections:
                if coll.fqcn == self.object.collection:
                    self.collection = coll
                    break

        if self.object.role:
            for role in self.project.roles:
                if role.fqcn == self.object.role:
                    self.role = role
                    break

        if not self.call_seq:
            call_seq = self.project.get_call_sequence_by_entrypoint(self.object)
            self.call_seq = call_seq

        for obj in self.call_seq:
            if isinstance(obj, Playbook):
                self.playbooks.append(obj)
            elif isinstance(obj, Play):
                self.plays.append(obj)
            elif isinstance(obj, Role):
                self.roles.append(obj)
            elif isinstance(obj, TaskFile):
                self.taskfiles.append(obj)
            elif isinstance(obj, Task):
                self.tasks.append(obj)

    def metrics_to_json(self):
        data = {}
        data["source"] = self.project.source
        data["filepath"] = self.object.filepath
        for k, v in self.metrics.__dict__.items():
            data[k] = v
        return json.dumps(data, separators=(',', ':'))

    def compute_metrics(self):
        self.metrics = DataMetrics()
        self.metrics.num_of_tasks = len(self.get_tasks_in_this_playbook())
        self.metrics.num_of_tasks_with_include_tasks = len(self.get_tasks_with_include_tasks())
        self.metrics.num_of_tasks_with_include_role = len(self.get_tasks_with_include_role())
        self.metrics.num_of_tasks_with_include_vars = len(self.get_tasks_with_include_vars())
        self.metrics.num_of_plays = len(self.get_plays_in_this_playbook())
        self.metrics.num_of_plays_with_vars = len(self.get_plays_with_vars())
        self.metrics.num_of_plays_with_roles = len(self.get_plays_with_roles())
        self.metrics.num_of_plays_with_import_playbook = len(self.get_plays_with_import_playbook())
        self.metrics.is_self_contained = self.is_self_contained()

        self.metrics.num_of_used_vars_defined_outside = 0
        return

    def get_tasks_in_this_playbook(self):
        return [t for t in self.tasks if t.filepath == self.object.filepath]

    def get_tasks_with_include_tasks(self):
        tasks_in_this_playbook = self.get_tasks_in_this_playbook()

        target_modules = [
            "import_tasks",
            "include_tasks",
            "include",
            "ansible.builtin.import_tasks",
            "ansible.builtin.include_tasks",
            "ansible.builtin.include",
        ]
        tasks_with_include_tasks = [
            t for t in tasks_in_this_playbook
            if t.module in target_modules or 
            t.get_annotation("module.correct_fqcn", "") in target_modules
        ]
        return tasks_with_include_tasks
    
    def get_tasks_with_include_role(self):
        target_modules = [
            "import_role",
            "include_role",
            "ansible.builtin.import_role",
            "ansible.builtin.include_role",
        ]
        tasks_in_this_playbook = self.get_tasks_in_this_playbook()
        tasks_with_include_role = [
            t for t in tasks_in_this_playbook
            if t.module in target_modules or 
            t.get_annotation("module.correct_fqcn", "") in target_modules
        ]
        return tasks_with_include_role
    
    def get_tasks_with_include_vars(self):
        target_modules = [
            "include_vars",
            "ansible.builtin.include_vars",
        ]
        tasks_in_this_playbook = self.get_tasks_in_this_playbook()
        tasks_with_include_vars = [
            t for t in tasks_in_this_playbook
            if t.module in target_modules or 
            t.get_annotation("module.correct_fqcn", "") in target_modules
        ]
        return tasks_with_include_vars

    def get_plays_in_this_playbook(self):
        return [p for p in self.plays if p.filepath == self.object.filepath]
    
    def get_plays_with_vars(self):
        plays_in_this_playbook = self.get_plays_in_this_playbook()
        plays_with_vars = [
            p for p in plays_in_this_playbook
            if p.variables
        ]
        return plays_with_vars

    def get_plays_with_roles(self):
        plays_in_this_playbook = self.get_plays_in_this_playbook()
        plays_with_roles = [
            p for p in plays_in_this_playbook
            if p.roles
        ]
        return plays_with_roles
    
    def get_plays_with_import_playbook(self):
        plays_in_this_playbook = self.get_plays_in_this_playbook()
        plays_with_import_playbook = [
            p for p in plays_in_this_playbook
            if p.import_playbook
        ]
        return plays_with_import_playbook


    def is_self_contained(self):
        if self.metrics.num_of_plays_with_import_playbook is None:
            self.metrics.num_of_plays_with_import_playbook = len(self.get_plays_with_import_playbook())
        if self.metrics.num_of_plays_with_import_playbook:
            return False

        if self.metrics.num_of_plays_with_roles is None:
            self.metrics.num_of_plays_with_roles = len(self.get_plays_with_roles())
        if self.metrics.num_of_plays_with_roles:
            return False
        
        if self.metrics.num_of_tasks_with_include_tasks is None:
            self.metrics.num_of_tasks_with_include_tasks = len(self.get_tasks_with_include_tasks())
        if self.metrics.num_of_tasks_with_include_tasks:
            return False
        
        if self.metrics.num_of_tasks_with_include_role is None:
            self.metrics.num_of_tasks_with_include_role = len(self.get_tasks_with_include_role())
        if self.metrics.num_of_tasks_with_include_role:
            return False
        
        if self.metrics.num_of_tasks_with_include_vars is None:
            self.metrics.num_of_tasks_with_include_vars = len(self.get_tasks_with_include_vars())
        if self.metrics.num_of_tasks_with_include_vars:
            return False
        
        return True


@dataclass
class TaskFileData(object):
    object: TaskFile = None
    project: SageProject = None

    # attributes below are automatically set by __post_init__() 

    # parent if any
    collection: Collection = None
    role: Role = None

    # children / include targets
    roles: list = field(default_factory=list)
    taskfiles: list = field(default_factory=list)
    tasks: list = field(default_factory=list)

    call_seq: list = field(default_factory=list)

    metrics: DataMetrics = field(default_factory=DataMetrics)

    def __post_init__(self):
        if not self.object:
            return
        
        if not self.project:
            return
        
        if self.object.collection:
            for coll in self.project.collections:
                if coll.fqcn == self.object.collection:
                    self.collection = coll
                    break

        if self.object.role:
            for role in self.project.roles:
                if role.fqcn == self.object.role:
                    self.role = role
                    break

        if not self.call_seq:
            call_seq = self.project.get_call_sequence_by_entrypoint(self.object)
            self.call_seq = call_seq

        for obj in self.call_seq:
            if isinstance(obj, Role):
                self.roles.append(obj)
            elif isinstance(obj, TaskFile):
                self.taskfiles.append(obj)
            elif isinstance(obj, Task):
                self.tasks.append(obj)

    def metrics_to_json(self):
        data = {}
        data["source"] = self.project.source
        data["filepath"] = self.object.filepath
        for k, v in self.metrics.__dict__.items():
            data[k] = v
        return json.dumps(data, separators=(',', ':'))

    def compute_metrics(self):
        self.metrics.num_of_tasks = len(self.get_tasks_in_this_taskfile())
        self.metrics.num_of_tasks_with_include_tasks = len(self.get_tasks_with_include_tasks())
        self.metrics.num_of_tasks_with_include_role = len(self.get_tasks_with_include_role())
        self.metrics.num_of_tasks_with_include_vars = len(self.get_tasks_with_include_vars())
        self.metrics.num_of_used_vars_defined_outside = len(self.get_used_vars_defined_outside())
        self.metrics.is_self_contained = self.is_self_contained()

        self.metrics.num_of_plays = 0
        self.metrics.num_of_plays_with_import_playbook = 0
        self.metrics.num_of_plays_with_roles = 0
        self.metrics.num_of_plays_with_vars = 0
        return

    def get_tasks_in_this_taskfile(self):
        return [t for t in self.tasks if t.filepath == self.object.filepath]

    def get_tasks_with_include_tasks(self):
        tasks_in_this_taskfile = self.get_tasks_in_this_taskfile()

        target_modules = [
            "import_tasks",
            "include_tasks",
            "include",
            "ansible.builtin.import_tasks",
            "ansible.builtin.include_tasks",
            "ansible.builtin.include",
        ]
        tasks_with_include_tasks = [
            t for t in tasks_in_this_taskfile
            if t.module in target_modules or 
            t.get_annotation("module.correct_fqcn", "") in target_modules
        ]
        return tasks_with_include_tasks
    
    def get_tasks_with_include_role(self):
        target_modules = [
            "import_role",
            "include_role",
            "ansible.builtin.import_role",
            "ansible.builtin.include_role",
        ]
        tasks_in_this_taskfile = self.get_tasks_in_this_taskfile()
        tasks_with_include_role = [
            t for t in tasks_in_this_taskfile
            if t.module in target_modules or 
            t.get_annotation("module.correct_fqcn", "") in target_modules
        ]
        return tasks_with_include_role
    
    def get_tasks_with_include_vars(self):
        target_modules = [
            "include_vars",
            "ansible.builtin.include_vars",
        ]
        tasks_in_this_taskfile = self.get_tasks_in_this_taskfile()
        tasks_with_include_vars = [
            t for t in tasks_in_this_taskfile
            if t.module in target_modules or 
            t.get_annotation("module.correct_fqcn", "") in target_modules
        ]
        return tasks_with_include_vars
    
    def get_used_vars_defined_outside(self):
        used_vars = get_used_vars(object=self.object, project=self.project)
        defined_vars_inside = {}
        tasks_in_this_taskfile = self.get_tasks_in_this_taskfile()
        for t in tasks_in_this_taskfile:
            if not isinstance(t, Task):
                continue
            if t.variables:
                defined_vars_inside.update(t.variables)
            if t.set_facts:
                defined_vars_inside.update(t.set_facts)
            if t.registered_variables:
                defined_vars_inside.update(t.registered_variables)
        used_vars_defined_outside = {}
        for used_var_name in used_vars:
            defined_inside = False
            for defined_var_name in defined_vars_inside:
                if used_var_name == defined_var_name:
                    defined_inside = True
                    break
                prefix = defined_var_name + "."
                if used_var_name.startswith(prefix):
                    defined_inside = True
                    break
            if not defined_inside:
                used_vars_defined_outside[used_var_name] = used_vars[used_var_name]
        return used_vars_defined_outside

    def is_self_contained(self):
        if self.metrics.num_of_tasks_with_include_tasks is None:
            self.metrics.num_of_tasks_with_include_tasks = len(self.get_tasks_with_include_tasks())
        if self.metrics.num_of_tasks_with_include_tasks:
            return False
        
        if self.metrics.num_of_tasks_with_include_role is None:
            self.metrics.num_of_tasks_with_include_role = len(self.get_tasks_with_include_role())
        if self.metrics.num_of_tasks_with_include_role:
            return False
        
        if self.metrics.num_of_tasks_with_include_vars is None:
            self.metrics.num_of_tasks_with_include_vars = len(self.get_tasks_with_include_vars())
        if self.metrics.num_of_tasks_with_include_vars:
            return False

        if self.metrics.num_of_used_vars_defined_outside is None:
            self.metrics.num_of_used_vars_defined_outside = len(self.get_used_vars_defined_outside())
        if self.metrics.num_of_used_vars_defined_outside:
            return False
        
        return True
