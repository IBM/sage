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

from mdutils.mdutils import MdUtils
from pathlib import Path
import os
import json
import argparse
import jsonpickle
from dataclasses import dataclass, field
import glob


@dataclass
class Summary():
    src_type: str = ''
    repo_name: str = ''
    findings: object = field(default_factory=dict)
    yml_inventory: object = field(default_factory=dict)
    sage_results: object = field(default_factory=dict)
    original: object = field(default_factory=dict)
    enriched: object = field(default_factory=dict)
    only_original: object = field(default_factory=dict)
    coverage: int = -1
    src_files: object = field(default_factory=dict)

def generate_summary(export_path, sage_dir, org_ft_dir, ftdata_src_type="", repo_name=""):
    scan_summary = Summary()

    scan_summary.src_type=ftdata_src_type
    scan_summary.repo_name=repo_name

    yml_inventory_file = os.path.join(sage_dir, "yml_inventory.json")
    findings_json = os.path.join(sage_dir, "findings.json")
    ftdata_file = os.path.join(org_ft_dir, "org-ftdata.json")
    sage_ftdata_file = os.path.join(sage_dir, "_tmp-ftdata.json")
    f_org_only = os.path.join(sage_dir, ftdata_src_type, "_only_org_ftdata.json")
    f_matched = os.path.join(sage_dir, ftdata_src_type, "_modified_ftdata.json")


    scan_summary.src_files = {
        "yml_inventory_file": yml_inventory_file,
        "findings_json": findings_json,
        "ftdata_file": ftdata_file,
        "sage_ftdata_file": sage_ftdata_file,
        "f_org_only": f_org_only,
        "f_matched": f_matched,
    }

    target_files, out_of_scopes = get_yml_inventory(yml_inventory_file)  # list: {path, label}
    
    tasks_in_findings = count_tasks_in_findings(findings_json)   # {path: task list}
    playbook_role = get_objects(findings_json)  # {playbook: [name], role: [name]}
    findings_task_count = sum(len(v) for v in tasks_in_findings.values())
    scan_summary.findings = {
        "task_count": findings_task_count,
        "playbooks": playbook_role["playbook"],
        "roles": playbook_role["role"],
        "file_tasks": tasks_in_findings,
    }

    playbook_count, taskfile_count, no_task_count, error_count, others_count, external_dep = get_file_type_count(out_of_scopes, target_files, tasks_in_findings)
    scan_summary.yml_inventory = {
        "playbook_count": playbook_count,
        "taskfile_count": taskfile_count,
        "no_task_count": no_task_count,
        "error_count": error_count,
        "others_count": others_count,
        "external_dep_count": external_dep,
        "target_files": target_files,
        "out_of_scopes": out_of_scopes,
    }

    task_count_org, o_playbooks, o_taskfiles = count_tasks_in_org_ftdata(ftdata_file)  #{path: task count}, p list, t list
    org_task_count = sum(task_count_org.values())
    scan_summary.original = {
        "task_count": org_task_count,
        "file_task_count": task_count_org,
        "playbooks": o_playbooks,
        "taskfiles": o_taskfiles,
        "playbook_count": len(o_playbooks),
        "taskfile_count": len(o_taskfiles),
    }

    task_count_sage, tasks_in_sage, s_playbooks, s_taskfiles = count_tasks_in_sage_ftdata(sage_ftdata_file) #{path: task count}, {path: task key list}, p list, t list
    sage_task_count = sum(task_count_sage.values())
    scan_summary.sage_results = {
        "task_count": sage_task_count,
        "file_task_count": task_count_sage,
        "file_task_keys": tasks_in_sage,
        "playbooks": s_playbooks,
        "taskfiles": s_taskfiles,
        "playbook_count": len(s_playbooks),
        "taskfile_count": len(s_taskfiles),
    }

    task_count_enriched, task_count_missing, missing_tasks = count_enriched_ftdata(f_org_only, f_matched) # {path: count}, list: {file, prompt}
    unchanged_sum = sum(task_count_missing.values())
    enriched_sum = sum(task_count_enriched.values())
    scan_summary.enriched = {
        "task_count": enriched_sum,
        "file_task_count": task_count_enriched
    }
    scan_summary.only_original = {
        "task_count": unchanged_sum,
        "file_task_count": task_count_missing,
        "only_org_detail": missing_tasks,
    }        

    if org_task_count != 0:
        p = enriched_sum/org_task_count*100
        coverage = round(p, 2)
        scan_summary.coverage = coverage

    export_result(export_path, scan_summary)
    return scan_summary

