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

from dataclasses import dataclass, field
import datetime
from ansible_risk_insight.scanner import ARIScanner, config, Config
from ansible_risk_insight.models import NodeResult, RuleResult, AnsibleRunContext, Object
from ansible_risk_insight.finder import (
    find_all_files,
    label_yml_file,
    get_role_info_from_path,
    get_project_info_for_file,
)
from ansible_risk_insight.utils import escape_local_path
from sage_scan.utils import get_rule_id_list, get_git_version
from sage_scan.models import convert_to_sage_obj, SageProject
import os
import time
import traceback
import logging
import threading
import json
import jsonpickle


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

ftdata_rule_dir = os.path.join(os.path.dirname(__file__), "custom_scan/rules")


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
    data: any = None
    metadata: dict = field(default_factory=dict)

    # convert the output data into a json line string
    def serialize(self):
        return jsonpickle.encode(self.data, make_refs=False, separators=(',', ':'))

@dataclass
class SerializableRunContext(object):
    targets: list = field(default_factory=list)
    root_key: str = ""
    parent: Object = None
    scan_metadata: dict = field(default_factory=dict)
    last_item: bool = False

    @classmethod
    def from_ansible_run_context(cls, rc: AnsibleRunContext):
        src = cls()
        src.targets = rc.sequence.items
        src.root_key = rc.root_key
        src.parent = rc.parent
        src.scan_metadata = rc.scan_metadata
        src.last_item = rc.last_item
        return src
    
    def to_ansible_run_context(self):
        rc = AnsibleRunContext.from_targets(
            targets=self.targets,
            root_key=self.root_key,
            parent=self.parent,
            scan_metadata=self.scan_metadata,
            last_item=self.last_item,
        )
        return rc


