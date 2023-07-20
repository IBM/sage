from mdutils.mdutils import MdUtils
from pathlib import Path
import os
import json
import argparse

def count_src_files(json_file_path):
    data = []
    with open(json_file_path, 'r') as file:
        for line in file:
            jo = json.loads(line)
            data.append(jo)

    value_counts = {
        "playbook": 0,
        "taskfile": 0,
        "others": 0,
        "error": 0,
        "role": 0,
        "external_dep": 0,
        "total_num_of_files": 0,
    }

    roles = []
    for item in data:
        label = item["label"]
        role_info = item["role_info"]
        if role_info:
            role_name = role_info["name"]
            if role_name not in roles:
                roles.append(role_name)

            is_external_dependency = role_info["is_external_dependency"]
            if is_external_dependency:
                value_counts["external_dep"] = value_counts.get("external_dep", 0) + 1
                continue
        value_counts[label] = value_counts.get(label, 0) + 1
    
    total_sum = 0
    for label in value_counts.values():
        if isinstance(label, (int, float)):
            total_sum += label
    value_counts["total_num_of_files"] = total_sum
    value_counts["role"] = len(roles)
    return value_counts

def count_file_type(json_file_path, key_type, key_path):
    data = []
    with open(json_file_path, 'r') as file:
        for line in file:
            jo = json.loads(line)
            data.append(jo)

    value_counts = {}
    paths = []
    for item in data:
        path = item[key_path]
        if path not in paths:
            value = item[key_type]
            value_counts[value] = value_counts.get(value, 0) + 1
            paths.append(path)

    total_sum = 0
    for value in value_counts.values():
        if isinstance(value, (int, float)):
            total_sum += value
    value_counts["total"] = total_sum
    return value_counts

def get_compare_result(f_matched, f_org_only, sage_ftdata):
    result = {}
    org_count = 0
    matched_count = 0

    data = []
    if os.path.exists(f_org_only):
        with open(f_org_only, 'r') as file:
            for line in file:
                jo = json.loads(line)
                data.append(jo)
        org_count = len(data)
    
    data = []
    if os.path.exists(f_matched):
        with open(f_matched, 'r') as file:
            for line in file:
                jo = json.loads(line)
                data.append(jo)
    
    matched_count = len(data)

    data = []
    if os.path.exists(sage_ftdata):
        with open(sage_ftdata, 'r') as file:
            for line in file:
                jo = json.loads(line)
                data.append(jo)
    sage_count = len(data)


    org_total = org_count + matched_count
    result["only_org_ftdata"] = org_count
    result["enriched_ftdata"] = matched_count
    result["sage_ftdata"] = sage_count
    result["org_total"] = org_total
    if org_total != 0:
        p = matched_count/org_total*100
        result["coverage"] = round(p, 2)
    else:
        result["coverage"] = -1
    return result

def get_roles(yml_inventory_file):
    roles = []
    if os.path.exists(yml_inventory_file):
        with open(yml_inventory_file, 'r') as file:
            for line in file:
                item = json.loads(line)
                role_info = item["role_info"]
                if role_info:
                    role_name = role_info["name"]
                    if role_name not in roles:
                        roles.append(role_name)
    return roles

def get_missing_tasks(only_org_file):
    missing_tasks = []
    if os.path.exists(only_org_file):
        with open(only_org_file, 'r') as file:  # ftdata-modified.json
            for line in file:
                jo = json.loads(line)
                missing_tasks.append({
                    "file": jo["path"],
                    "prompt": jo["prompt"]
                })
    return missing_tasks

