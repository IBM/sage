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
from sage_scan.models import SageObject, SageProject, Playbook, TaskFile, Play, Task, Role
from sage_scan.process.variable_resolver import VariableResolver
from sage_scan.process.knowledge_base import KnowledgeBase, MODULE_OBJECT_ANNOTATION_KEY
from sage_scan.process.annotations import (
    set_module_spec_annotations,
    set_module_arg_key_annotations,
    set_module_arg_value_annotations,
    set_variable_annotations,
    omit_object_annotations,
)
from ansible_risk_insight.models import Annotation


# find all tasks defined in the specified playbook from SageProject
def get_tasks_in_playbook(playbook: Playbook, project: SageProject=None):
    play_keys = playbook.plays
    tasks = []
    for p_key in play_keys:
        play = project.get_object(key=p_key)
        if not play:
            continue
        p_tasks = get_tasks_in_play(play, project)
        tasks.extend(p_tasks)
    return tasks


# find all tasks defined in the specified play from SageProject
def get_tasks_in_play(play: Play, project: SageProject=None):
    task_keys = play.pre_tasks + play.tasks + play.post_tasks
    tasks = []
    for t_key in task_keys:
        task = project.get_object(key=t_key)
        if not task:
            continue
        tasks.append(task)
    return tasks


# find all tasks defined in the specified taskfile from SageProject
def get_tasks_in_taskfile(taskfile: TaskFile, project: SageProject=None):
    task_keys = taskfile.tasks
    tasks = []
    for t_key in task_keys:
        task = project.get_object(key=t_key)
        if not task:
            continue
        tasks.append(task)
    return tasks


# find all tasks defined in the specified playbook or taskfile from SageProject
def get_tasks_in_file(target: Playbook|TaskFile=None, project: SageProject=None):
    tasks = []
    if isinstance(target, Playbook):
        tasks = get_tasks_in_playbook(target, project)
    elif isinstance(target, TaskFile):
        tasks = get_tasks_in_taskfile(target, project)
    return tasks


# find all tasks defined in the specified playbook or taskfile from SageProject
# if `root` is an object key, get the object from SageProject first
def get_tasks(root: str | SageObject, project: SageProject=None):
    root_obj = root
    if isinstance(root, str):
        root_obj = project.get_object(key=root)
    return get_tasks_in_file(target=root_obj, project=project)


# find all plays defined in the specified playbook from SageProject
def get_plays(playbook: Playbook, project: SageProject):
    play_keys = playbook.plays
    plays = []
    for p_key in play_keys:
        play = project.get_object(key=p_key)
        if not play:
            continue
        if not isinstance(play, Play):
            continue
        plays.append(play)
    return plays


# find all taskfiles in the speciifed role from SageProject
def get_taskfiles_in_role(role: Role, project: SageProject):
    taskfile_keys = role.taskfiles
    taskfiles = []
    for tf_key in taskfile_keys:
        taskfile = project.get_object(key=tf_key)
        if not taskfile:
            continue
        if not isinstance(taskfile, TaskFile):
            continue
        taskfiles.append(taskfile)
    return taskfiles


# find main.yml or main.yaml in the specified role from SageProject
def get_main_taskfile_for_role(role: Role, project: SageProject):
    taskfiles = get_taskfiles_in_role(role, project)
    for tf in taskfiles:
        filename = os.path.basename(tf.filepath)
        if filename in ["main.yml", "main.yaml"]:
            return tf
    return None


# find a parent role for the specified taskfile if it exists
def find_parent_role(taskfile: TaskFile, project: SageProject):
    for role in project.roles:
        taskfile_keys = role.taskfiles
        if taskfile.key in taskfile_keys:
            return role
    return None


# get call tree which starts from the specified entrypoint
# call tree is a list of (obj, child_obj)
def get_call_tree_by_entrypoint(entrypoint: Playbook|Role|TaskFile, project: SageProject, follow_include: bool=True):
    return project.get_call_tree_by_entrypoint(entrypoint, follow_include)


# get all call sequences found in the SageProject
# call sequence is a sequence of objects executed by an entrypoint
# e.g.) Playbook --> Play 1 -> Task 1a -> Task 1b -> Play 2 -> Task 2a 
def get_all_call_sequences(project: SageProject, follow_include: bool=True):
    return project.get_all_call_sequences(follow_include)


# get a call sequence which contains the specified task
def get_call_sequence_for_task(task: Task, project: SageProject, follow_include: bool=True):
    return project.get_call_sequence_for_task(task, follow_include)


# get call sequence which starts from the specified entrypoint
def get_call_sequence_by_entrypoint(entrypoint: Playbook|Role|TaskFile, project: SageProject, follow_include: bool=True):
    return project.get_call_sequence_by_entrypoint(entrypoint, follow_include)