def get_yml_inventory(yml_inventory_file):
    target_files = []
    out_of_scope = []
    if os.path.exists(yml_inventory_file):
        with open(yml_inventory_file, 'r') as file:
            for line in file:
                item = json.loads(line)
                label = item["label"]
                role_info = item["role_info"]
                y = {
                    "path": item["path_from_root"].lstrip("/"),
                    "type": label,
                }
                if role_info:
                    role_name = role_info["name"]
                    y["role"] = role_name
                    is_external_dependency = role_info["is_external_dependency"]
                    if is_external_dependency:
                        y["external"] = True
                        out_of_scope.append(y)
                        continue
                if label == "others":
                    out_of_scope.append(y)
                    continue

                if label == "error":
                    out_of_scope.append(y)
                    continue
                target_files.append(y)
    # sort
    target_files = sorted(target_files, key=lambda x: x['type'])
    out_of_scope = sorted(out_of_scope, key=lambda x: x['type'])
    return target_files, out_of_scope

def count_tasks_in_findings(findings_json):
    file_tasks = {}
    if os.path.exists(findings_json):
        with open(findings_json, "r") as file:
            for line in file:
                findings = json.loads(line)
                mappings = findings.get("root_definitions", {}).get("mappings", {})
                target_name = mappings.get("target_name")

                definitions = findings.get("root_definitions", {}).get("definitions", {})
                playbooks = definitions.get("playbooks", [])
                for playbook in playbooks:
                    tasks = []
                    path = playbook["defined_in"].lstrip("/")
                    if not target_name.endswith(path):
                        path = f"{target_name}/{path}"
                    elif target_name != path:
                        path = target_name
                    plays = playbook.get("plays", [])
                    if len(plays) == 0:
                        if path not in file_tasks:
                            file_tasks[path] = []
                    else:
                        d_plays = definitions.get("plays", [])
                        for p in plays:
                            for dp in d_plays:
                                p_key = dp.get("key", "")
                                if p == p_key:
                                    p_tasks = dp.get("tasks", [])
                                    tasks.extend(p_tasks)
                                    post_tasks = dp.get("post_tasks", [])
                                    tasks.extend(post_tasks)
                                    pre_tasks = dp.get("pre_tasks", [])
                                    tasks.extend(pre_tasks)
                    uniq_tasks = list(set(tasks))
                    if path not in file_tasks:
                        file_tasks[path] = uniq_tasks
                    else:
                        _tasks = file_tasks[path]
                        _tasks.extend(uniq_tasks)
                        file_tasks[path] = list(set(_tasks))
                        
                taskfiles = definitions.get("taskfiles", [])
                for taskfile in taskfiles:
                    path = taskfile["defined_in"].lstrip("/")
                    if not target_name.endswith(path):
                        path = f"{target_name}/{path}"
                    elif target_name != path:
                        path = target_name
                    t_tasks = taskfile["tasks"]
                    if path not in file_tasks:
                        file_tasks[path] = t_tasks
                    else:
                        _tasks = file_tasks[path]
                        _tasks.extend(t_tasks)
                        file_tasks[path] = list(set(_tasks))
    # file_task_count = {}
    # for p, t in file_tasks.items():
    #     file_task_count[p] = len(t)
    return file_tasks

def get_objects(findings_json):
    objects = {"playbook": [], "role": []}
    if os.path.exists(findings_json):
        with open(findings_json, "r") as file:
            for line in file:
                findings = json.loads(line)
                definitions = findings.get("root_definitions", {}).get("definitions", {})
                playbooks = definitions.get("playbooks", [])
                # plays = definitions.get("plays", [])
                roles = definitions.get("roles", [])
                # taskfiles = definitions.get("taskfiles", [])
                for p in playbooks:
                    name = p.get("name", "")
                    if "playbook" in objects:
                        objects["playbook"].append(name)
                    else:
                        objects["playbook"] = [name]
                for r in roles:
                    name = r.get("name", "")
                    if "role" in objects:
                        objects["role"].append(name)
                    else:
                        objects["role"] = [name]
            for t, items in objects.items():
                objects[t] = list(set(items))
    return objects

def count_tasks_in_org_ftdata(ftdata_file):
    data = []
    if os.path.exists(ftdata_file):
        with open(ftdata_file, 'r') as file:
            for line in file:
                jo = json.loads(line)
                data.append(jo)
    task_count = {}
    playbooks = []
    taskfiles = []
    for d in data:
        path = d["path"].lstrip("/")
        task_count[path] = task_count.get(path, 0) + 1
        type = d["type"]
        if type == "playbook":
            if path not in playbooks:
                playbooks.append(path)
        if type == "task":
            if path not in taskfiles:
                taskfiles.append(path)
    return task_count, playbooks, taskfiles