def get_missing_files(yml_inventory_file, sage_ftdata_file):
    i_yamls = []
    if os.path.exists(yml_inventory_file):
        with open(yml_inventory_file, 'r') as file:
            for line in file:
                item = json.loads(line)
                label = item["label"]
                role_info = item["role_info"]
                if role_info:
                    is_external_dependency = role_info["is_external_dependency"]
                    if is_external_dependency:
                        continue
                if label == "others":
                    continue

                if label == "error":
                    continue
                y = {
                    "path": item["path_from_root"],
                    "type": label
                }
                if y not in i_yamls:
                    i_yamls.append(y)

    findings_json = yml_inventory_file.replace("yml_inventory.json", "findings.json")
    no_task_files = []
    task_exist_files = []
    if os.path.exists(findings_json):
        with open(findings_json, "r") as file:
            for line in file:
                findings = json.loads(line)
                definitions = findings.get("root_definitions", {}).get("definitions", {})
                _no_task_files, _task_exist_files = get_no_task_files(i_yamls, definitions)
                no_task_files.extend(_no_task_files)
                task_exist_files.extend(_task_exist_files)

    no_task_files = [dict(s) for s in set(frozenset(d.items()) for d in no_task_files)]
    no_task_files = [d for d in no_task_files if d not in task_exist_files]
    i_task_yamls = [d for d in i_yamls if d not in no_task_files]

    s_yamls = []
    if os.path.exists(sage_ftdata_file):
        with open(sage_ftdata_file, 'r') as file:  # ftdata-modified.json
            for line in file:
                jo = json.loads(line)
                s_yamls.append(jo["path"])

    diff_list = []
    for iy in i_task_yamls:
        p = iy["path"]
        t = iy["type"]
        if p not in s_yamls:
            diff_list.append(f"{p} ({t})")

    no_task_playbook = 0
    no_task_taskfile = 0
    for ntf in no_task_files:
        if ntf["type"] == "playbook":
            no_task_playbook += 1
        if ntf["type"] == "taskfile":
            no_task_taskfile += 1
    return diff_list, no_task_playbook, no_task_taskfile, no_task_files

def get_no_task_files(i_yamls, definitions):
    no_task_files = []
    task_exist_files = []
    for iy in i_yamls:
        if iy["type"] == "playbook":
            task_found = False
            root_obj_found = False
            playbooks = definitions.get("playbooks", [])
            for playbook in playbooks:
                if iy["path"].endswith(playbook["defined_in"]):
                    root_obj_found = True
                    plays = playbook.get("plays", [])
                    if len(plays) == 0:
                        continue
                    else:
                        d_plays = definitions.get("plays", [])
                        for p in plays:
                            for dp in d_plays:
                                p_key = dp.get("key", "")
                                if p == p_key:
                                    p_tasks = dp.get("tasks", [])
                                    if len(p_tasks) != 0:
                                        task_found = True
                                    post_tasks = dp.get("post_tasks", [])
                                    if len(post_tasks) != 0:
                                        task_found = True
                                    pre_tasks = dp.get("pre_tasks", [])
                                    if len(pre_tasks) != 0:
                                        task_found = True
            if root_obj_found and not task_found:
                no_task_files.append(iy)
            if root_obj_found and task_found:
                task_exist_files.append(iy)
        if iy["type"] == "taskfile":
            task_found = False
            root_obj_found = False
            taskfiles = definitions.get("taskfiles", [])
            for taskfile in taskfiles:
                if iy["path"].endswith(taskfile["defined_in"]):
                    root_obj_found = True
                    t_tasks = taskfile["tasks"]
                    if len(t_tasks) != 0:
                        task_found = True
            if root_obj_found and not task_found:
                no_task_files.append(iy)
            if root_obj_found and task_found:
                task_exist_files.append(iy)
    return no_task_files, task_exist_files

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
    return target_files, out_of_scope

def count_tasks_in_findings(findings_json):
    file_tasks = {}
    if os.path.exists(findings_json):
        with open(findings_json, "r") as file:
            for line in file:
                findings = json.loads(line)
                definitions = findings.get("root_definitions", {}).get("definitions", {})
                playbooks = definitions.get("playbooks", [])
                for playbook in playbooks:
                    tasks = []
                    path = playbook["defined_in"].lstrip("/")
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
                    t_tasks = taskfile["tasks"]
                    if path not in file_tasks:
                        file_tasks[path] = t_tasks
                    else:
                        _tasks = file_tasks[path]
                        _tasks.extend(t_tasks)
                        file_tasks[path] = list(set(_tasks))
    file_task_count = {}
    for p, t in file_tasks.items():
        file_task_count[p] = len(t)
    return file_task_count


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
    for d in data:
        path = d["path"].lstrip("/")
        if path in missing_task_count:
            missing_task_count[path]["count"] = missing_task_count[path].get("count", 0) + 1
            missing_task_count[path]["detail"].append(d["prompt"])
        else:
            missing_task_count[path] = {}
            missing_task_count[path]["count"] = missing_task_count[path].get("count", 0) + 1
            missing_task_count[path]["detail"] = [d["prompt"]]

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
    return missing_task_count, matched_task_count

