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


def find_result(result, type, target, rule_id):
    roots = []
    playbooks = result.playbooks()
    roles = result.roles()
    if playbooks:
        roots.extend(playbooks.targets)
    if roles:
        roots.extend(roles.targets)

    print("num of root:", len(roots))
    results = []
    for root in roots:
        tasks = root.tasks()
        if not tasks:
            raise ValueError("the task was not found")

        if len(tasks.nodes) != 0:
            for task in tasks.nodes:
                rule_result = task.find_result(rule_id=rule_id)
                if rule_result:
                    if rule_result.error:
                        raise ValueError(f"the rule could not be evaluated: {rule_result.error}")
                    # get some info from the rule_result detail
                    if rule_result.verdict:
                        detail_dict = rule_result.get_detail()
                        if detail_dict:
                            # print(json.dumps(detail_dict, indent=4))
                            results.append(detail_dict)
                            # return detail_dict
                else:
                    raise ValueError("the rule result was not found")

    return results


class PreProcesser(object):
    args = None
    _scanner = None
    start = None

    def __init__(self, args):
        self.args = args

        use_ansible_doc = True
        read_ram = False
        write_ram = False
        read_ram_for_dependency = True

        data_dir = "/Users/hiro/ari-kb/ram-generate/ram-all-20230704"
        self.data_dir = data_dir
        self._scanner = ARIScanner(
            Config(
                rules_dir=os.path.join(os.path.dirname(__file__), "rules"),
                # data_dir=config.data_dir,
                data_dir=data_dir,
                rules=[
                    "P001",
                    "P002",
                    "P003",
                    "P004",
                    args.rule,
                ],
            ),
            silent=True,
            use_ansible_doc=use_ansible_doc,
            persist_dependency_cache=True,
            read_ram=read_ram,
            read_ram_for_dependency=read_ram_for_dependency,
            write_ram=write_ram,
        )
        self.all_ymls = []
        self.project_file_list = {}
        self.role_file_list = {}
        self.independent_file_list = []

        self.non_task_scanned_files = []
        self.missing_files = []

    def run(self, target_list, output_path):
        args = self.args

        resume = -1
        if args.resume:
            resume = int(args.resume)

        self.all_ymls = target_list

        project_file_list, role_file_list, independent_file_list = create_scan_list(target_list)
        # used for detecting missing files at the 1st scan
        self.project_file_list = project_file_list
        self.role_file_list = role_file_list
        self.independent_file_list = independent_file_list

        num = len(project_file_list) + len(role_file_list) + len(independent_file_list)
        resume_str = f"(resume from {resume})" if resume > 0 else ""
        target_counts = []
        if project_file_list:
            target_counts.append(f"{len(project_file_list)} projects")
        if role_file_list:
            target_counts.append(f"{len(role_file_list)} roles")
        if independent_file_list:
            target_counts.append(f"{len(independent_file_list)} playbooks/taskfiles")
        target_str = ", ".join(target_counts)
        total_str = f"(total {len(target_list)} files)"

        print(f"Start scanning for {target_str} {total_str} {resume_str}")

        input_list = []

        i = 0
        for project_name in project_file_list:
            _type = "project"
            _name = project_name
            project_path = project_file_list[project_name].get("path")
            input_list.append((i, num, _type, _name, project_path))
            i += 1

        for role_name in role_file_list:
            _type = "role"
            _name = role_name
            role_path = role_file_list[role_name].get("path")
            input_list.append((i, num, _type, _name, role_path))
            i += 1

        for file in independent_file_list:
            _name = file.get("filepath")
            filepath = _name
            _type = file.get("label")
            if _type in ["playbook", "taskfile"]:
                input_list.append((i, num, _type, _name, filepath))
            i += 1

        self.start = time.time()
        for (i, num, _type, _name, _full_path) in input_list:
            self.scan(i, num, _type, _name, _full_path, _type)

        missing_files = []
        for project_name in self.project_file_list:
            for file in self.project_file_list[project_name]["files"]:
                label = file.get("label", "")
                filepath = file.get("filepath", "")
                task_scanned = file.get("task_scanned", False)
                role_info = file.get("role_info", {})
                non_task_scanned = True if filepath in self.non_task_scanned_files else False
                if not task_scanned and not non_task_scanned and label in ["playbook", "taskfile"]:
                    if role_info and role_info.get("is_external_dependency", False):
                        continue
                    _type = label
                    _name = filepath
                    missing_files.append((_type, _name, filepath, "project"))

        for role_name in self.role_file_list:
            for file in self.role_file_list[role_name]["files"]:
                label = file.get("label", "")
                filepath = file.get("filepath", "")
                task_scanned = file.get("task_scanned", False)
                role_info = file.get("role_info", {})
                non_task_scanned = True if filepath in self.non_task_scanned_files else False
                if not task_scanned and not non_task_scanned and label in ["playbook", "taskfile"]:
                    if role_info and role_info.get("is_external_dependency", False):
                        continue
                    _type = label
                    _name = filepath
                    missing_files.append((_type, _name, filepath, "role"))
        
        self.missing_files = missing_files
        num_of_missing = len(missing_files)
        second_input_list = [(i, num_of_missing, _type, _name, filepath, original_type) for i, (_type, _name, filepath, original_type) in enumerate(missing_files)]
        self.start = time.time()
        for (i, num, _type, _name, _full_path, original_type) in second_input_list:
            self.scan(i, num, _type, _name, _full_path, original_type)

        self.save_yml_inventory(output_path)

        self.task_context_to_ftdata(self.args.out_dir)

    def scan(self, i, num, type, name, path, original_type):
        args = self.args
        elapsed = round(time.time() - self.start, 2)
        start_of_this_scan = time.time()
        thread_id = threading.get_native_id()
        print(f"[{i+1}/{num}] start {type} {name} {path} ({elapsed} sec. elapsed) (thread: {thread_id})")
        use_src_cache = True

        taskfile_only = False
        playbook_only = False
        out_dir_basename = name
        if type != "role" and type != "project":
            taskfile_only = True
            playbook_only = True
            out_dir_basename = escape_local_path(name)

        result = None
        scandata = None
        try:
            out_dir = ""
            if args.out_dir and args.rule_result:
                out_dir = os.path.join(args.out_dir, type, out_dir_basename)
            result = self._scanner.evaluate(
                type=type,
                name=path,
                install_dependencies=True,
                include_test_contents=args.include_tests,
                objects=args.objects,
                out_dir=out_dir,
                load_all_taskfiles=True,
                use_src_cache=use_src_cache,
                taskfile_only=taskfile_only,
                playbook_only=playbook_only
            )
            scandata = self._scanner.get_last_scandata()
        except Exception:
            error = traceback.format_exc()
            self._scanner.save_error(error)
            if error:
                print(f"Failed to scan {path} in {name}: error detail: {error}")

        if result:
            for target_result in result.targets:
                for node_result in target_result.nodes:
                    if not node_result:
                        continue
                    if not isinstance(node_result, NodeResult):
                        raise ValueError(f"node_result must be a NodeResult instance, but {type(node_result)}")
                    rule_result = node_result.find_result(self.args.rule)
                    if not isinstance(rule_result, RuleResult):
                        raise ValueError(f"rule_result must be a RuleResult instance, but {type(rule_result)}")
                    if rule_result.error:
                        spec = node_result.node.spec
                        key = spec.key

        if scandata:
            all_scanned_files = self.get_all_files_from_scandata(scandata, path)
            task_scanned_files = [fpath for fpath, scan_type in all_scanned_files if scan_type == "task"]
            play_scanned_files = [fpath for fpath, scan_type in all_scanned_files if scan_type == "play"]
            found_files = []
            if original_type == "project":
                if name in self.project_file_list:
                    files_num = len(self.project_file_list[name]["files"])
                    for j in range(files_num):
                        fpath = self.project_file_list[name]["files"][j]["filepath"]
                        if fpath in task_scanned_files:
                            self.project_file_list[name]["files"][j]["task_scanned"] = True
                            self.project_file_list[name]["files"][j]["scanned_as"] = type
                        elif fpath in play_scanned_files:
                            self.project_file_list[name]["files"][j]["scanned_as"] = type
                            self.non_task_scanned_files.append(fpath)

            elif original_type == "role":
                if name in self.role_file_list:
                    files_num = len(self.role_file_list[name]["files"])
                    for j in range(files_num):
                        fpath = self.role_file_list[name]["files"][j]["filepath"]
                        if fpath in task_scanned_files:
                            self.role_file_list[name]["files"][j]["task_scanned"] = True
                            self.role_file_list[name]["files"][j]["scanned_as"] = type
                        elif fpath in play_scanned_files:
                            self.role_file_list[name]["files"][j]["scanned_as"] = type
                            self.non_task_scanned_files.append(fpath)
            else:
                files_num = len(self.independent_file_list)
                for j in range(files_num):
                    fpath = self.independent_file_list[j]["filepath"]
                    if fpath in task_scanned_files:
                        self.independent_file_list[j]["task_scanned"] = True
                        self.independent_file_list[j]["scanned_as"] = type
                    elif fpath in play_scanned_files:
                        self.independent_file_list[j]["scanned_as"] = type
                        self.non_task_scanned_files.append(fpath)

        elapsed_for_this_scan = round(time.time() - start_of_this_scan, 2)
        if elapsed_for_this_scan > 60:
            print(f"WARNING: It took {elapsed_for_this_scan} sec. to process [{i+1}/{num}] {type} {name}")

    def get_all_files_from_scandata(self, scandata, scan_root_dir):
        
        task_specs = scandata.root_definitions.get("definitions", {}).get("tasks", [])
        all_files = []
        for task_spec in task_specs:
            fullpath = os.path.join(scan_root_dir, task_spec.defined_in)
            if fullpath not in all_files:
                all_files.append((fullpath, "task"))

        # some plays have only `roles` instead of `tasks`
        # count this type of playbook files here
        play_specs = scandata.root_definitions.get("definitions", {}).get("plays", [])
        for play_spec in play_specs:
            fullpath = os.path.join(scan_root_dir, play_spec.defined_in)
            if fullpath not in all_files:
                all_files.append((fullpath, "play"))
        return all_files
    
    def save_yml_inventory(self, output_path):
        lines = []
        for project_name in self.project_file_list:
            for file in self.project_file_list[project_name]["files"]:
                task_scanned = file.get("task_scanned", False)
                file["task_scanned"] = task_scanned
                scanned_as = file.get("scanned_as", "")
                file["scanned_as"] = scanned_as
                lines.append(json.dumps(file))

        for role_name in self.role_file_list:
            for file in self.role_file_list[role_name]["files"]:
                task_scanned = file.get("task_scanned", False)
                file["task_scanned"] = task_scanned
                scanned_as = file.get("scanned_as", "")
                file["scanned_as"] = scanned_as
                lines.append(json.dumps(file))

        for file in self.independent_file_list:
            task_scanned = file.get("task_scanned", False)
            file["task_scanned"] = task_scanned
            scanned_as = file.get("scanned_as", "")
            file["scanned_as"] = scanned_as
            lines.append(json.dumps(file))

        out_dir = os.path.dirname(output_path)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        
        with open(output_path, "w") as outfile:
            outfile.write("\n".join(lines))

    def task_context_to_ftdata(self, out_dir):
        prefix = "task_context_data"
        filenames = os.listdir(out_dir)
        ftdata_lines = []
        loaded_task_keys = []
        for filename in filenames:
            if filename.startswith(prefix):
                fpath = os.path.join(out_dir, filename)
                with open(fpath, "r") as file:
                    for line in file:
                        d = json.loads(line)
                        task_key = d.get("ari_task_key", None)
                        if not task_key:
                            continue
                        if task_key in loaded_task_keys:
                            continue
                        ftdata_lines.append(json.dumps(d))
                        loaded_task_keys.append(task_key)
        ftdata_path = os.path.join(out_dir, "ftdata.json")
        with open(ftdata_path, "w") as file:
            file.write("\n".join(ftdata_lines))


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