def count_enriched_ftdata(f_org_only, f_matched):
    data = []
    if os.path.exists(f_org_only):
        with open(f_org_only, 'r') as file:
            for line in file:
                jo = json.loads(line)
                data.append(jo)
    missing_task_count = {}
    missing_tasks = []
    for d in data:
        path = d["path"].lstrip("/")
        missing_task_count[path] = missing_task_count.get(path, 0) + 1
        missing_tasks.append({
            "file": d["path"],
            "prompt": d["prompt"]
        })
    data = []
    if os.path.exists(f_matched):
        with open(f_matched, 'r') as file:
            for line in file:
                jo = json.loads(line)
                data.append(jo)
    matched_task_count = {}
    for d in data:
        path = d["path"].lstrip("/")
        matched_task_count[path] = matched_task_count.get(path, 0) + 1
    return matched_task_count, missing_task_count, missing_tasks

def count_tasks_in_sage_ftdata(sage_ftdata_file):
    data = []
    if os.path.exists(sage_ftdata_file):
        with open(sage_ftdata_file, 'r') as file:
            for line in file:
                jo = json.loads(line)
                data.append(jo)
    task_count = {}
    file_tasks = {}
    playbooks = []
    taskfiles = []
    for d in data:
        path = d["path"].lstrip("/")
        task_count[path] = task_count.get(path, 0) + 1
        if path not in file_tasks:
            file_tasks[path] = [d["ari_task_key"]]
        else:
            file_tasks[path].append(d["ari_task_key"])
        type = d["type"]
        if type == "playbook":
            if path not in playbooks:
                playbooks.append(path)
        if type == "taskfile":
            if path not in taskfiles:
                taskfiles.append(path)
    return task_count, file_tasks, playbooks, taskfiles

def get_file_type_count(out_of_scopes, target_files, tasks_in_findings):
    others_count = 0
    external_dep = 0
    error_count = 0
    no_task_count = 0
    playbook_count = 0
    taskfile_count = 0
    for oos in out_of_scopes:
        is_external = oos.get("external", False)
        type = oos["type"]
        if is_external:
            external_dep += 1
            continue
        if type == "others":
            others_count += 1
            continue
        if type == "error":
            error_count += 1
            continue
    for tf in target_files:
        type = tf["type"]
        path = tf["path"]
        fc = _get_task_count(path, tasks_in_findings)
        if fc == 0:
            no_task_count += 1
            continue
        if type == "playbook":
            playbook_count += 1
        if type == "taskfile":
            taskfile_count += 1
    return playbook_count, taskfile_count, no_task_count, error_count, others_count, external_dep

def _get_task_count(path, file_tasks):
    for p, t in file_tasks.items():
        if p.endswith(path):
            return len(t)
    return -1

def _get_tasks_in_findings(path, file_tasks):
    for p, t in file_tasks.items():
        if p.endswith(path):
            return t
    return []