def count_tasks_in_sage_ftdata(sage_ftdata_file):
    data = []
    if os.path.exists(sage_ftdata_file):
        with open(sage_ftdata_file, 'r') as file:
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
        if type == "taskfile":
            if path not in taskfiles:
                taskfiles.append(path)
    return task_count, playbooks, taskfiles

def get_file_type_count(out_of_scopes, target_files, task_counts_findings):
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
        fc = _get_task_count(path, task_counts_findings)
        if fc == 0:
            no_task_count += 1
            continue
        if type == "playbook":
            playbook_count += 1
        if type == "taskfile":
            taskfile_count += 1
    return playbook_count, taskfile_count, no_task_count, error_count, others_count, external_dep

def generate_new_detail_report(export_path, sage_dir, ft_tmp_dir, org_ft_dir):
    yml_inventory_file = os.path.join(sage_dir, "yml_inventory.json")
    findings_json = os.path.join(sage_dir, "findings.json")
    ftdata_file = os.path.join(org_ft_dir, "org-ftdata.json")
    sage_ftdata_file = os.path.join(sage_dir, "ftdata-modified.json")
    f_org_only = os.path.join(ft_tmp_dir, "only_org_ftdata.json")
    f_matched = os.path.join(ft_tmp_dir, "modified_ftdata.json")

    # src_type = file_scan_res["src_type"] 
    # repo_name = file_scan_res["repo_name"]
    title = f"Sage Repo Scan Report"
    mdFile = MdUtils(file_name=export_path, title=title)

    # mdFile.new_line(f"src_type: {src_type}")
    # mdFile.new_line(f"src_file: RH_IBM_FT_data_GH_api.json")
    # mdFile.new_line(f"original ftdata: awft_v5.5.2_train, test, val")
    mdFile.new_line(f"yml_inventory_file: {yml_inventory_file}")
    mdFile.new_line(f"findings_json: {findings_json}")
    mdFile.new_line(f"original ftdata_file: {ftdata_file}")
    mdFile.new_line(f"sage_ftdata_file: {sage_ftdata_file}")


    target_files, out_of_scopes = get_yml_inventory(yml_inventory_file)
    task_count_findings = count_tasks_in_findings(findings_json)
    task_count_org, o_playbooks, o_taskfiles = count_tasks_in_org_ftdata(ftdata_file)
    task_count_sage, s_playbooks, s_taskfiles = count_tasks_in_sage_ftdata(sage_ftdata_file)
    task_count_missing, task_count_enriched = count_enriched_ftdata(f_org_only, f_matched)


    mdFile.new_header(level=1, title='Yaml file inventory')
    header = ["playbooks", "taskfiles", "no task", "external dep", "others", "parse error", "total_num"]
    cells = header
    playbook_count, taskfile_count, no_task_count, error_count, others_count, external_dep = get_file_type_count(out_of_scopes, target_files, task_count_findings)
    cells.append(playbook_count)
    cells.append(taskfile_count)
    cells.append(no_task_count)
    cells.append(external_dep)
    cells.append(others_count)
    cells.append(error_count)
    cells.append(playbook_count+taskfile_count+no_task_count+external_dep+others_count+error_count)
    mdFile.new_table(columns=7, rows=2, text=cells, text_align='left')
    
     # file scan result
    mdFile.new_header(level=1, title='File scan result')
    header = ["", "sage", "original"]
    cells = header
    cells.append("playbook")
    cells.append(len(s_playbooks))
    cells.append(len(o_playbooks))
    cells.append("taskfile")
    cells.append(len(s_taskfiles))
    cells.append(len(o_taskfiles))
    mdFile.new_table(columns=3, rows=3, text=cells, text_align='left')

    # task scan result
    mdFile.new_header(level=1, title='Task scan result')
    header = ["sage ftdata", "original ftdata", "updated", "unchanged"]
    cells = header
    tc_f_total = sum(task_count_findings.values())
    tc_s_total = sum(task_count_sage.values())
    tc_o_total = sum(task_count_org.values())
    tc_e_total = sum(task_count_enriched.values())
    tc_m_total = 0
    for m in task_count_missing:
        tc_m_total += task_count_missing[m]["count"]
    # cells.append(tc_f_total)
    cells.append(tc_s_total)
    cells.append(tc_o_total)
    cells.append(tc_e_total)
    cells.append(tc_m_total)
    mdFile.new_table(columns=4, rows=2, text=cells, text_align='left')

    # tasks
    mdFile.new_header(level=1, title='Tasks scanned per file')
    # files | type | role | findings count |ari count | wisdom count | enriched count | unchanged count | o/x　
    header = ["path", "type", "role", "findings", "sage", "org", "enriched", "unchanged", "status"]
    cells = header
    for ty in target_files:
        path = ty["path"]
        cells.append(path)
        cells.append(ty["type"])
        cells.append(ty.get("role", ""))
        fc = _get_task_count(path, task_count_findings)
        cells.append(fc)
        cells.append(task_count_sage.get(path, 0))
        cells.append(task_count_org.get(path, 0))
        cells.append(task_count_enriched.get(path, 0))
        if task_count_missing.get(path, {}):
            cells.append(task_count_missing[path]["count"])
        else:
            cells.append(0)
        if task_count_enriched.get(path, 0) >= task_count_org.get(path, 0):
            cells.append("✔")
        else:
            cells.append("x")
    mdFile.new_table(columns=9, rows=len(target_files)+1, text=cells, text_align='left')
    mdFile.create_md_file()
    return

