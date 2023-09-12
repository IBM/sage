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

from pathlib import Path
import os
import json
import argparse
from treelib import Node, Tree
from ansible_risk_insight.findings import Findings
from ansible_risk_insight.models import Collection, Module, Playbook, Play, RoleInPlay, Repository, Role, TaskFile, Task
from ansible_risk_insight.keyutil import get_obj_type



types_map = {
    "collection": "collections",
    "module": "modules",
    "playbook": "playbooks",
    "play": "plays",
    "project": "projects",
    "role": "roles",
    "taskfile": "taskfiles",
    "task": "tasks",
}

# possible children types in spec objects
# NOTE: `playbook -> play -> task` is possible,
#       but `task -> (include) -> role` is not, because this checks only spec trees
tree_node_types = {
    "collections": ["playbooks", "roles", "modules", "plays", "taskfiles", "tasks"],
    "modules": [],
    "playbooks": ["plays", "tasks"],
    "plays": ["tasks"],
    "projects": ["collections", "playbooks", "roles", "modules", "plays", "taskfiles", "tasks"],
    "roles": ["playbooks", "plays", "taskfiles", "tasks", "modules"],
    "taskfiles": ["tasks"],
    "tasks": [],
}

def normalize_type_str(_type: str):
    
    lower_type = _type.lower()
    if lower_type in types_map:
        return types_map[lower_type]
    if lower_type in list(types_map.values()):
        return lower_type
    raise ValueError(f"Unknown ARI object type: {_type}")


def get_children_keys(obj):
    raw_children = obj.resolver_targets
    if not raw_children:
        return []
    children = []
    for c in raw_children:
        if isinstance(c, RoleInPlay):
            continue
        children.append(c)
    return children


def get_object_by_key(specs, key):
    type_str = get_obj_type(key)
    type_str = normalize_type_str(type_str)
    if type_str not in specs:
        return None
    objs = specs.get(type_str, [])
    found = None
    for obj in objs:
        if obj.key == key:
            found = obj
            break
    return found


def _recursive_get_children(specs, obj):
    obj_key = obj.key
    children_keys = get_children_keys(obj)
    if not children_keys:
        return []
    
    children = []
    for c_key in children_keys:
        c_obj = get_object_by_key(specs, c_key)
        c_name = ""
        if c_obj:
            c_name = create_node_name_from_obj(c_obj)
        else:
            c_name = "(Unknown)"
        node = (c_name, c_key, obj_key)
        children.append(node)

        if c_obj:
            offspring = _recursive_get_children(specs, c_obj)
            children.extend(offspring) 

    return children


def create_node_name_from_obj(obj):
    _type = ""
    _name = ""
    if isinstance(obj, Collection):
        _type = "Collection"
        _name = obj.fqcn
    elif isinstance(obj, Module):
        _type = "Module"
        _name = obj.fqcn
    elif isinstance(obj, Playbook):
        _type = "Playbook"
        _name = obj.defined_in
    elif isinstance(obj, Play):
        _type = "Play"
        _name = obj.name
    elif isinstance(obj, Repository):
        _type = "Project"
        _name = obj.name
    elif isinstance(obj, Role):
        _type = "Role"
        _name = obj.fqcn
        if obj.metadata and isinstance(obj.metadata, dict):
            role_desc = obj.metadata.get("galaxy_info", {}).get("description", "")
            if role_desc:
                _name = _name + f" ({role_desc})"
    elif isinstance(obj, TaskFile):
        _type = "TaskFile"
        _name = obj.defined_in
    elif isinstance(obj, Task):
        _type = "Task"
        _name = obj.name
    if not _name:
        _name = "(No name)"
    name = f"{_type} {_name}"
    return name


def create_object_tree_by_specs(specs, _type):
    if not specs:
        return None
    
    if not isinstance(specs, dict):
        return None
    
    # create root nodes
    trees = []
    for obj in specs.get(_type, []):
        key = obj.key
        tree = Tree()
        root_name = create_node_name_from_obj(obj)
        tree.create_node(root_name, key)
        tree_nodes = _recursive_get_children(specs, obj)

        for node in tree_nodes:
            node_name, obj_key, parent_key = node
            tree.create_node(node_name, obj_key, parent=parent_key)

        trees.append(tree)
    
    for tree in trees:
        tree.show(sorting=False)
        print("-" * 90)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--file", help='findings json file')
    parser.add_argument("-t", "--type", help='type of objects to view')
    # parser.add_argument("-d", "--dir", help='tmp dir to recreate source dir')
    # parser.add_argument("-o", "--out-file", help="output directory for the rule evaluation result")
    args = parser.parse_args()

    fpath = args.file
    _type = normalize_type_str(args.type)
    findings_list = []
    with open(fpath, "r") as file:
        for line in file:
            f = Findings.load(json_str=line)
            findings_list.append(f)
    
    for findings in findings_list:
        specs = findings.root_definitions.get("definitions", {})
        if _type not in specs:
            continue
        
        create_object_tree_by_specs(specs, _type)
        