@dataclass
class SagePipeline(object):
    ari_kb_data_dir: str = ""
    ari_rules_dir: str = ""
    ari_rules: list = field(default_factory=list)

    scanner: ARIScanner = None
    log_level_str: str = ""
    logger: logging.Logger = None
    silent: bool = False

    timeout: float = 0.0

    # whether it scans the failed files later: default to True
    do_multi_stage: bool = True

    # whether it scans the targets in parallel: default to False
    do_parallel: bool = False

    do_save_file_inventory: bool = True
    do_save_findings: bool = False
    do_save_metadata: bool = True
    do_save_objects: bool = True
    do_save_output: bool = False

    use_ftdata_rule: bool = False 

    aggregation_rule_id: str = ""

    ari_out_dir: str = ""
    ari_include_tests: bool = True
    ari_objects: bool = False

    accumulate: bool = False
    scan_records: dict = field(default_factory=dict)

    # special scan records
    file_inventory: list = field(default_factory=list)

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
        _data_dir = self.ari_kb_data_dir
        if not _data_dir:
            if not self.silent:
                self.logger.debug(f"ARI KB data dir is not configured.")
        _rules_dir = self.ari_rules_dir
        _rule_id_list = []
        if self.use_ftdata_rule:
            if not _rules_dir:
                _rules_dir = ftdata_rule_dir
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
            read_ram=False,
            write_ram=False,
            silent=True,
        )
        self.scanner = scanner


    # create a list of InputData to scan
    def to_input(self, **kwargs):
        if isinstance(kwargs, dict) and "target_dir" in kwargs:
            target_dir = kwargs["target_dir"]
            self.scan_records["source"] = kwargs.get("source", {})
            return self._target_dir_to_input(target_dir)
        elif isinstance(kwargs, dict) and "raw_yaml" in kwargs:
            raw_yaml = kwargs["raw_yaml"]
            yaml_label = kwargs.get("yaml_label", "")
            filepath = kwargs.get("filepath", "")
            self.scan_records["single_scan"] = True
            self.scan_records["source"] = kwargs.get("source", {})
            return self._single_yaml_to_input(raw_yaml=raw_yaml, label=yaml_label, filepath=filepath)
        elif isinstance(kwargs, dict) and "ftdata_path" in kwargs:
            ftdata_path = kwargs["ftdata_path"]
            return self._ftdata_to_input(ftdata_path)
        return
    
    # create a list of OutputData to save as a multi-line json file
    def to_output(self, **kwargs):
        if self.accumulate and "output_dir" in kwargs:
            search_dir = kwargs["output_dir"]
            return self._task_context_to_output(search_dir)
        elif isinstance(kwargs, dict) and "from_aggregated_results" in kwargs:
            return self._aggregated_results_to_output()
        # return SageProject by default
        return self._sage_project_to_output()

    def _target_dir_to_input(self, target_dir):
        dir_size = get_dir_size(target_dir)
        path_list = get_yml_list(target_dir)
        project_file_list, role_file_list, independent_file_list, non_yaml_file_list = create_scan_list(path_list)
        # used for detecting missing files at the 1st scan
        self.scan_records["project_file_list"] = project_file_list
        self.scan_records["role_file_list"] = role_file_list
        self.scan_records["independent_file_list"] = independent_file_list
        self.scan_records["non_yaml_file_list"] = non_yaml_file_list
        self.scan_records["non_task_scanned_files"] = []
        self.scan_records["findings"] = []
        self.scan_records["metadata"] = {}
        self.scan_records["time"] = []
        self.scan_records["size"] = dir_size
        self.scan_records["objects"] = []
        self.scan_records["ignored_files"] = []

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

        if not self.silent:
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

    def _single_yaml_to_input(self, raw_yaml, label="", filepath=""):
        if not label:
            label, _, error = label_yml_file(yml_body=raw_yaml)
            if error:
                raise ValueError(f"failed to detect the input YAML type: {error}")
        if label not in ["playbook", "taskfile"]:
            raise ValueError(f"playbook and taskfile are the only supported types, but the input file is `{label}`")
        input_data = InputData(
            index=0,
            total_num=1,
            yaml=raw_yaml,
            path=filepath,
            type=label,
        )
        input_list = [input_data]
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
                if not self.silent:
                    self.logger.warn(f"failed to remove the temporary file \"{fpath}\": {err}")
        return output_list
    
    def _sage_project_to_output(self):
        proj = self._create_sage_project()
        output_data = OutputData(data=proj, metadata={"single_object": True})
        output_list = [output_data]
        return output_list

    # TODO: implement this
    def _aggregated_results_to_output(self):
        pass

    def check_timeout(self):
        limit_seconds = self.timeout
        if limit_seconds <= 0:
            return
        
        now = time.time()
        begin = self.scan_records["begin"]
        if (now - begin) > limit_seconds:
            raise ValueError(f"TimeoutError: this scan took more than {limit_seconds} seconds")

    
    def run(self, **kwargs):
        if not self.silent:
            self.logger.info("Running data pipeline")
        
        self._init_scan_records()

        if isinstance(kwargs, dict) and "timeout" in kwargs:
            self.timeout = kwargs["timeout"]
        
        # By default, three types of input are supported
        #   - target_dir: path to a target directory
        #   - raw_yaml: YAML string of a playbook or a taskfile
        #   - (TODO) ftdata_path: path to a ftdata file
        # You can override `to_input` function to define a customized one
        input_list = self.to_input(**kwargs)
        self.check_timeout()

        # Specify output filepath with the following argument
        #   - output_dir: path to the output directory
        output_dir = ""
        if isinstance(kwargs, dict) and "output_dir" in kwargs:
            output_dir = kwargs["output_dir"]

        if isinstance(kwargs, dict) and "scan_func" in kwargs:
            scan_func = kwargs["scan_func"]
            scan_func(input_list)

        # create file inventory here, but this will be updated after scanning
        self.file_inventory = self.create_file_inventory()

        multi_stage = self.do_multi_stage
        if "single_scan" in self.scan_records and self.scan_records["single_scan"]:
            multi_stage = False
        file_inventory_only = False
        if isinstance(kwargs, dict) and "file_inventory_only" in kwargs:
            file_inventory_only = kwargs["file_inventory_only"]
        if file_inventory_only:
            self.check_timeout()
            if output_dir and self.do_save_file_inventory:
                file_inventory_path = os.path.join(output_dir, "file_inventory.json")
                self.save_file_inventory(file_inventory_path)
                self.check_timeout()
            return

        elif multi_stage:
            self._multi_stage_scan(input_list)
            self.check_timeout()
        else:
            self._single_scan(input_list)
            self.check_timeout()

        if isinstance(kwargs, dict) and "process_fn" in kwargs:
            process_fn = kwargs["process_fn"]
            objects = self.scan_records["objects"]
            objects = process_fn(objects)
            self.scan_records["objects"] = objects
        
        self.file_inventory = self.create_file_inventory()
        if output_dir and self.do_save_file_inventory:
            file_inventory_path = os.path.join(output_dir, "file_inventory.json")
            self.save_file_inventory(file_inventory_path)
            self.check_timeout()

        if output_dir and self.do_save_findings:
            findings_path = os.path.join(output_dir, "findings.json")
            self.save_findings(findings_path)
            self.check_timeout()

        if output_dir and self.do_save_metadata:
            metadata_path = os.path.join(output_dir, "sage-metadata.json")
            self.save_metadata(metadata_path)
            self.check_timeout()

        if output_dir and self.do_save_objects:
            objects_path = os.path.join(output_dir, "sage-objects.json")
            self.save_objects(objects_path)
            self.check_timeout()

        output_list = self.to_output(**kwargs)
        self.check_timeout()
        output_data = None
        if output_list:
            if len(output_list) == 1 and output_list[0].metadata.get("single_object"):
                output_data = output_list[0].data
            else:
                output_data = [od.data for od in output_list if isinstance(od, OutputData)]

        if not self.silent:
            self.logger.info("Done")

        self._clear_scan_records()
        
        return output_data

    # TODO: implement this
    def _single_scan(self, input_list):
        start = time.time()
        # first stage scan; scan the input as project
        for input_data in input_list:
            self.scan(start, input_data)
            self.check_timeout()

        self.check_timeout()
        return

    def _multi_stage_scan(self, input_list):

        start = time.time()
        # first stage scan; scan the input as project
        for input_data in input_list:
            self.scan(start, input_data)
            self.check_timeout()

        # make a list of missing files from the first scan
        missing_files = []
        for project_name in self.scan_records["project_file_list"]:
            base_dir = os.path.abspath(self.scan_records["project_file_list"][project_name]["path"])
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
                    missing_files.append((_type, _name, filepath, base_dir, "project"))
            self.check_timeout()

        for role_name in self.scan_records["role_file_list"]:
            base_dir = os.path.abspath(self.scan_records["role_file_list"][role_name]["path"])
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
                    missing_files.append((_type, _name, filepath, base_dir, "role"))
            self.check_timeout()
        
        self.scan_records["missing_files"] = missing_files
        num_of_missing = len(missing_files)
        second_input_list = [
            InputData(
                index=i,
                total_num=num_of_missing,
                type=_type,
                name=_name,
                path=filepath,
                metadata={"original_type": original_type, "base_dir": base_dir}
            )
            for i, (_type, _name, filepath, base_dir, original_type) in enumerate(missing_files)
        ]
        start = time.time()
        for input_data in second_input_list:
            self.scan(start, input_data)
            self.check_timeout()
        return
    
    def _init_scan_records(self):
        self.scan_records = {
            "project_file_list": {},
            "role_file_list": {},
            "independent_file_list": [],
            "non_yaml_file_list": [],
            "non_task_scanned_files": [],
            "findings": [],
            "metadata": {},
            "time": [],
            "size": 0,
            "objects": [],
            "ignored_files": [],
            "begin": time.time(),
        }
        self.file_inventory = []
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
        raw_yaml = input_data.yaml
        original_type = input_data.metadata.get("original_type", _type)
        base_dir = input_data.metadata.get("base_dir", None)

        kwargs = {
            "type": _type,
        }
        if path:
            kwargs["name"] = path
        if raw_yaml:
            kwargs["raw_yaml"] = raw_yaml
        
        source = self.scan_records.get("source", {})
        display_name = name
        if base_dir and name.startswith(base_dir):
            display_name = name.replace(base_dir, "", 1)
            if display_name and display_name[-1] == "/":
                display_name = display_name[:-1]

        yaml_label_list = []
        if self.file_inventory:
            for file_info in self.file_inventory:
                if not isinstance(file_info, dict):
                    continue
                is_yml = file_info.get("is_yml", False)
                if not is_yml:
                    continue
                fpath = file_info.get("path_from_root", "")
                label = file_info.get("label", "")
                role_info = file_info.get("role_info", {})
                if not fpath or not label:
                    continue
                yaml_label_list.append((fpath, label, role_info))

        start_of_this_scan = time.time()
        thread_id = threading.get_native_id()
        if not self.silent:
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
        elapsed = None
        try:
            include_tests = self.ari_include_tests
            out_dir = ""
            if self.ari_out_dir:
                out_dir = os.path.join(self.ari_out_dir, _type, out_dir_basename)
            objects = False
            if self.ari_objects and out_dir:
                objects = True
            begin = time.time()
            result = self.scanner.evaluate(
                **kwargs,
                install_dependencies=True,
                include_test_contents=include_tests,
                objects=objects,
                out_dir=out_dir,
                load_all_taskfiles=True,
                use_src_cache=use_src_cache,
                taskfile_only=taskfile_only,
                playbook_only=playbook_only,
                base_dir=base_dir,
                yaml_label_list=yaml_label_list,
            )
            elapsed = time.time() - begin
            scandata = self.scanner.get_last_scandata()
        except Exception:
            error = traceback.format_exc()
            if error:
                if not self.silent:
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
            file_scanned_files = [fpath for fpath, scan_type in all_scanned_files if scan_type == "file"]
            found_files = []
            if original_type == "project":
                if name in self.scan_records["project_file_list"]:
                    files_num = len(self.scan_records["project_file_list"][name]["files"])
                    for j in range(files_num):
                        fpath = self.scan_records["project_file_list"][name]["files"][j]["filepath"]
                        if fpath in task_scanned_files:
                            self.scan_records["project_file_list"][name]["files"][j]["task_scanned"] = True
                            self.scan_records["project_file_list"][name]["files"][j]["scanned_as"] = _type
                            self.scan_records["project_file_list"][name]["files"][j]["loaded"] = True
                        elif fpath in play_scanned_files:
                            self.scan_records["project_file_list"][name]["files"][j]["scanned_as"] = _type
                            self.scan_records["project_file_list"][name]["files"][j]["loaded"] = True
                            self.scan_records["non_task_scanned_files"].append(fpath)
                        elif fpath in file_scanned_files:
                            self.scan_records["project_file_list"][name]["files"][j]["scanned_as"] = _type
                            self.scan_records["project_file_list"][name]["files"][j]["loaded"] = True

            elif original_type == "role":
                if name in self.scan_records["role_file_list"]:
                    files_num = len(self.scan_records["role_file_list"][name]["files"])
                    for j in range(files_num):
                        fpath = self.scan_records["role_file_list"][name]["files"][j]["filepath"]
                        if fpath in task_scanned_files:
                            self.scan_records["role_file_list"][name]["files"][j]["task_scanned"] = True
                            self.scan_records["role_file_list"][name]["files"][j]["scanned_as"] = _type
                            self.scan_records["role_file_list"][name]["files"][j]["loaded"] = True
                        elif fpath in play_scanned_files:
                            self.scan_records["role_file_list"][name]["files"][j]["scanned_as"] = _type
                            self.scan_records["role_file_list"][name]["files"][j]["loaded"] = True
                            self.scan_records["non_task_scanned_files"].append(fpath)
            else:
                files_num = len(self.scan_records["independent_file_list"])
                for j in range(files_num):
                    fpath = self.scan_records["independent_file_list"][j]["filepath"]
                    if fpath in task_scanned_files:
                        self.scan_records["independent_file_list"][j]["task_scanned"] = True
                        self.scan_records["independent_file_list"][j]["scanned_as"] = _type
                        self.scan_records["independent_file_list"][j]["loaded"] = True
                    elif fpath in play_scanned_files:
                        self.scan_records["independent_file_list"][j]["scanned_as"] = _type
                        self.scan_records["independent_file_list"][j]["loaded"] = True
                        self.scan_records["non_task_scanned_files"].append(fpath)

            findings = scandata.findings
            self.scan_records["findings"].append({"target_type": _type, "target_name": name, "findings": findings})

            trees = scandata.trees
            annotation_dict = {}
            skip_annotation_keys = [
                "",
                "module.available_args",
                "variable.unnecessary_loop_vars",
            ]
            for _tree in trees:
                for call_obj in _tree.items:
                    if not hasattr(call_obj, "annotations"):
                        continue
                    orig_annotations = call_obj.annotations
                    annotations = {anno.key: anno.value for anno in orig_annotations if isinstance(anno.key, str) and anno.key not in skip_annotation_keys}
                    spec_key = call_obj.spec.key
                    if annotations:
                        annotation_dict[spec_key] = annotations

            ari_objects = {}
            tasks = []
            plays = []
            if findings and findings.root_definitions:
                ari_objects = findings.root_definitions.get("definitions", {})
                tasks = ari_objects["tasks"]
                plays = ari_objects["plays"]
            
            added_obj_keys = []
            for obj_type in ari_objects:
                ari_objects_per_type = ari_objects[obj_type]
                for ari_obj in ari_objects_per_type:

                    # filter files to avoid too many files in sage-objects
                    if obj_type == "files":
                        if is_skip_file_obj(ari_obj, tasks, plays):
                            self.scan_records["ignored_files"].append(ari_obj.defined_in)
                            continue

                    ari_spec_key = ari_obj.key
                    if ari_spec_key in added_obj_keys:
                        continue
                    
                    sage_obj = convert_to_sage_obj(ari_obj, source)
                    if source:
                        sage_obj.set_source(source)
                    if ari_spec_key in annotation_dict:
                        sage_obj.annotations = annotation_dict[ari_spec_key]
                    self.scan_records["objects"].append(sage_obj)
                    added_obj_keys.append(ari_spec_key)

            self.scan_records["time"].append({"target_type": _type, "target_name": name, "scan_seconds": elapsed})

            if findings and _type == "project":
                metadata = findings.metadata.copy()
                metadata.pop("time_records")
                metadata["scan_timestamp"] = datetime.datetime.utcnow().isoformat(timespec="seconds")
                metadata["pipeline_version"] = get_git_version()
                self.scan_records["metadata"] = metadata

                ari_metadata = findings.metadata.copy()
                dependencies = findings.dependencies.copy()
                self.scan_records["ari_metadata"] = ari_metadata
                self.scan_records["dependencies"] = dependencies

        elapsed_for_this_scan = round(time.time() - start_of_this_scan, 2)
        if elapsed_for_this_scan > 60:
            if not self.silent:
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

        file_specs = scandata.root_definitions.get("definitions", {}).get("files", [])
        for file_spec in file_specs:
            fullpath = os.path.join(scan_root_dir, file_spec.defined_in)
            if fullpath not in all_files:
                all_files.append((fullpath, "file"))
        return all_files
    
    def create_file_inventory(self):
        file_inventory = []
        for project_name in self.scan_records["project_file_list"]:
            for file in self.scan_records["project_file_list"][project_name]["files"]:
                task_scanned = file.get("task_scanned", False)
                file["task_scanned"] = task_scanned
                scanned_as = file.get("scanned_as", "")
                file["scanned_as"] = scanned_as
                loaded = file.get("loaded", False)
                # we intentionally remove some files by is_skip_file_obj() in the current implementation
                # so set loaded=False here in that case
                if loaded:
                    in_proj_path = file.get("path_from_root", "")
                    if in_proj_path and in_proj_path in self.scan_records["ignored_files"]:
                        loaded = False
                file["loaded"] = loaded
                file_inventory.append(file)

        for role_name in self.scan_records["role_file_list"]:
            for file in self.scan_records["role_file_list"][role_name]["files"]:
                task_scanned = file.get("task_scanned", False)
                file["task_scanned"] = task_scanned
                scanned_as = file.get("scanned_as", "")
                file["scanned_as"] = scanned_as
                loaded = file.get("loaded", False)
                # we intentionally remove some files by is_skip_file_obj() in the current implementation
                # so set loaded=False here in that case
                if loaded:
                    in_proj_path = file.get("path_from_root", "")
                    if in_proj_path and in_proj_path in self.scan_records["ignored_files"]:
                        loaded = False
                file["loaded"] = loaded
                file_inventory.append(file)

        for file in self.scan_records["independent_file_list"]:
            task_scanned = file.get("task_scanned", False)
            file["task_scanned"] = task_scanned
            scanned_as = file.get("scanned_as", "")
            file["scanned_as"] = scanned_as
            loaded = file.get("loaded", False)
            # we intentionally remove some files by is_skip_file_obj() in the current implementation
            # so set loaded=False here in that case
            if loaded:
                in_proj_path = file.get("path_from_root", "")
                if in_proj_path and in_proj_path in self.scan_records["ignored_files"]:
                    loaded = False
            file["loaded"] = loaded
            file_inventory.append(file)

        for file in self.scan_records["non_yaml_file_list"]:
            task_scanned = file.get("task_scanned", False)
            file["task_scanned"] = task_scanned
            scanned_as = file.get("scanned_as", "")
            file["scanned_as"] = scanned_as
            loaded = file.get("loaded", False)
            # we intentionally remove some files by is_skip_file_obj() in the current implementation
            # so set loaded=False here in that case
            if loaded:
                in_proj_path = file.get("path_from_root", "")
                if in_proj_path and in_proj_path in self.scan_records["ignored_files"]:
                    loaded = False
            file["loaded"] = loaded
            file_inventory.append(file)
        
        return file_inventory

    def save_file_inventory(self, output_path):
        lines = [json.dumps(file) + "\n" for file in self.file_inventory]

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

    def _create_sage_project(self):
        if not self.scan_records:
            return
        source = self.scan_records.get("source", {})
        file_inventory = self.file_inventory
        objects = self.scan_records.get("objects", [])
        metadata = self.scan_records.get("metadata", {})
        scan_time = self.scan_records.get("time", [])
        dir_size = self.scan_records.get("size", 0)
        ari_metadata = self.scan_records.get("ari_metadata", {})
        dependencies = self.scan_records.get("dependencies", [])
        proj = SageProject.from_source_objects(
            source=source,
            file_inventory=file_inventory,
            objects=objects,
            metadata=metadata,
            scan_time=scan_time,
            dir_size=dir_size,
            ari_metadata=ari_metadata,
            dependencies=dependencies,
        )
        return proj

    def save_metadata(self, output_path):
        if not self.scan_records:
            return
        if "metadata" not in self.scan_records:
            return
        
        proj = self._create_sage_project()        
        proj_metadata = proj.metadata()
        
        out_dir = os.path.dirname(output_path)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        with open(output_path, "w") as outfile:
            outfile.write(jsonpickle.encode(proj_metadata, make_refs=False, separators=(',', ':')))

    def save_objects(self, output_path):
        if not self.scan_records:
            return
        if "objects" not in self.scan_records:
            return
        
        objects = self.scan_records["objects"]
        lines = []
        for obj in objects:
            obj_json = jsonpickle.encode(obj, make_refs=False, separators=(',', ':'))
            lines.append(obj_json + "\n")
        
        out_dir = os.path.dirname(output_path)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        with open(output_path, "w") as outfile:
            outfile.write("".join(lines))