def _get_task_count(path, file_tasks):
    for p, c in file_tasks.items():
        if path.endswith(p):
            return c
    return -1


def generate_main_report(sorted_file_scan_results, outdir, subdir):
    export_path = os.path.join(outdir, "sage_data_scan_report.md")
    mdFile = MdUtils(file_name=export_path, title='Sage Repo Scan Report')

    # mdFile.new_header(level=1, title='Num. of Source Files')
    mdFile.new_line(f"src_type: {sorted_file_scan_results[0]['src_type']}")
    mdFile.new_line(f"src_file: RH_IBM_FT_data_GH_api.json")
    mdFile.new_line(f"original ftdata: awft_v5.5.2_train, test, val")
    
    header = ["repo_name", "playbooks (org)", "taskfiles (org)", "roles", "tasks", "enriched ftdata", "coverage (%)", "status"]
    cells = header
    for fsr in sorted_file_scan_results:
        # prepare single report
        src_type = fsr["src_type"] 
        repo_name = fsr["repo_name"]
        detail_report_path = os.path.join(subdir, f"{src_type}-{repo_name}.md")
        target_file_dir = os.path.dirname(detail_report_path)
        if not os.path.exists(target_file_dir):
            os.makedirs(target_file_dir)
        generate_detail_report(detail_report_path, fsr)
        relative_path = detail_report_path.replace(outdir, "")
        if relative_path.startswith("/"):
            relative_path = relative_path.replace("/", "./", 1)

        f_sage_ftdata = fsr["sage_ftdata"]
        org_ftdata = fsr["org_ftdata"]

        sp = st = wp = wt = 0
        if "playbook" in f_sage_ftdata:
            sp = f_sage_ftdata["playbook"]
        if "taskfile" in f_sage_ftdata:
           st = f_sage_ftdata["taskfile"]
        if "playbook" in org_ftdata:
            wp = org_ftdata["playbook"]
        if "task" in org_ftdata:
            wt = org_ftdata["task"]

        cells.append(f"[{repo_name}]({relative_path})")
        cells.append(f"{sp} ({wp})")
        cells.append(f"{st} ({wt})")
        cells.append(fsr["label_counts"]["role"])

        scanned_tasks = fsr["scanned_tasks"]
        cells.append(scanned_tasks["sage_ftdata"])
        enriched_ftdata = scanned_tasks["enriched_ftdata"]
        org_total = scanned_tasks["org_total"]
        cells.append(f"{enriched_ftdata}/{org_total}")
        p = scanned_tasks["coverage"]
        if p == -1:
            p = "N/A"
        cells.append(p)
        if p == 100 or p == "N/A":
            cells.append("✔")
        else:
            cells.append("x")
    mdFile.new_table(columns=8, rows=len(file_scan_results) + 1, text=cells, text_align='left')

    mdFile.create_md_file()
    return