# get task sequence which starts from the specified entrypoint
def get_task_sequence_by_entrypoint(entrypoint: Playbook|Role|TaskFile, project: SageProject, follow_include: bool=True):
    call_seq = get_call_sequence_by_entrypoint(entrypoint, project, follow_include)
    if not call_seq:
        return None
    return [obj for obj in call_seq if isinstance(obj, Task)]


# get a task sequence which starts from the specified playbook
def get_task_sequence_for_playbook(playbook: Playbook, project: SageProject, follow_include: bool=True):
    return get_task_sequence_by_entrypoint(playbook, project, follow_include)


# get a task sequences which starts from the specified role
# this returns a list of task sequences; each sequence starts from a single taskfile in the role
def get_task_sequences_for_role(role: Role, project: SageProject, follow_include: bool=True):
    taskfiles = get_taskfiles_in_role(role, project)
    task_seq_list = []
    for taskfile in taskfiles:
        task_seq = get_task_sequence_by_entrypoint(taskfile, project, follow_include)
        if not task_seq:
            continue
        task_seq_list.append(task_seq)
    return task_seq_list


# get a task sequences which starts from the specified taskfile
def get_task_sequence_for_taskfile(taskfile: TaskFile, project: SageProject, follow_include: bool=True):
    return get_task_sequence_by_entrypoint(taskfile, project, follow_include)


# embed `defined_vars` annotation to all objects in a call sequence
def set_defined_vars(call_seq: list):
    resolver = VariableResolver()
    obj_and_vars_list = resolver.set_defined_vars(call_seq=call_seq)
    call_seq = resolver.call_seq
    return obj_and_vars_list


# get defined vars for the specified object
# if object is a TaskFile, this returnes defined vars of a Role which contains the TaskFile if found
def get_defined_vars(object: SageObject, project: SageProject):
    target = object
    obj_list = [object]
    if isinstance(object, TaskFile):
        role = find_parent_role(object, project)
        if role:
            target = role
            obj_list = [role, object]

    resolver = VariableResolver()
    return resolver.get_defined_vars(object=target, call_seq=obj_list)

# get used vars for the specified object
# this returns a dict of var_name and var_value pairs, where values are resolved as much as possible
# if variable resolution fails, the value will be a placeholder string like `{{ var_name }}`
def get_used_vars(object: SageObject, project: SageProject, follow_include: bool=True):
    obj_list = []
    if isinstance(object, TaskFile):
        role = find_parent_role(object, project)
        if role:
            obj_list = [role]
    call_seq = get_call_sequence_by_entrypoint(
        entrypoint=object,
        project=project,
        follow_include=follow_include,
    )
    obj_list.extend(call_seq)
    if not obj_list:
        return {}
    
    target = obj_list[-1]
    resolver = VariableResolver()
    return resolver.get_used_vars(object=target, call_seq=obj_list)


def set_vars_annotation(object: SageObject, project: SageProject):
    obj_list = []
    if isinstance(object, TaskFile):
        role = find_parent_role(object, project)
        if role:
            obj_list = [role]
    call_seq = get_call_sequence_by_entrypoint(entrypoint=object, project=project)
    obj_list.extend(call_seq)
    if not obj_list:
        return []
    
    resolver = VariableResolver()
    obj_vars_list = resolver.set_used_vars(call_seq=obj_list)
    obj_list = [obj for (obj, _, _) in obj_vars_list]
    return obj_list


# returns all entrypoint objects
# playbooks, roles and independent taskfiles (=not in a role) can be an entrypoint
def list_entrypoints(project: SageProject):
    entrypoints = []
    entrypoints.extend(project.playbooks)
    entrypoints.extend(project.roles)
    # only independent taskfiles; skip taskfiles in role
    entrypoints.extend([tf for tf in project.taskfiles if not tf.role])
    return entrypoints


# set `module_info` in task
# this requires ARI KB data for non-builtin modules
def set_module_info_to_task(task: Task):
    kb = KnowledgeBase()
    return kb.set_module_info(task)


def set_primary_annotations_to_project(project: SageProject):
    resolver = VariableResolver()
    # set variable data
    project = resolver.resolve_all_vars_in_project(project=project)
    kb = KnowledgeBase()
    tasks = project.tasks
    for task in tasks:
        # set module_info/include_info
        kb.resolve_task(task, set_module_object_annotation=True)

        # set P001 annotations
        set_module_spec_annotations(task)

        # set P002 annotations
        set_module_arg_key_annotations(task, knowledge_base=kb)

        # set P003 annotations
        set_module_arg_value_annotations(task)

        # set P004 annotations
        set_variable_annotations(task)

        # remove temporary annotations (to avoid saving large data)
        omit_object_annotations(task)
    return project