def get_yml_label(file_path, root_path):
    if root_path and root_path[-1] == "/":
        root_path = root_path[:-1]
    
    relative_path = file_path.replace(root_path, "")
    if relative_path[-1] == "/":
        relative_path = relative_path[:-1]
    
    label, name_count, error = label_yml_file(yml_path=file_path)
    role_name, role_path = get_role_info_from_path(file_path)
    role_info = None
    if role_name and role_path:
        relative_role_path = role_path.replace(root_path, "")
        if relative_role_path and relative_role_path[0] == "/":
            relative_role_path = relative_role_path[1:]
        role_info = {"name": role_name, "path": role_path, "relative_path": relative_role_path}

    project_name, project_path = get_project_info_for_file(file_path, root_path)
    project_info = None
    if project_name and project_path:
        project_info = {"name": project_name, "path": project_path}
    
    # print(f"[{label}] {relative_path} {role_info}")
    if error:
        logger.debug(f"failed to get yml label:\n {error}")
        label = "error"
    return label, role_info, project_info, name_count, error


def get_yml_list(root_dir: str):
    found_files = find_all_files(root_dir)
    all_files = []
    for filepath in found_files:
        ext = os.path.splitext(filepath)[1]
        # YAML file
        if ext and ext.lower() in [".yml", ".yaml"]:
            yml_path = filepath
            label, role_info, project_info, name_count, error = get_yml_label(yml_path, root_dir)
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
                "ext": ext,
                "is_yml": True,
                "role_info": role_info,
                "project_info": project_info,
                "in_role": in_role,
                "in_project": in_project,
                "name_count": name_count,
                "error": error,
            })
        else:
            # non YAML file
            all_files.append({
                "filepath": filepath,
                "path_from_root": filepath.replace(root_dir, "").lstrip("/"),
                "label": "others",
                "ext": ext,
                "is_yml": False,
                "role_info": None,
                "project_info": None,
                "in_role": False,
                "in_project": False,
                "name_count": -1,
                "error": None,
            })
    return all_files