def generate_detail_report(export_path, ss: Summary):
    if ss.repo_name:
        title = f"Sage Repo Scan Report: [{ss.repo_name}](https://github.com/{ss.repo_name})"
    else:
        title = f"Sage Repo Scan Report"
    mdFile = MdUtils(file_name=export_path, title=title)

    if src_type:
        mdFile.new_line(f"src_type: {src_type}")
        
    mdFile.new_line(f"yml_inventory_file: {ss.src_files['yml_inventory_file']}")
    mdFile.new_line(f"findings_json: {ss.src_files['findings_json']}")
    mdFile.new_line(f"original ftdata_file: {ss.src_files['ftdata_file']}")
    mdFile.new_line(f"sage_ftdata_file: {ss.src_files['sage_ftdata_file']}")

    mdFile.new_header(level=1, title='Detail reports')
    mdFile.new_line("[Yaml file inventory](#yaml-file-inventory)")
    mdFile.new_line("[Playbooks and Roles](#playbooks-and-roles)")
    mdFile.new_line("[Tasks scanned per file](#tasks-scanned-per-file)")
    mdFile.new_line("[Unrecorded tasks (parsed but rule failed)](#unrecorded-tasks)")
    mdFile.new_line("[Unchanged tasks (failed to add a new context)](#unchanged-tasks)")

    task_count_org = ss.original["task_count"]
    file_task_count_org = ss.original["file_task_count"]

    file_task_count_sage = ss.sage_results["file_task_count"]
    task_count_sage = ss.sage_results["task_count"]
    tasks_in_sage = ss.sage_results["file_task_keys"]
    s_playbook_count = ss.sage_results["playbook_count"]
    s_taskfile_count = ss.sage_results["taskfile_count"]

    task_count_missing = ss.only_original["task_count"]
    file_task_count_missing = ss.only_original["file_task_count"]
    missing_tasks = ss.only_original["only_org_detail"]
    file_task_count_enriched = ss.enriched["file_task_count"]
    
    findings_playbook = ss.findings["playbooks"]
    findings_role = ss.findings["roles"]
    findings_task_count = ss.findings["task_count"]
    tasks_in_findings = ss.findings["file_tasks"]

    playbook_count = ss.yml_inventory["playbook_count"]
    taskfile_count = ss.yml_inventory["taskfile_count"]
    no_task_count = ss.yml_inventory["no_task_count"]
    error_count = ss.yml_inventory["error_count"]
    others_count = ss.yml_inventory["others_count"]
    external_dep = ss.yml_inventory["external_dep_count"]
    target_files = ss.yml_inventory["target_files"]
    out_of_scopes = ss.yml_inventory["out_of_scopes"]


    mdFile.new_header(level=1, title='Yaml file inventory')
    header = ["playbooks", "taskfiles", "no task", "external dep", "others", "parse error", "total_num"]
    cells = header
    cells.append(playbook_count)
    cells.append(taskfile_count)
    cells.append(no_task_count)
    cells.append(external_dep)
    cells.append(others_count)
    cells.append(error_count)
    cells.append(playbook_count+taskfile_count+no_task_count+external_dep+others_count+error_count)
    mdFile.new_table(columns=7, rows=2, text=cells, text_align='left')
    
    # playbooks and roles
    mdFile.new_header(level=1, title='Playbooks and Roles')
    header = ["type", "name"]
    cells = header
    item_count = len(findings_playbook) + len(findings_role)
    for p in findings_playbook:
        cells.extend(["playbook", p])
    for r in findings_role:
        cells.extend(["role", r])
    mdFile.new_table(columns=2, rows=item_count+1, text=cells, text_align='left')

    # tasks
    header = ["path", "type", "status", "task count", "task recorded", "org tasks", "unchanged", "role"]
    cells = header
    status_count = {"fail": 0, "pass": 0}
    for ty in target_files:
        path = ty["path"]
        cells.append(path)
        cells.append(ty["type"])
        fc = _get_task_count(path, tasks_in_findings)
        if file_task_count_enriched.get(path, 0) < file_task_count_org.get(path, 0):
            cells.append("x")
            status_count["fail"] = status_count.get("fail", 0) + 1
        elif file_task_count_sage.get(path, 0) < fc:
            cells.append("△")
            status_count["fail"] = status_count.get("fail", 0) + 1
        else:
            cells.append("✔")
            status_count["pass"]= status_count.get("pass", 0) + 1
        cells.append(fc)
        cells.append(file_task_count_sage.get(path, 0))
        cells.append(file_task_count_org.get(path, 0))
        cells.append(file_task_count_missing.get(path, 0))
        cells.append(ty.get("role", ""))
    for o in out_of_scopes:
        cells.append(o["path"])
        cells.append(o["type"])
        cells.append("-")
        cells.append("-")
        cells.append("-")
        cells.append(file_task_count_org.get(o["path"], "-"))
        cells.append(file_task_count_missing.get(o["path"], "-"))
        cells.append(o.get("role", ""))
    # add summary table
    header = ["status count", "playbook (recorded/count)", "taskfile (recorded/count)", "task count", "task recorded", "org tasks", "unchanged"]
    cells_summary = header

    cells_summary.append(f"{status_count['pass']}/{status_count['pass']+status_count['fail']}")
    cells_summary.append(f"{s_playbook_count}/{playbook_count}")
    cells_summary.append(f"{s_taskfile_count}/{taskfile_count}")
    cells_summary.append(findings_task_count)
    cells_summary.append(task_count_sage)
    cells_summary.append(task_count_org)
    cells_summary.append(task_count_missing)
    mdFile.new_header(level=1, title='Summary')
    mdFile.new_table(columns=7, rows=2, text=cells_summary, text_align='left')

    # add tasks table
    mdFile.new_header(level=1, title='Tasks scanned per file')
    mdFile.new_table(columns=8, rows=len(target_files)+len(out_of_scopes)+1, text=cells, text_align='left')

    # unrecorded task (findings - sage ftdata)
    header = ["file", "task key"]
    mdFile.new_header(level=1, title='Unrecorded tasks')
    mdFile.new_line("List of tasks parsed but rule failed")
    cells = header
    count = 1
    for ty in target_files:
        path = ty["path"]
        f_task_keys = _get_tasks_in_findings(path, tasks_in_findings)
        s_task_keys = tasks_in_sage.get(path, [])
        for ft in f_task_keys:
            if ft not in s_task_keys:
                cells.append(path)
                cells.append(ft)
                count += 1
    mdFile.new_table(columns=2, rows=count, text=cells, text_align='left')

    # unchanged task (wisdom - sage ftdata)
    mdFile.new_header(level=1, title='Unchanged tasks')
    mdFile.new_line("List of tasks without new context")
    header = ["file", "prompt"]
    cells = header
    for t in missing_tasks:
         cells.append(t["file"])
         cells.append(t["prompt"])
    mdFile.new_table(columns=2, rows=len(missing_tasks)+1, text=cells, text_align='left')
    mdFile.create_md_file()
    return 