def generate_detail_report(export_path, file_scan_res):
    src_type = file_scan_res["src_type"] 
    repo_name = file_scan_res["repo_name"]
    title = f"Sage Repo Scan Report: [{repo_name}](https://github.com/{repo_name})"
    mdFile = MdUtils(file_name=export_path, title=title)

    mdFile.new_line(f"src_type: {src_type}")
    mdFile.new_line(f"src_file: RH_IBM_FT_data_GH_api.json")
    mdFile.new_line(f"original ftdata: awft_v5.5.2_train, test, val")

    # missing file
    file_paths = file_scan_res["paths"]
    yml_inventory_file = file_paths["yml_inventory"]
    sage_ftdata_file = file_paths["sage_ftdata"]
    org_only_file = file_paths["org_only"]
    sage_missing_files, no_task_playbook_count, no_task_taskfile_count, _ = get_missing_files(yml_inventory_file, sage_ftdata_file)

    # ymls
    mdFile.new_header(level=1, title='Yaml file inventory')
    header = ["playbooks", "taskfiles", "no task", "external dep", "others", "parse error", "total_num"]
    cells = header
    label_counts = file_scan_res["label_counts"]
    cells.append(label_counts["playbook"] - no_task_playbook_count)
    cells.append(label_counts["taskfile"] - no_task_taskfile_count)
    cells.append(no_task_playbook_count+no_task_taskfile_count)
    cells.append(label_counts["external_dep"])
    cells.append(label_counts["others"])
    cells.append(label_counts["error"])
    cells.append(label_counts["total_num_of_files"])
    mdFile.new_table(columns=7, rows=2, text=cells, text_align='left')

    # role
    mdFile.new_header(level=1, title='role inventory')
    header = ["roles"]
    cells = header
    label_counts = file_scan_res["label_counts"]
    cells.append(label_counts["role"])
    mdFile.new_table(columns=1, rows=2, text=cells, text_align='left')
    roles = get_roles(yml_inventory_file)
    if len(roles) < 10:
        mdFile.new_list(roles)

    # file scan result
    mdFile.new_header(level=1, title='File scan result')
    header = ["", "sage", "original"]
    cells = header
    cells.append("playbook")
    sage_ftdata = file_scan_res["sage_ftdata"]
    if "playbook" in sage_ftdata:
        cells.append(sage_ftdata["playbook"])
    else:
        cells.append(0)
    org_ftdata = file_scan_res["org_ftdata"]
    if "playbook" in org_ftdata:
        cells.append(org_ftdata["playbook"])
    else:
        cells.append(0)
    
    cells.append("taskfile")
    if "taskfile" in sage_ftdata:
        cells.append(sage_ftdata["taskfile"])
    else:
        cells.append(0)

    if "task" in org_ftdata:
        cells.append(org_ftdata["task"])
    else:
        cells.append(0)
    mdFile.new_table(columns=3, rows=3, text=cells, text_align='left')

    # task scan result
    mdFile.new_header(level=1, title='Task scan result')
    header = ["sage ftdata", "original ftdata", "updated", "unchanged"]
    cells = header
    sct = file_scan_res["scanned_tasks"]
    if "sage_ftdata" in sct:
        cells.append(sct["sage_ftdata"])
    else:
        cells.append(0)
    if "org_total" in sct:
        cells.append(sct["org_total"])
    else:
        cells.append(0)
    if "enriched_ftdata" in sct:
        cells.append(sct["enriched_ftdata"])
    else:
        cells.append(0)

    if "only_org_ftdata" in sct:
        cells.append(sct["only_org_ftdata"])
    else:
        cells.append(0)
    mdFile.new_table(columns=4, rows=2, text=cells, text_align='left')

    # missing file
    mdFile.new_header(level=1, title='missing file list')
    mdFile.new_list(sage_missing_files)
    # missing task
    sage_missing_tasks = get_missing_tasks(org_only_file)
    mdFile.new_header(level=1, title='unchanged tasks')
    header = ["file", "prompt"]
    cells = header
    for t in sage_missing_tasks:
         cells.append(t["file"])
         cells.append(t["prompt"])
    mdFile.new_table(columns=2, rows=len(sage_missing_tasks)+1, text=cells, text_align='left')

    mdFile.create_md_file()
    return

