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

import argparse
import json
import jsonpickle
import os
import copy


def prepare_source_dir(root_dir, src_json):
    path_list = []
    if not os.path.exists(root_dir):
        os.makedirs(root_dir)

    ignore_list = [
        "m4rkw/minotaur-install",
        "rodo/ansible-tsung",

        #GH2-PT
        "AutomateCompliance/AnsibleCompliancePlaybooks",
        "DevalexLLC/ansible-hardening-playbook",
        "ugns/ansible-ssg",
    ]
    
    for content in load_json_data(src_json):
        repo_name = content.get("repo_name")
        if not repo_name and "namespace_name" in content:
            repo_name = content.get("namespace_name")
        if repo_name in ignore_list:
            continue
        path = content.get("path")
        if path == "":
            path = "example.yml"
        elif path.endswith(".py"):
            # to support a module example task file which is saved as `<module>.py` 
            # while its content is a task YAML, we replace `.py` with `.yml`
            # so that sage can correctly scan it as task YAML file.
            path = path[:-3] + ".yml"
        text = content.get("text")
        if not text:
            text = content.get("content")
        source = content.get("source")
        license = content.get("license")
        _type = content.get("type")
        target_dir = os.path.join(root_dir, repo_name)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        target_file = os.path.join(target_dir, path.lstrip("/"))
        print(f"exporting yaml file {target_file}")
        target_file_dir = extract_directory(target_file)
        try:
            if not os.path.exists(target_file_dir):
                os.makedirs(target_file_dir)
            with open(target_file, "w") as file:
                file.write(text)
            path_list.append({
                "repo_type": _type,
                "repo_name": repo_name,
                "source": source,
                "license": license,
                "path": path,
            })
        except Exception as e:
            print(e)
    return path_list

def extract_directory(file_path):
    directory = os.path.dirname(file_path)
    return directory



def get_repo_name_from_source_data(single_soruce_data: dict):
    d = single_soruce_data
    repo_name = ""
    if "namespace_name" in d:
        repo_name = d["namespace_name"]
    elif "repo_name" in d:
        repo_name = d["repo_name"]
    return repo_name


# yields source data for each project
def load_source_data_per_project(filepath):
    with open(filepath, "r") as file:
        data = []
        for line in file:
            d = json.loads(line)
            if not d or not isinstance(d, dict):
                continue
            repo_name = get_repo_name_from_source_data(d)
            if len(data) == 0:
                current_repo_name = repo_name
            else:
                current_repo_name = get_repo_name_from_source_data(data[0])
            
            if repo_name == current_repo_name:
                data.append(d)
            else:
                # copy the current `data`` to yield it
                project_data = copy.deepcopy(data)
                # reset data and append the new project data to it here
                data = []
                data.append(d)
                yield project_data
        # yield the last project in the source file
        if data:
            yield data


def load_json_data(filepath):
    with open(filepath, "r") as file:
        for line in file:
            record = json.loads(line)
            if not record:
                continue
            yield record


def write_result(filepath, results):
    with open(filepath, "w") as file:
        if type(results) == list:
            for result in results:
                json_str = jsonpickle.encode(result, make_refs=False, unpicklable=False)
                file.write(f"{json_str}\n")
        else:
            json_str = jsonpickle.encode(results, make_refs=False, unpicklable=False)
            file.write(f"{json_str}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-t", "--source-type", help='source type (e.g."GitHub-RHIBM")')
    parser.add_argument("-s", "--source-json", help='source json file path (e.g. "/tmp/RH_IBM_FT_data_GH_api.json")')
    parser.add_argument("-o", "--out-dir", help="output directory")
    parser.add_argument("-p", "--project-list", help="project list")
    args = parser.parse_args()

    work_dir = args.out_dir
    src_type = args.source_type
    src_json = args.source_json
    project_list = args.project_list
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