def generate_main_report(org_ftdata_dir, sage_dir, outdir, src_type, org_ftdata_type=""):
    if not org_ftdata_type:
        org_ftdata_type = src_type
    
    report_dir = os.path.join(outdir, org_ftdata_type)
    os.makedirs(report_dir, exist_ok=True)
    export_path = os.path.join(report_dir, "README.md")
    data_export_path = os.path.join(report_dir, "summary.json")
    mdFile = MdUtils(file_name=export_path, title='Sage Repo Scan Report')

    results = []
    target_sage_dir = os.path.join(sage_dir, src_type)
    for f_inventory in Path(target_sage_dir).rglob("yml_inventory.json"):
        if Path.is_file(f_inventory):
            f_inventory_str = str(f_inventory)
            parts = f_inventory_str.split("/")
            # project
            if parts[-3] != src_type:
                repo_name = f"{parts[-3]}/{parts[-2]}"
            else:
                repo_name = parts[-2]

            t_org_ftdata_dir = os.path.join(org_ftdata_dir, org_ftdata_type, repo_name)
            t_sage_dir = os.path.join(sage_dir, src_type, repo_name)

            detail_report_path = os.path.join(outdir, org_ftdata_type, repo_name, "README.md")
            detail_data_path = os.path.join(outdir, org_ftdata_type, repo_name, "summary.json")
            target_file_dir = os.path.dirname(detail_report_path)
            if not os.path.exists(target_file_dir):
                os.makedirs(target_file_dir)
            summary_data = generate_summary(detail_data_path, t_sage_dir, t_org_ftdata_dir, org_ftdata_type, repo_name)
            generate_detail_report(detail_report_path, summary_data)
            summary = {}
            summary["detail_report_path"] = detail_report_path
            summary["data"] = summary_data
            results.append(summary)

    sorted_results = sorted(results, key=lambda x: x["data"].coverage, reverse=True)

    mdFile.new_line(f"src_type: {sorted_results[0]['data'].src_type}")
    mdFile.new_line(f"src_file: RH_IBM_FT_data_GH_api.json")
    mdFile.new_line(f"original ftdata: {org_ftdata_dir}")

    json_data = []

    header = ["repo_name", "status", "playbooks (recorded/total)", "taskfiles", "roles", "tasks", "task recorded",  "enriched ftdata", "coverage (%)"]
    cells = header
    for res in sorted_results:
        ss = res["data"]
        src_type = ss.src_type
        repo_name = ss.repo_name
        detail_report_path = res["detail_report_path"]
        relative_path = os.path.relpath(detail_report_path, report_dir)
        cells.append(f"[{repo_name}]({relative_path})")
        p = ss.coverage
        status = "x"
        if p == 100 or p == -1:
            status = "✔"
        cells.append(status)

        playbook_count = ss.yml_inventory["playbook_count"]
        taskfile_count = ss.yml_inventory["taskfile_count"]
        playbook_count_sage = ss.sage_results["playbook_count"]
        taskfile_count_sage = ss.sage_results["taskfile_count"]

        task_count_org = ss.original["task_count"]
        task_count_sage = ss.sage_results["task_count"]
        task_count_findings = ss.findings["task_count"]
        task_count_en = ss.enriched["task_count"]

        cells.append(f'{playbook_count_sage}/{playbook_count}')
        cells.append(f'{taskfile_count_sage}/{taskfile_count}')
        cells.append(len(ss.findings["roles"]))
        cells.append(task_count_findings)
        cells.append(task_count_sage)
        cells.append(f'{task_count_en}/{task_count_org}')
        if p == -1:
            p = "N/A"
        cells.append(p)

        sj = {
            "src_type": src_type,
            "repo_name": repo_name,
            "status": status,
            "playbook_count_total": playbook_count,
            "playbook_count_sage": playbook_count_sage,
            "taskfile_count_total": taskfile_count,
            "taskfile_count_sage": taskfile_count_sage,
            "role_count": len(ss.findings["roles"]),
            "task_count_total": task_count_findings,
            "task_count_org": task_count_org,
            "task_count_sage": task_count_sage,
            "task_count_enriched": task_count_en,
            "coverage": ss.coverage,
            "detail_report_path": detail_report_path
        }
        json_data.append(sj)

    mdFile.new_table(columns=9, rows=len(sorted_results) + 1, text=cells, text_align='left')
    mdFile.create_md_file()
    json_result = {"md_path": export_path, "data": json_data}
    export_result(data_export_path, json_result)
    return