def create_scan_list(file_inventory):
    role_file_list = {}
    project_file_list = {}
    independent_file_list = []
    non_yaml_file_list = []
    for file_data in file_inventory:
        filepath = file_data["filepath"]
        path_from_root = file_data["path_from_root"]
        ext = file_data["ext"]
        is_yml = file_data["is_yml"]
        label = file_data["label"]
        role_info = file_data["role_info"]
        in_role = file_data["in_role"]
        project_info = file_data["project_info"]
        in_project = file_data["in_project"]
        name_count = file_data["name_count"]
        error = file_data["error"]
        if is_yml:
            if project_info:
                p_name = project_info.get("name", "")
                p_path = project_info.get("path", "")
                if p_name not in project_file_list:
                    project_file_list[p_name] = {"path": p_path, "files": []}
                project_file_list[p_name]["files"].append({
                    "filepath": filepath,
                    "path_from_root": path_from_root,
                    "ext": ext,
                    "is_yml": is_yml,
                    "label": label,
                    "project_info": project_info,
                    "role_info": role_info,
                    "in_project": in_project,
                    "in_role": in_role,
                    "name_count": name_count,
                    "error": error,
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
                    "ext": ext,
                    "is_yml": is_yml,
                    "label": label,
                    "project_info": project_info,
                    "role_info": role_info,
                    "in_project": in_project,
                    "in_role": in_role,
                    "name_count": name_count,
                    "error": error,
                })
            else:
                independent_file_list.append({
                    "filepath": filepath,
                    "path_from_root": path_from_root,
                    "ext": ext,
                    "is_yml": is_yml,
                    "label": label,
                    "project_info": project_info,
                    "role_info": role_info,
                    "in_project": in_project,
                    "in_role": in_role,
                    "name_count": name_count,
                    "error": error,
                })
        else:
            non_yaml_file_list.append({
                "filepath": filepath,
                "path_from_root": path_from_root,
                "ext": ext,
                "is_yml": is_yml,
                "label": label,
                "project_info": project_info,
                "role_info": role_info,
                "in_project": in_project,
                "in_role": in_role,
                "name_count": name_count,
                "error": error,
            })
    return project_file_list, role_file_list, independent_file_list, non_yaml_file_list


