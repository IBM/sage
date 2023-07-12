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

from ansible_risk_insight.scanner import ARIScanner, config, Config
from ansible_risk_insight.models import NodeResult, RuleResult
from ansible_risk_insight.finder import (
    find_all_ymls,
    label_yml_file,
    get_role_info_from_path,
    get_project_info_for_file,
)
from ansible_risk_insight.utils import escape_local_path
import os
import argparse
import time
import traceback
import joblib
import threading
import jsonpickle
import json


def get_yml_label(file_path, root_path):
    relative_path = file_path.replace(root_path, "")
    if relative_path[-1] == "/":
        relative_path = relative_path[:-1]
    
    label, error = label_yml_file(file_path)
    role_name, role_path = get_role_info_from_path(file_path)
    role_info = None
    if role_name and role_path:
        role_info = {"name": role_name, "path": role_path}

    project_name, project_path = get_project_info_for_file(file_path, root_path)
    project_info = None
    if project_name and project_path:
        project_info = {"name": project_name, "path": project_path}
    
    # print(f"[{label}] {relative_path} {role_info}")
    if error:
        print(f"failed to get yml label:\n {error}")
        label = "error"
    return label, role_info, project_info


def create_scan_list(yml_inventory):
    role_file_list = {}
    project_file_list = {}
    independent_file_list = []
    for yml_data in yml_inventory:
        filepath = yml_data["filepath"]
        path_from_root = yml_data["path_from_root"]
        label = yml_data["label"]
        role_info = yml_data["role_info"]
        in_role = yml_data["in_role"]
        project_info = yml_data["project_info"]
        in_project = yml_data["in_project"]
        if project_info:
            p_name = project_info.get("name", "")
            p_path = project_info.get("path", "")
            if p_name not in project_file_list:
                project_file_list[p_name] = {"path": p_path, "files": []}
            project_file_list[p_name]["files"].append({
                "filepath": filepath,
                "path_from_root": path_from_root,
                "label": label,
                "project_info": project_info,
                "role_info": role_info,
                "in_project": in_project,
                "in_role": in_role,
            })
        elif role_info:
            r_name = role_info.get("name", "")
            r_path = role_info.get("path", "")
            if role_info.get("is_external_dependency", False):
                continue
            if r_name not in role_file_list:
                role_file_list[r_name] = {"path": r_path, "files": []}
            role_file_list[r_name]["files"].append({
                "filepath": filepath,
                "path_from_root": path_from_root,
                "label": label,
                "project_info": project_info,
                "role_info": role_info,
                "in_project": in_project,
                "in_role": in_role,
            })
        else:
            independent_file_list.append({
                "filepath": filepath,
                "path_from_root": path_from_root,
                "label": label,
                "project_info": project_info,
                "role_info": role_info,
                "in_project": in_project,
                "in_role": in_role,
            })
    return project_file_list, role_file_list, independent_file_list



def get_yml_list(root_dir: str):
    found_ymls = find_all_ymls(root_dir)
    all_files = []
    for yml_path in found_ymls:
        label, role_info, project_info = get_yml_label(yml_path, root_dir)
        if not role_info:
            role_info = {}
        if not project_info:
            project_info = {}
        if role_info:
            if role_info["path"] and not role_info["path"].startswith(root_dir):
                role_info["path"] = os.path.join(root_dir, role_info["path"])
            role_info["is_external_dependency"] = True if "." in role_info["name"] else False
        in_role = True if role_info else False
        in_project = True if project_info else False
        all_files.append({
            "filepath": yml_path,
            "path_from_root": yml_path.replace(root_dir, "").lstrip("/"),
            "label": label,
            "role_info": role_info,
            "project_info": project_info,
            "in_role": in_role,
            "in_project": in_project,
        })
    return all_files