def export_result(filepath, results):
    with open(filepath, "w") as file:
        if type(results) == list:
            for result in results:
                json_str = jsonpickle.encode(result, make_refs=False, unpicklable=False)
                file.write(f"{json_str}\n")
        else:
            json_str = jsonpickle.encode(results, make_refs=False, unpicklable=False)
            file.write(f"{json_str}\n")

def load_json_data(filepath):
    with open(filepath, "r") as file:
        records = file.readlines()
    data = []
    for record in records:
        d = json.loads(record)
        data.append(d)
    return data

def generate_repo_src_type_report(st_report_dir, export_path, data_export_path, repo_results):
    sorted_repo_results = sorted(repo_results, key=lambda x: x["coverage"], reverse=True)
    mdFile = MdUtils(file_name=export_path, title=f'Sage Repo Scan Report - {sorted_repo_results[0]["repo_name"]}')    
    header = ["src_type", "status", "playbooks (recorded/total)", "taskfiles", "roles", "tasks", "task recorded",  "enriched ftdata", "coverage (%)"]
    cells = header
    for data in sorted_repo_results:
        relative_path = os.path.relpath(data["detail_report_path"], st_report_dir)
        cells.append(f"[{data['src_type']}]({relative_path})")
        cells.append(data["status"])
        cells.append(f"{data['playbook_count_sage']}/{data['playbook_count_total']}")
        cells.append(f"{data['taskfile_count_sage']}/{data['taskfile_count_total']}")
        cells.append(data["role_count"])
        cells.append(data["task_count_total"])
        cells.append(data["task_count_sage"])
        cells.append(f'{data["task_count_enriched"]}/{data["task_count_org"]}')
        if data["coverage"] == -1:
            cells.append("N/A")
        else:
            cells.append(data["coverage"])
    mdFile.new_table(columns=9, rows=len(sorted_repo_results) + 1, text=cells, text_align='left')
    mdFile.create_md_file()
    json_result = {"md_path": export_path, "data": sorted_repo_results}
    export_result(data_export_path, json_result)
    return

def generate_repo_summary_report(outdir, src_type, detail_outdir, subdir):
    files = glob.glob(os.path.join(subdir,f"{src_type}*","summary.json"))
    repo_data = {}
    for f in files:
        summary_data = load_json_data(f)
        data = summary_data[0]["data"]
        for result in data:
            repo_name = result["repo_name"]
            if repo_name in repo_data:
                repo_data[repo_name].append(result)
            else:
                repo_data[repo_name] = [result]

    repo_summary = []
    for repo, data in repo_data.items():
        coverage = -1
        status = "x"

        task_count_org = sum(v["task_count_org"] for v in data)
        task_count_enriched = sum(v["task_count_enriched"] for v in data)
        if task_count_org != 0:
            p = task_count_enriched/task_count_org*100
            coverage = round(p, 2)
        if coverage == 100 or coverage == -1:
            status = "✔"

        # generate detail md
        st_report_dir = os.path.join(detail_outdir, repo)
        os.makedirs(st_report_dir, exist_ok=True)
        detail_md_path = os.path.join(st_report_dir, "README.md")
        detail_data_path = os.path.join(st_report_dir, "summary.json")
        generate_repo_src_type_report(st_report_dir, detail_md_path, detail_data_path, data)

        result = {
            "repo_name": repo,
            "status": status,
            "playbook_count_total": data[0]["playbook_count_total"],
            "playbook_count_sage": data[0]["playbook_count_sage"],
            "taskfile_count_total": data[0]["taskfile_count_total"],
            "taskfile_count_sage": data[0]["taskfile_count_sage"],
            "role_count": data[0]["role_count"],
            "task_count_total": data[0]["task_count_total"],
            "task_count_org": task_count_org,
            "task_count_sage": data[0]["task_count_sage"],
            "task_count_enriched": task_count_enriched,
            "coverage": coverage,
            "detail_report_path": detail_md_path,
        }
        repo_summary.append(result)

    sorted_repo_summary = sorted(repo_summary, key=lambda x: x["coverage"], reverse=True)

    export_path = os.path.join(outdir, f"README-{src_type}-repo.md")
    data_export_path = os.path.join(outdir, f"summary-{src_type}-repo.json")
    mdFile = MdUtils(file_name=export_path, title='Sage Repo Scan Report')    
    header = ["repo_name", "status", "playbooks (recorded/total)", "taskfiles", "roles", "tasks", "task recorded",  "enriched ftdata", "coverage (%)"]
    cells = header
    for data in sorted_repo_summary:
        relative_path = os.path.relpath(data["detail_report_path"], outdir)
        cells.append(f'[{data["repo_name"]}]({relative_path})')
        cells.append(data["status"])
        cells.append(f"{data['playbook_count_sage']}/{data['playbook_count_total']}")
        cells.append(f"{data['taskfile_count_sage']}/{data['taskfile_count_total']}")
        cells.append(data["role_count"])
        cells.append(data["task_count_total"])
        cells.append(data["task_count_sage"])
        cells.append(f'{data["task_count_enriched"]}/{data["task_count_org"]}')
        if data["coverage"] == -1:
            cells.append("N/A")
        else:
            cells.append(data["coverage"])
    mdFile.new_table(columns=9, rows=len(sorted_repo_summary) + 1, text=cells, text_align='left')
    mdFile.create_md_file()
    json_result = {"md_path": export_path, "data": sorted_repo_summary}
    export_result(data_export_path, json_result)
    return