def get_dir_size(path=""):
    total = 0
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False):
                total += get_dir_size(entry.path)
    return total


# NOTE: currently we keep just files that are obviously for vars with a certain path
#       and vars files that are explicitly used in some tasks; other types of files will be skipped
def is_skip_file_obj(obj, tasks=[], plays=[]):
    if not obj or getattr(obj, "type", "") != "file":
        return True
    
    fpath = getattr(obj, "defined_in") or getattr(obj, "filepath")
    if not fpath:
        return True
    
    vars_file_patterns = [
        "vars/main.yml",
        "vars/main.yaml",
        "defaults/main.yml",
        "defaults/main.yaml",
    ]
    # check if the filepath is one of role vars files
    for p in vars_file_patterns:
        if p in fpath:
            return False
    
    # check if the filepath is likely called from known tasks
    for t in tasks:
        module = getattr(t, "module")
        short_module = module.split(".")[-1]
        if short_module != "include_vars":
            continue
        mo = getattr(t, "module_options")
        
        vars_file_ref_list = []
        loop_info = getattr(t, "loop")
        if loop_info and isinstance(loop_info, dict):
            for loop_var in loop_info:
                loop_items = loop_info[loop_var]
                if isinstance(loop_items, list):
                    for v in loop_items:
                        if isinstance(v, str):
                            vars_file_ref_list.append(v)
                        elif isinstance(v, dict):
                            # `with_first_found` case
                            if "files" in v:
                                vars_file_ref_list.extend(v["files"])
        else:
            vars_file_ref = ""
            if isinstance(mo, str):
                vars_file_ref = mo
            elif isinstance(mo, dict):
                vars_file_ref = mo.get("file", "")
            if vars_file_ref:
                vars_file_ref_list.append(vars_file_ref)
        if not vars_file_ref_list:
            continue
        
        for vars_file_ref in vars_file_ref_list:
            basename = vars_file_ref.split("/")[-1]
            if basename in fpath:
                return False
        
    for p in plays:
        vars_files = getattr(p, "vars_files")
        for vars_file in vars_files:
            basename = vars_file.split("/")[-1]
            if basename in fpath:
                return False
        
    return  True


