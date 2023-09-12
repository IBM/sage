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
import sys
import jsonpickle
import argparse
from sage_scan.pipeline import SerializableRunContext
from ansible_risk_insight.models import (
    Module,
    Task,
    TaskCall,
    AnsibleRunContext,
)
from ansible_risk_insight.risk_assessment_model import RAMClient
import tabulate




ARI_KB_DATA_DIR = os.getenv("ARI_KB_DATA_DIR", None)

if ARI_KB_DATA_DIR is None:
    raise ValueError(f"Please specify an existing ARI KB dir by an env param:\n$ export ARI_KB_DATA_DIR=<PATH/TO/ARI_KB_DATA_DIR>")

if not os.path.exists(ARI_KB_DATA_DIR):
    raise ValueError(f"the ARI_KB_DATA_DIR does not exist: {ARI_KB_DATA_DIR}")

ram_client = RAMClient(root_dir=ARI_KB_DATA_DIR)


def get_module_fqcn(module_name):
    found_candidates = ram_client.search_module(module_name)
    if not found_candidates:
        return None

    # pick the best matched module instance here
    module = found_candidates[0]["object"]
    if not isinstance(module, Module):
        return None
    
    return module.fqcn


def main():
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--file", help='result json file')
    args = parser.parse_args()

    fpath = args.file
    result = {}
    with open(fpath, "r") as file:
        body = file.read()
        result = jsonpickle.decode(body, safe=True)
    
    objects = result.get("objects", [])
    table_data = []
    not_found = []
    for obj in objects:
        if not isinstance(obj, SerializableRunContext):
            continue
        rc = obj.to_ansible_run_context()
        if not isinstance(rc, AnsibleRunContext):
            continue

        for node in rc:
            if not isinstance(node, TaskCall):
                continue
            if not isinstance(node.spec, Task):
                continue
            task = node.spec
            module_name = task.module
            module_fqcn = get_module_fqcn(module_name)
            if module_fqcn is None:
                not_found.append(module_name)
                continue
            table_data.append([module_name, module_fqcn])
        
    table_str = tabulate.tabulate(table_data, headers=["SHORT_NAME", "FQCN"])
    print(table_str)


if __name__ == '__main__':
    main()