def generate_src_type_derivation_summary_report(_type, outdir, subdir):
    files = glob.glob(f'{subdir}/{_type}*/summary.json')
    repo_data = {}
    for f in files:
        summary_data = load_json_data(f)
        data = summary_data[0]["data"]
        for result in data:
            src_type = result["src_type"]
            if src_type in repo_data:
                repo_data[src_type].append(result)
            else:
                repo_data[src_type] = [result]

    repo_summary = []
    for src_type, data in repo_data.items():
        coverage = -1
        status = "x"

        task_count_org = sum(v["task_count_org"] for v in data)
        task_count_enriched = sum(v["task_count_enriched"] for v in data)
        if task_count_org != 0:
            p = task_count_enriched/task_count_org*100
            coverage = round(p, 2)
        if coverage == 100 or coverage == -1:
            status = "✔"

        result = {
            "src_type": src_type,
            "status": status,
            "playbook_count_total": sum(v["playbook_count_total"] for v in data),
            "playbook_count_sage": sum(v["playbook_count_sage"] for v in data),
            "taskfile_count_total": sum(v["taskfile_count_total"] for v in data),
            "taskfile_count_sage": sum(v["taskfile_count_sage"] for v in data),
            "role_count": sum(v["role_count"] for v in data),
            "task_count_total": sum(v["task_count_total"] for v in data),
            "task_count_org": task_count_org,
            "task_count_sage": sum(v["task_count_sage"] for v in data),
            "task_count_enriched": task_count_enriched,
            "coverage": coverage,
        }
        repo_summary.append(result)

    sorted_repo_summary = sorted(repo_summary, key=lambda x: x["coverage"], reverse=True)

    export_path = os.path.join(outdir, f"README-{_type}-st.md")
    data_export_path = os.path.join(outdir, f"summary-{_type}-st.json")
    mdFile = MdUtils(file_name=export_path, title=f'Sage Repo Scan Report {_type}')    
    header = ["src_type", "status", "playbooks (recorded/total)", "taskfiles", "roles", "tasks", "task recorded",  "enriched ftdata", "coverage (%)"]
    cells = header
    for data in sorted_repo_summary:
        cells.append(data["src_type"])
        cells.append(data["status"])
        cells.append(f"{data['playbook_count_sage']}/{data['playbook_count_total']}")
        cells.append(f"{data['taskfile_count_sage']}/{data['taskfile_count_total']}")
        cells.append(data["role_count"])
        cells.append(data["task_count_total"])
        cells.append(data["task_count_sage"])
        cells.append(f'{data["task_count_enriched"]}/{data["task_count_org"]}')
        if data["coverage"] == -1:
            cells.append("N/A")
        else:
            cells.append(data["coverage"])
    mdFile.new_table(columns=9, rows=len(sorted_repo_summary) + 1, text=cells, text_align='left')
    mdFile.create_md_file()
    json_result = {"md_path": export_path, "org_src_type": _type, "data": sorted_repo_summary}
    export_result(data_export_path, json_result)
    return