def extract_directory(file_path):
    directory = os.path.dirname(file_path)
    return directory

def load_json_data(filepath):
    with open(filepath, "r") as file:
        records = file.readlines()
    trains = []
    for record in records:
        train = json.loads(record)
        trains.append(train)
    return trains

def write_result(filepath, results):
    with open(filepath, "w") as file:
        if type(results) == list:
            for result in results:
                json_str = jsonpickle.encode(result, make_refs=False, unpicklable=False)
                file.write(f"{json_str}\n")
        else:
            json_str = jsonpickle.encode(results, make_refs=False, unpicklable=False)
            file.write(f"{json_str}\n")


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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-d", "--dir", help='root direcotry for scan')
    parser.add_argument("--include-tests", action="store_true", help='if true, load test contents in "tests/integration/targets"')
    parser.add_argument("--objects", action="store_true", help="if true, output objects.json to the output directory")
    parser.add_argument("--rule-result", action="store_true", help="if true, output rule_result.json to the output directory")
    parser.add_argument("-r", "--resume", help="line number to resume scanning")
    parser.add_argument("--serial", action="store_true", help="if true, do not parallelize ram generation")
    parser.add_argument("--rule", default="PP004", help="rule id (default to \"PP004\")")
    parser.add_argument("-o", "--out-dir", default="", help="output directory for the rule evaluation result")
    args = parser.parse_args()

    pp = PreProcesser(args=args)

    output_path = os.path.join(args.out_dir, "yml_inventory.json")
    os.environ['SAGE_CONTENT_ANALYSIS_OUT_DIR'] = args.out_dir

    path_list = get_yml_list(args.dir)
    # os.environ['FTDATA_SRC_PATH_LIST'] = os.path.abspath(args.file)
    pp.run(path_list, output_path)
