import argparse
import os
import json
import jsonpickle
import glob
import re
import tempfile
import Levenshtein




class Mapping(object):
    def __init__(self, output_dir) -> None:
        self.output_dir = output_dir

    def run(self, ari_file, wisdom_file):
        ari_ftdata = load_json_data(ari_file)
        wisdom_ftdata = load_json_data(wisdom_file)
        print(f"comparing tasks: ari {len(ari_ftdata)} wisdom {(len(wisdom_ftdata))}")

        spec_match, similarity_match_list, only_wisdom = self.separate_wisdom_data(wisdom_ftdata, ari_ftdata)
        matched_list = []
        matched_list.extend(spec_match)
        matched_list.extend(similarity_match_list)

        modified_wisdom_ftdata = self.add_dense_context(matched_list)
        export_result(os.path.join(self.output_dir, "modified_ftdata.json"), modified_wisdom_ftdata)
        export_result(os.path.join(self.output_dir, "only_wisdom.json"), only_wisdom)
        return

    def export_tmp_file(self, type, sorted_data):
        file_list = []
        for repo, items in sorted_data.items():
            file_name = os.path.join(self.tmpdir, f"{type}-{repo}.json")
            write_result(file_name, items)
            file_list.append(file_name)
        return file_list

    def separate_wisdom_data(self, wisdom_list, ari_list):
        spec_match_list = []
        similarity_match_list = []
        only_wisdom = []

        for i, w_item in enumerate(wisdom_list):
            w_module_name = w_item.get("module_name")
            w_path = w_item.get("path").lstrip("/")
            w_output_script = w_item.get("output_script")
            w_output_script_parts = w_output_script.split("\n")
            w_task_spec_str = re.sub(r"[^a-zA-Z]", "", ''.join(w_output_script_parts)).lower()
            w_task_spec_str = ''.join(sorted(w_task_spec_str))

            for a_item in ari_list:
                a_module_name = a_item.get("module_name")
                a_path = a_item.get("path").lstrip("/")
                a_output_script = a_item.get("output_script")
                a_output_script_parts = a_output_script.split("\n")
                a_task_spec_str = re.sub(r"[^a-zA-Z]", "", ''.join(a_output_script_parts)).lower()
                a_task_spec_str = ''.join(sorted(a_task_spec_str))

                if w_path != a_path:
                    continue
                if w_module_name != a_module_name and not w_module_name.endswith(a_module_name):
                    continue

                # exact match
                if w_task_spec_str == a_task_spec_str:
                    if self.is_in_list(similarity_match_list, w_item):
                        matched = self.get_item_from_list(similarity_match_list, w_item)
                        for item in matched:
                            similarity_match_list.remove(item)
                    spec_match_list.append({"wisdom": w_item, "ari": a_item})
                    break
                # similarity
                elif Levenshtein.ratio(w_task_spec_str, a_task_spec_str) > 0.8:
                    if not self.is_in_list(spec_match_list, w_item):
                        if not self.is_in_list(similarity_match_list, w_item):
                            similarity_match_list.append({"wisdom": w_item, "ari": a_item})

        for w_item in wisdom_list:
            if not self.is_in_list(spec_match_list, w_item) and not self.is_in_list(similarity_match_list, w_item):
                only_wisdom.append(w_item)

        return spec_match_list, similarity_match_list, only_wisdom

    def add_dense_context(self, matched_list):
        modified_list = []
        for pair in matched_list:
            wisdom = pair["wisdom"]
            ari = pair["ari"]
            dense_context = ari["ari_new_context"]
            wisdom["new_context"] = dense_context
            modified_list.append(wisdom)
        return modified_list

    def is_in_list(self, items, target, key="wisdom"):
        for item in items:
            if item[key] == target:
                return True
        return False

    def get_item_from_list(self, items, target,  key="wisdom"):
        matched = []
        for item in items:
            if item[key] == target:
                matched.append(item)
        return matched

def load_json_data(filepath):
    with open(filepath, "r") as file:
        records = file.readlines()
    trains = []
    for record in records:
        train = json.loads(record)
        trains.append(train)
    return trains

def export_result(filepath, results):
    with open(filepath, "a") as file:
        if type(results) == list:
            for result in results:
                json_str = jsonpickle.encode(result, make_refs=False, unpicklable=False)
                file.write(f"{json_str}\n")
        else:
            json_str = jsonpickle.encode(results, make_refs=False, unpicklable=False)
            file.write(f"{json_str}\n")

def write_result(filepath, results):
    with open(filepath, "w") as file:
        if type(results) == list:
            for result in results:
                json_str = jsonpickle.encode(result, make_refs=False, unpicklable=False)
                file.write(f"{json_str}\n")
        else:
            json_str = jsonpickle.encode(results, make_refs=False, unpicklable=False)
            file.write(f"{json_str}\n")


def add_repo_info_from_inventory(inventory_file, ftdata_file, output_file):
    inventory = load_json_data(inventory_file)
    ftdata = load_json_data(ftdata_file)

    updated_ftdata = []

    for fd in ftdata:
        path = fd.get("path", "")
        scan_path = fd.get("scan_path", "")
        scan_type = fd.get("scan_type", "")
        for y in inventory:
            filepath = y.get("filepath", "")
            label = y.get("label", "")
            project_path = y.get("project_info", {}).get("path", "")
            project_name = y.get("project_info", {}).get("name", "")
            if scan_type == "project" and scan_path == project_path:
                if filepath.endswith(path):
                    fd["type"] = label
                    fd["repo_name"] = project_name
                    updated_ftdata.append(fd)

            elif scan_type == "taskfile" or scan_type == "playbook":
                if scan_path.endswith(filepath):
                    fd["type"] = label
                    fd["repo_name"] = project_name
                    fd["path"] = y.get("path_from_root","").lstrip("/")
                    updated_ftdata.append(fd)
            else:
                updated_ftdata.append(fd)
    
    write_result(output_file, updated_ftdata)
    return

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-s", "--sage-dir", help="")
    parser.add_argument("-w", "--wisdom", help="")
    parser.add_argument("-o", "--output-dir", help="")
    args = parser.parse_args()

    sage_dir = args.sage_dir
    if not os.path.isdir(sage_dir):
        print(f"no sage_dir exist: {sage_dir}")

    inventory_file = os.path.join(sage_dir, "yml_inventory.json")
    sage_ftdata = os.path.join(sage_dir, "ftdata.json")
    tmp_sage_ftdata = os.path.join(sage_dir, "ftdata-modified.json") # with correct path

    wisdom_input = args.wisdom
    output_dir = args.output_dir

    add_repo_info_from_inventory(inventory_file, sage_ftdata, tmp_sage_ftdata)

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    m = Mapping(output_dir)
    m.run(tmp_sage_ftdata, wisdom_input)