def generate_top_report(outdir):
    files = glob.glob(f'{outdir}/summary-*st.json')
    summary = []
    for file in files:
        jd = load_json_data(file)
        src_type = jd[0]["org_src_type"]
        data = jd[0]["data"]
        coverage = -1
        status = "x"

        task_count_org = sum(v["task_count_org"] for v in data)
        task_count_enriched = sum(v["task_count_enriched"] for v in data)
        if task_count_org != 0:
            p = task_count_enriched/task_count_org*100
            coverage = round(p, 2)
        if coverage == 100 or coverage == -1:
            status = "✔"

        result = {
            "src_type": src_type,
            "status": status,
            "playbook_count_total": data[0]["playbook_count_total"],
            "playbook_count_sage": data[0]["playbook_count_sage"],
            "taskfile_count_total": data[0]["taskfile_count_total"],
            "taskfile_count_sage": data[0]["taskfile_count_sage"],
            "role_count": data[0]["role_count"],
            "task_count_total": data[0]["task_count_total"],
            "task_count_org": task_count_org,
            "task_count_sage": data[0]["task_count_sage"],
            "task_count_enriched": task_count_enriched,
            "coverage": coverage,
        }
        summary.append(result)

    sorted_summary = sorted(summary, key=lambda x: x["coverage"], reverse=True)

    export_path = os.path.join(outdir, f"README.md")
    data_export_path = os.path.join(outdir, f"summary.json")
    mdFile = MdUtils(file_name=export_path, title=f'Sage Repo Scan Report')    
    header = ["src_type", "status", "playbooks (recorded/total)", "taskfiles", "roles", "tasks", "task recorded",  "enriched ftdata", "coverage (%)"]
    cells = header
    for data in sorted_summary:
        cells.append(data["src_type"])
        cells.append(data["status"])
        cells.append(f"{data['playbook_count_sage']}/{data['playbook_count_total']}")
        cells.append(f"{data['taskfile_count_sage']}/{data['taskfile_count_total']}")
        cells.append(data["role_count"])
        cells.append(data["task_count_total"])
        cells.append(data["task_count_sage"])
        cells.append(f'{data["task_count_enriched"]}/{data["task_count_org"]}')
        if data["coverage"] == -1:
            cells.append("N/A")
        else:
            cells.append(data["coverage"])
    mdFile.new_table(columns=9, rows=len(sorted_summary) + 1, text=cells, text_align='left')
    mdFile.create_md_file()
    json_result = {"md_path": export_path, "data": sorted_summary}
    export_result(data_export_path, json_result)
    return


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    # parser.add_argument("-f", "--file", help='md file')
    parser.add_argument("-o", "--out-dir", help='e.g. /tmp/batch/report')
    parser.add_argument("-s", "--sage-dir", help="e.g. /tmp/batch/results")
    parser.add_argument("--ft-data-dir", help="e.g. /tmp/batch/data")
    parser.add_argument("-t", "--type", help="e.g. GitHub-RHIBM")
    parser.add_argument("--ftdata-type", help='specify the type if original ftdata type is different from src-type (e.g. GitHub-RHIBM-disambiguate-module)')
    parser.add_argument("--single", action="store_true", help="")

    args = parser.parse_args()

    results = args.sage_dir
    ftdata_dir = args.ft_data_dir
    outdir = args.out_dir

    src_type = args.type
    org_ftdata_type = args.ftdata_type
    ftdata_src_type_list = [
        "",
        "-disambiguate-module", 
        "-disambiguate-module-prompt_mutation", 
        "-disambiguate-platform-or-module", 
        "-disambiguate-platform-or-module-prompt_mutation",
        "-prompt_mutation",
        "-prompt_mutation-prompt_mutation",
        ]

    if not os.path.isdir(outdir):
        os.makedirs(outdir)

    single_scan_mode = args.single

    if single_scan_mode:
        md_export_path = os.path.join(outdir, "report.md")
        json_export_path = os.path.join(outdir, "summary.json")
        summary_data = generate_summary(json_export_path, results, ftdata_dir)
        _ = generate_detail_report(md_export_path, summary_data)
    else:
        detail_dir = os.path.join(outdir, "details")
        if not os.path.exists(detail_dir):
            os.makedirs(detail_dir)
        # per repo in src-type
        for _derivation in ftdata_src_type_list:
            org_ftdata_type = f"{src_type}{_derivation}"
            generate_main_report(ftdata_dir, results, detail_dir, src_type, org_ftdata_type)

            # summarize report
            # per repo (repo_name.md)
            repo_dir = os.path.join(outdir, "repo-results")
            generate_repo_summary_report(outdir, src_type, repo_dir, detail_dir)
            # per src-type derivation (GitHub-RHIBM.md)
            generate_src_type_derivation_summary_report(src_type, outdir, detail_dir) 
            # all (README.md)
            generate_top_report(outdir)
