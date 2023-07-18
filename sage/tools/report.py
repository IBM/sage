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

    value_counts = {}
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
        # todo: remove num of tasks == 0
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

def get_compare_result(f_str, f_org_only, sage_ftdata):
    result = {}
    org_count = 0
    matched_count = 0
    if os.path.exists(f_org_only):
        data = []
        with open(f_org_only, 'r') as file:
            for line in file:
                jo = json.loads(line)
                data.append(jo)
        org_count = len(data)
    
    data = []
    with open(f_str, 'r') as file:
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
    p = matched_count/org_total*100
    result["coverage"] = round(p, 2)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--file", help='md file')
    # parser.add_argument("-t", "--type", help='type of data source')
    # parser.add_argument("-d", "--dir", help='tmp dir to recreate source dir')
    # parser.add_argument("-o", "--out-file", help="output directory for the rule evaluation result")
    args = parser.parse_args()

    path_list_dir = "/tmp/batch/path_list"
    results = "/tmp/batch/results"
    ftdata_dir = "/tmp/batch/data"
    tmp_dir = "/tmp/batch/tmp"
    src_dir = "/tmp/batch/src_rb"

    file_scan_results = []
    for f in Path(results).rglob("yml_inventory.json"):
        if Path.is_file(f):
            f_str =  str(f)
            parts = f_str.split("/")
            # project
            repo_name = f"{parts[-3]}/{parts[-2]}"
            src_name = parts[-4]
            # get yml inventory
            label_counts = count_src_files(f_str)
            # files scanned by sage
            sage_ftdata = f_str.replace("yml_inventory.json", "ftdata-modified.json")
            if os.path.exists(sage_ftdata):
                sage_scanned_file_count = count_file_type(sage_ftdata, "type", "path")
            else:
                sage_scanned_file_count = {}
            # files scanned by wisdom
            org_ftdata_file = os.path.join(ftdata_dir, src_name, repo_name, "org-ftdata.json")
            if os.path.exists(org_ftdata_file):
                org_scanned_file_count = count_file_type(org_ftdata_file, "type", "path")
            else:
                org_scanned_file_count = {}
            
            file_scan_res = {}
            file_scan_res["src_type"] = src_name
            file_scan_res["repo_name"] = repo_name
            file_scan_res["playbook"] = label_counts.get("playbook", 0)
            file_scan_res["taskfile"] = label_counts.get("taskfile", 0)
            file_scan_res["total_num_of_files"] = label_counts.get("total_num_of_files", 0)
            file_scan_res["role"] = label_counts.get("role", 0)
            file_scan_res["sage_ftdata"] = sage_scanned_file_count
            file_scan_res["org_ftdata"] = org_scanned_file_count

            mf_str = os.path.join(tmp_dir, src_name, repo_name, "modified_ftdata.json")
            f_org_only = mf_str.replace("modified_ftdata.json", "only_org_ftdata.json")
            c_res = get_compare_result(f_str, f_org_only, sage_ftdata)
            file_scan_res["scanned_tasks"] = c_res
            file_scan_results.append(file_scan_res)
    
    # sort by coverage
    sorted_file_scan_results = sorted(file_scan_results, key=lambda x: x["scanned_tasks"]["coverage"], reverse=True)


    export_path = "sage_data_scan_report.md"
    if args.file:
        export_path = args.file
    mdFile = MdUtils(file_name=export_path, title='Sage Repo Scan Report')

    # mdFile.new_header(level=1, title='Num. of Source Files')
    mdFile.new_line(f"src_type: {sorted_file_scan_results[0]['src_type']}")
    mdFile.new_line(f"src_file: RH_IBM_FT_data_GH_api.json")
    mdFile.new_line(f"original ftdata: awft_v5.5.2_train.json")
    
    header = ["repo_name", "playbooks (org)", "taskfiles (org)", "roles", "tasks", "enriched ftdata", "coverage (%)"]
    cells = header
    for fsr in sorted_file_scan_results:
        sage_ftdata = fsr["sage_ftdata"]
        org_ftdata = fsr["org_ftdata"]

        sp = 0
        st = 0
        wp = 0
        wt = 0
        if "playbook" in sage_ftdata:
            sp = sage_ftdata["playbook"]
        if "taskfile" in sage_ftdata:
           st = sage_ftdata["taskfile"]
        if "playbook" in org_ftdata:
            wp = org_ftdata["playbook"]
        if "task" in org_ftdata:
            wt = org_ftdata["task"]

        cells.append(fsr["repo_name"])
        cells.append(f"{sp} ({wp})")
        cells.append(f"{st} ({wt})")
        cells.append(fsr["role"])

        scanned_tasks = fsr["scanned_tasks"]
        cells.append(scanned_tasks["sage_ftdata"])
        enriched_ftdata = scanned_tasks["enriched_ftdata"]
        org_total = scanned_tasks["org_total"]
        cells.append(f"{enriched_ftdata}/{org_total}")
        cells.append(scanned_tasks["coverage"])
    mdFile.new_table(columns=7, rows=len(file_scan_results) + 1, text=cells, text_align='left')

    mdFile.create_md_file()


