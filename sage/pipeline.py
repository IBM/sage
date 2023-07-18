from dataclasses import dataclass, field
from ansible_risk_insight.scanner import ARIScanner, config, Config
from ansible_risk_insight.models import NodeResult, RuleResult
from ansible_risk_insight.finder import (
    find_all_ymls,
    label_yml_file,
    get_role_info_from_path,
    get_project_info_for_file,
)
from ansible_risk_insight.utils import escape_local_path
from sage.utils import get_rule_id_list
import os
import time
import traceback
import logging
import threading
import json


logging.basicConfig()
logger = logging.getLogger("pipeline")
log_level_str = os.getenv("SAGE_LOG_LEVEL", "info")
log_level_map = {
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}
log_level = log_level_map.get(log_level_str, None)
if log_level is None:
    logger.warn(f"logging level \"{log_level_str}\" is not supported. Set to \"info\" instead.")
    log_level = logging.INFO
logger.setLevel(log_level)

ari_kb_dir = os.getenv("ARI_KB_DIR", None)
ari_kb_data_dir = ""
ari_rules_dir = ""
if ari_kb_dir and \
    os.path.exists(ari_kb_dir) and \
    os.path.exists(os.path.join(ari_kb_dir, "data")) and \
    os.path.exists(os.path.join(ari_kb_dir, "rules")):

    ari_kb_data_dir = os.path.join(ari_kb_dir, "data")
    ari_kb_rule_dir = os.path.join(ari_kb_dir, "rules")

else:
    ari_kb_data_dir = os.getenv("ARI_KB_DATA_DIR", "")
    ari_rules_dir = os.getenv("ARI_RULES_DIR", "")


@dataclass
class InputData:
    index: int = 0
    total_num: int = 0
    type: str = ""
    name: str = ""
    path: str = ""
    yaml: str = ""
    metadata: dict = field(default_factory=dict)

@dataclass
class OutputData:
    input: InputData = field(default_factory=InputData)
    data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    # convert the output data into a json line string
    def serialize(self):
        return json.dumps(self.data)