def make_file_scan_result(f_inventory_str, f_org_ftdata, f_enriched_ftdata, src_name="", repo_name=""):
    # get yml inventory
    label_counts = count_src_files(f_inventory_str)
    # files scanned by sage
    f_sage_ftdata = f_inventory_str.replace("yml_inventory.json", "ftdata-modified.json")
    if os.path.exists(f_sage_ftdata):
        sage_scanned_file_count = count_file_type(f_sage_ftdata, "type", "path")
    else:
        sage_scanned_file_count = {}
    # files scanned by wisdom
    if os.path.exists(f_org_ftdata):
        org_scanned_file_count = count_file_type(f_org_ftdata, "type", "path")
    else:
        org_scanned_file_count = {}
    
    file_scan_res = {}
    file_scan_res["src_type"] = src_name
    file_scan_res["repo_name"] = repo_name
    file_scan_res["label_counts"] = label_counts
    file_scan_res["sage_ftdata"] = sage_scanned_file_count
    file_scan_res["org_ftdata"] = org_scanned_file_count

    f_org_only = f_enriched_ftdata.replace("modified_ftdata.json", "only_org_ftdata.json")
    c_res = get_compare_result(f_enriched_ftdata, f_org_only, f_sage_ftdata)
    file_scan_res["scanned_tasks"] = c_res

    # path list
    paths = {
        "yml_inventory": f_inventory_str,
        "sage_ftdata": f_sage_ftdata,
        "org_ftdata": f_org_ftdata,
        "enriched_ftdata": f_enriched_ftdata,
        "org_only": f_org_only,
    }
    file_scan_res["paths"] = paths
    return file_scan_res


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    # parser.add_argument("-f", "--file", help='md file')
    parser.add_argument("-o", "--out-dir", help='e.g. /tmp/batch/report')
    parser.add_argument("-s", "--sage-dir", help="e.g. /tmp/batch/results")
    parser.add_argument("--ft-data-dir", help="e.g. /tmp/batch/data")
    parser.add_argument("--ft-tmp-dir", help="e.g. /tmp/batch/tmp")
    parser.add_argument("-t", "--type", help="e.g. GitHub-RHIBM")
    parser.add_argument("--single", action="store_true", help="")

    args = parser.parse_args()

    results = args.sage_dir
    ftdata_dir = args.ft_data_dir
    tmp_dir = args.ft_tmp_dir 
    outdir = args.out_dir
    if not os.path.isdir(outdir):
        os.makedirs(outdir)

    single_scan_mode = args.single

    if single_scan_mode:
        # f_inventory_str = os.path.join(results, "yml_inventory.json")
        export_path = os.path.join(outdir, "report.md")
        # f_org_ftdata = os.path.join(ftdata_dir, "org-ftdata.json")
        # f_enriched_ftdata = os.path.join(tmp_dir, "modified_ftdata.json")
        # file_scan_res = make_file_scan_result(f_inventory_str, f_org_ftdata, f_enriched_ftdata)
        # generate_detail_report(export_path, file_scan_res)
        generate_new_detail_report(export_path, results, tmp_dir, ftdata_dir)
    else:
        subdir = os.path.join(outdir, "details")
        if not os.path.exists(subdir):
            os.makedirs(subdir)

        file_scan_results = []
        for f_inventory in Path(results).rglob("yml_inventory.json"):
            if Path.is_file(f_inventory):
                f_inventory_str = str(f_inventory)
                parts = f_inventory_str.split("/")
                # project
                repo_name = f"{parts[-3]}/{parts[-2]}"
                src_name = parts[-4]
                f_org_ftdata = os.path.join(ftdata_dir, src_name, repo_name, "org-ftdata.json")
                f_enriched_ftdata = os.path.join(tmp_dir, src_name, repo_name, "modified_ftdata.json")
                file_scan_res = make_file_scan_result(f_inventory_str, f_org_ftdata, f_enriched_ftdata, src_name, repo_name)
                file_scan_results.append(file_scan_res)
        
        # sort by coverage
        sorted_file_scan_results = sorted(file_scan_results, key=lambda x: x["scanned_tasks"]["coverage"], reverse=True)

        generate_main_report(sorted_file_scan_results, outdir, subdir)