@dataclass
class SagePipeline(object):
    ari_kb_data_dir: str = ""
    ari_rules_dir: str = ""
    ari_rules: list = field(default_factory=list)

    scanner: ARIScanner = None
    log_level_str: str = ""
    logger: logging.Logger = None

    # whether it scans the failed files later: default to True
    do_multi_stage: bool = True

    # whether it scans the targets in parallel: default to False
    do_parallel: bool = False

    do_save_yml_inventory: bool = True
    do_save_unique_tasks: bool = True
    do_save_findings: bool = True

    aggregation_rule_id: str = ""

    ari_out_dir: str = ""
    ari_include_tests: bool = True
    ari_objects: bool = False

    accumulate: bool = True
    scan_records: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.logger:
            self.init_logger()

        if not self.scanner:
            self.init_scanner()

    def init_logger(self):
        global logger
        _level_str = self.log_level_str or log_level_str
        _level = log_level_map.get(_level_str, logging.INFO)
        logger.setLevel(_level)
        self.logger = logger

    def init_scanner(self):
        _data_dir = self.ari_kb_data_dir or ari_kb_data_dir
        if not _data_dir:
            self.logger.warn(f"ARI KB dir is empty. ARI is running with very limited knowledge base data.")
        _rules_dir = self.ari_rules_dir or ari_rules_dir
        _rule_id_list = get_rule_id_list(_rules_dir)
        _rules = []
        if self.ari_rules:
            _rules = self.ari_rules
        else:
            _rules = ["P001", "P002", "P003", "P004"] + _rule_id_list
            self.ari_rules = _rules
            self.aggregation_rule_id = _rules[0] if _rules else ""
        scanner = ARIScanner(
            config=Config(
                data_dir=_data_dir,
                rules_dir=_rules_dir,
                rules=_rules,
                log_level=self.log_level_str,
            ),
            silent=True,
        )
        self.scanner = scanner


    # create a list of InputData to scan
    def to_input(self, **kwargs):
        if isinstance(kwargs, dict) and "target_dir" in kwargs:
            target_dir = kwargs["target_dir"]
            return self._target_dir_to_input(target_dir)
        elif isinstance(kwargs, dict) and "ftdata_path" in kwargs:
            ftdata_path = kwargs["ftdata_path"]
            return self._ftdata_to_input(ftdata_path)
        return
    
    # create a list of OutputData to save as a multi-line json file
    def to_output(self, **kwargs):
        if self.accumulate and "output_dir" in kwargs:
            search_dir = kwargs["output_dir"]
            return self._task_context_to_output(search_dir)
        elif isinstance(kwargs, dict) and kwargs.get("from_aggregated_results") in kwargs:
            return self._aggregated_results_to_output()
        return

    def _target_dir_to_input(self, target_dir):
        path_list = get_yml_list(target_dir)
        project_file_list, role_file_list, independent_file_list = create_scan_list(path_list)
        # used for detecting missing files at the 1st scan
        self.scan_records["project_file_list"] = project_file_list
        self.scan_records["role_file_list"] = role_file_list
        self.scan_records["independent_file_list"] = independent_file_list
        self.scan_records["non_task_scanned_files"] = []
        self.scan_records["findings"] = []

        num = len(project_file_list) + len(role_file_list) + len(independent_file_list)
        target_counts = []
        if project_file_list:
            target_counts.append(f"{len(project_file_list)} projects")
        if role_file_list:
            target_counts.append(f"{len(role_file_list)} roles")
        if independent_file_list:
            target_counts.append(f"{len(independent_file_list)} playbooks/taskfiles")
        target_str = ", ".join(target_counts)
        total_str = f"(total {len(path_list)} files)"

        self.logger.info(f"Start scanning for {target_str} {total_str}")

        input_list = []

        i = 0
        for project_name in project_file_list:
            project_path = project_file_list[project_name].get("path")
            input_list.append(InputData(
                index=i,
                total_num=num,
                type="project",
                name=project_name,
                path=project_path,
                metadata={
                    "base_dir": project_path,
                }
            ))
            i += 1

        for role_name in role_file_list:
            _type = "role"
            _name = role_name
            role_path = role_file_list[role_name].get("path")
            input_list.append(InputData(
                index=i,
                total_num=num,
                type="role",
                name=role_name,
                path=role_path,
                metadata={
                    "base_dir": role_path,
                }
            ))
            i += 1

        for file in independent_file_list:
            _name = file.get("filepath")
            filepath = _name
            _type = file.get("label")
            if _type in ["playbook", "taskfile"]:
                input_list.append(InputData(
                index=i,
                total_num=num,
                type=_type,
                name=_name,
                path=filepath,
                metadata={
                    "base_dir": target_dir,
                }
            ))
            i += 1

        return input_list
    
    # TODO: implement this
    def _ftdata_to_input(self, ftdata_path):
        pass

    def _task_context_to_output(self, search_dir):
        if search_dir is None:
            return []

        prefix = "task_context_data"
        filenames = os.listdir(search_dir)
        output_list = []
        loaded_task_keys = []
        used_task_context_files = []
        for filename in filenames:
            if filename.startswith(prefix):
                fpath = os.path.join(search_dir, filename)
                with open(fpath, "r") as file:
                    for line in file:
                        d = json.loads(line)
                        task_key = d.get("ari_task_key", None)
                        scan_path = d.get("scan_path", None)
                        uniq_task_key = f"{scan_path}-{task_key}"
                        if uniq_task_key in loaded_task_keys:
                            continue
                        if task_key in loaded_task_keys:
                            continue
                        output_data = OutputData(data=d)
                        output_list.append(output_data)
                        loaded_task_keys.append(uniq_task_key)
                used_task_context_files.append(fpath)
        for fpath in used_task_context_files:
            if not fpath:
                continue
            try:
                os.remove(fpath)
            except Exception:
                err = traceback.format_exc()
                self.logger.warn(f"failed to remove the temporary file \"{fpath}\": {err}")
        return output_list

    # TODO: implement this
    def _aggregated_results_to_output(self):
        pass

    
    def run(self, **kwargs):
        self.logger.info("Running data pipeline")
        
        self._init_scan_records()
        
        # By default, two types of input are supported
        #   - target_dir: path to a target directory
        #   - ftdata_path: path to a ftdata file
        # You can override `to_input` function to define a customized one
        input_list = self.to_input(**kwargs)

        # Specify output filepath with the following argument
        #   - output_dir: path to the output directory
        output_dir = ""
        if isinstance(kwargs, dict) and "output_dir" in kwargs:
            output_dir = kwargs["output_dir"]

        if isinstance(kwargs, dict) and "scan_func" in kwargs:
            scan_func = kwargs["scan_func"]
            scan_func(input_list)
        elif self.do_multi_stage:
            self._multi_stage_scan(input_list)
        else:
            self._single_scan(input_list)
        
        if output_dir and self.do_save_yml_inventory:
            yml_inventory_path = os.path.join(output_dir, "yml_inventory.json")
            self.save_yml_inventory(yml_inventory_path)

        if output_dir and self.do_save_findings:
            findings_path = os.path.join(output_dir, "findings.json")
            self.save_findings(findings_path)

        self._clear_scan_records()

        output_list = self.to_output(**kwargs)

        if output_dir:
            output_path = os.path.join(output_dir, "ftdata.json")
            self.save(output_list, output_path)

        self.logger.info("Done")

    # TODO: implement this
    def _single_scan(self):
        return

    def _multi_stage_scan(self, input_list):

        start = time.time()
        # first stage scan; scan the input as project
        for input_data in input_list:
            self.scan(start, input_data)

        # make a list of missing files from the first scan
        missing_files = []
        for project_name in self.scan_records["project_file_list"]:
            for file in self.scan_records["project_file_list"][project_name]["files"]:
                label = file.get("label", "")
                filepath = file.get("filepath", "")
                task_scanned = file.get("task_scanned", False)
                role_info = file.get("role_info", {})
                non_task_scanned = True if filepath in self.scan_records["non_task_scanned_files"] else False
                if not task_scanned and not non_task_scanned and label in ["playbook", "taskfile"]:
                    if role_info and role_info.get("is_external_dependency", False):
                        continue
                    _type = label
                    _name = filepath
                    missing_files.append((_type, _name, filepath, "project"))

        for role_name in self.scan_records["role_file_list"]:
            for file in self.scan_records["role_file_list"][role_name]["files"]:
                label = file.get("label", "")
                filepath = file.get("filepath", "")
                task_scanned = file.get("task_scanned", False)
                role_info = file.get("role_info", {})
                non_task_scanned = True if filepath in self.scan_records["non_task_scanned_files"] else False
                if not task_scanned and not non_task_scanned and label in ["playbook", "taskfile"]:
                    if role_info and role_info.get("is_external_dependency", False):
                        continue
                    _type = label
                    _name = filepath
                    missing_files.append((_type, _name, filepath, "role"))
        
        self.scan_records["missing_files"] = missing_files
        num_of_missing = len(missing_files)
        second_input_list = [
            InputData(
                index=i,
                total_num=num_of_missing,
                type=_type,
                name=_name,
                path=filepath,
                metadata={"original_type": original_type}
            )
            for i, (_type, _name, filepath, original_type) in enumerate(missing_files)
        ]
        start = time.time()
        for input_data in second_input_list:
            self.scan(start, input_data)
        return
    
    def _init_scan_records(self):
        self.scan_records = {
            "project_file_list": {},
            "role_file_list": {},
            "independent_file_list": [],
            "non_task_scanned_files": [],
        }
        return
    
    def _clear_scan_records(self):
        self.scan_records = {}
        return
    
    def scan(self, start, input_data):
        if not isinstance(input_data, InputData):
            raise ValueError(f"input data must be InputData type, but {type(input_data)}")         
        
        i = input_data.index
        num = input_data.total_num
        _type = input_data.type
        name = input_data.name
        path = input_data.path
        original_type = input_data.metadata.get("original_type", _type)
        base_dir = input_data.metadata.get("base_dir", None)
        display_name = name
        if base_dir and name.startswith(base_dir):
            display_name = name.replace(base_dir, "", 1)
            if display_name and display_name[-1] == "/":
                display_name = display_name[:-1]

        start_of_this_scan = time.time()
        thread_id = threading.get_native_id()
        self.logger.debug(f"[{i+1}/{num}] start {_type} {display_name}")
        use_src_cache = True

        taskfile_only = False
        playbook_only = False
        out_dir_basename = name
        if _type != "role" and _type != "project":
            taskfile_only = True
            playbook_only = True
            out_dir_basename = escape_local_path(name)

        result = None
        scandata = None
        try:
            include_tests = self.ari_include_tests
            out_dir = ""
            if self.ari_out_dir:
                out_dir = os.path.join(self.ari_out_dir, _type, out_dir_basename)
            objects = False
            if self.ari_objects and out_dir:
                objects = True
            result = self.scanner.evaluate(
                type=_type,
                name=path,
                install_dependencies=True,
                include_test_contents=include_tests,
                objects=objects,
                out_dir=out_dir,
                load_all_taskfiles=True,
                use_src_cache=use_src_cache,
                taskfile_only=taskfile_only,
                playbook_only=playbook_only
            )
            scandata = self.scanner.get_last_scandata()
        except Exception:
            error = traceback.format_exc()
            self.scanner.save_error(error)
            if error:
                self.logger.error(f"Failed to scan {path} in {name}: error detail: {error}")

        if result:
            for target_result in result.targets:
                for node_result in target_result.nodes:
                    if not node_result:
                        continue
                    if not isinstance(node_result, NodeResult):
                        raise ValueError(f"node_result must be a NodeResult instance, but {type(node_result)}")
                    rule_result = node_result.find_result(self.aggregation_rule_id)
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
                if name in self.scan_records["project_file_list"]:
                    files_num = len(self.scan_records["project_file_list"][name]["files"])
                    for j in range(files_num):
                        fpath = self.scan_records["project_file_list"][name]["files"][j]["filepath"]
                        if fpath in task_scanned_files:
                            self.scan_records["project_file_list"][name]["files"][j]["task_scanned"] = True
                            self.scan_records["project_file_list"][name]["files"][j]["scanned_as"] = _type
                        elif fpath in play_scanned_files:
                            self.scan_records["project_file_list"][name]["files"][j]["scanned_as"] = _type
                            self.scan_records["non_task_scanned_files"].append(fpath)

            elif original_type == "role":
                if name in self.scan_records["role_file_list"]:
                    files_num = len(self.scan_records["role_file_list"][name]["files"])
                    for j in range(files_num):
                        fpath = self.scan_records["role_file_list"][name]["files"][j]["filepath"]
                        if fpath in task_scanned_files:
                            self.scan_records["role_file_list"][name]["files"][j]["task_scanned"] = True
                            self.scan_records["role_file_list"][name]["files"][j]["scanned_as"] = _type
                        elif fpath in play_scanned_files:
                            self.scan_records["role_file_list"][name]["files"][j]["scanned_as"] = _type
                            self.scan_records["non_task_scanned_files"].append(fpath)
            else:
                files_num = len(self.scan_records["independent_file_list"])
                for j in range(files_num):
                    fpath = self.scan_records["independent_file_list"][j]["filepath"]
                    if fpath in task_scanned_files:
                        self.scan_records["independent_file_list"][j]["task_scanned"] = True
                        self.scan_records["independent_file_list"][j]["scanned_as"] = _type
                    elif fpath in play_scanned_files:
                        self.scan_records["independent_file_list"][j]["scanned_as"] = _type
                        self.scan_records["non_task_scanned_files"].append(fpath)

            findings = scandata.findings
            self.scan_records["findings"].append({"target_type": _type, "target_name": name, "findings": findings})

        elapsed_for_this_scan = round(time.time() - start_of_this_scan, 2)
        if elapsed_for_this_scan > 60:
            self.logger.warn(f"It took {elapsed_for_this_scan} sec. to process [{i+1}/{num}] {_type} {name}")


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
        for project_name in self.scan_records["project_file_list"]:
            for file in self.scan_records["project_file_list"][project_name]["files"]:
                task_scanned = file.get("task_scanned", False)
                file["task_scanned"] = task_scanned
                scanned_as = file.get("scanned_as", "")
                file["scanned_as"] = scanned_as
                lines.append(json.dumps(file) + "\n")

        for role_name in self.scan_records["role_file_list"]:
            for file in self.scan_records["role_file_list"][role_name]["files"]:
                task_scanned = file.get("task_scanned", False)
                file["task_scanned"] = task_scanned
                scanned_as = file.get("scanned_as", "")
                file["scanned_as"] = scanned_as
                lines.append(json.dumps(file) + "\n")

        for file in self.scan_records["independent_file_list"]:
            task_scanned = file.get("task_scanned", False)
            file["task_scanned"] = task_scanned
            scanned_as = file.get("scanned_as", "")
            file["scanned_as"] = scanned_as
            lines.append(json.dumps(file) + "\n")

        out_dir = os.path.dirname(output_path)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        
        with open(output_path, "w") as outfile:
            outfile.write("".join(lines))

    def save_findings(self, output_path):
        if not self.scan_records:
            return
        if "findings" not in self.scan_records:
            return
        
        findings_list = self.scan_records["findings"]
        lines = []
        for d in findings_list:
            findings = d["findings"]
            findings_json_str = findings.dump()
            lines.append(findings_json_str + "\n")
        
        out_dir = os.path.dirname(output_path)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        with open(output_path, "w") as outfile:
            outfile.write("".join(lines))

    def save(self, output_list, filepath):
        if not filepath:
            return
        
        dir_path = os.path.dirname(filepath)
        os.makedirs(dir_path, exist_ok=True)

        lines = []
        for od in output_list:
            line = od.serialize()
            lines.append(line + "\n")
        with open(filepath, "w") as file:
            file.write("".join(lines))

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
        logger.debug(f"failed to get yml label:\n {error}")
        label = "error"
    return label, role_info, project_info


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
