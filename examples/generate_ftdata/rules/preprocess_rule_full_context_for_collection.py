import json
import jsonpickle
import threading
from datetime import date, time
from dataclasses import dataclass, field

from ansible_risk_insight.models import (
    AnsibleRunContext,
    RunTargetType,
    Rule,
    RuleResult,
    Severity,
    Collection,
    Role,
    Playbook,
    TaskFile,
    Task,
    VariableType,
)
import os
import re


thread_id = threading.get_native_id()
default_filepath = f"/tmp/ftdata/ftdata_{thread_id}.json"


def find_repo_info(ctx: AnsibleRunContext):
    repo_name = ""
    license = ""
    source = ""

    # `parent` is collection or role (or repository?)
    parent = ctx.parent

    if isinstance(parent, Collection):
        collection = parent
        repo_name = collection.name
        license = collection.metadata.get("collection_info", {}).get("license", "")
        # if the license is object, serialize it in json
        if license and not isinstance(license, str):
            license = json.dumps(license)
        if not license:
            # use first line in the license file as a license string
            license_file_contents = collection.metadata.get("_ari_added", {}).get("license_file_contents_head", "")
            if license_file_contents:
                lines = [line.strip() for line in license_file_contents.splitlines() if line.strip() != ""]
                if len(lines) >= 1:
                    license = lines[0]
        
        if not license:
            # try `license_file` if all the candidates above did not work
            license = parent.metadata.get("collection_info", {}).get("license_file", "")

    elif isinstance(parent, Role):
        role = parent
        license = role.metadata.get("galaxy_info", {}).get("license", "")
        repo_name = role.fqcn

    return repo_name, license, source  


def make_sequence(ctx: AnsibleRunContext, current_depth, current_id) -> list:
    wisdom_sequence = []
    for node in ctx:
        if node.type == "taskcall" and node.get_annotation("module.correct_fqcn", "").endswith("assert"):
            continue
        skip = True
        if node.depth < current_depth:
            if current_id.startswith(node.node_id):  # 0.1
                skip = False
        elif node.depth == current_depth:
            sid = str(node.node_id)
            scid = str(current_id)
            if sid[:-1] == scid[:-1] and int(sid[-1]) < int(scid[-1]):
                skip = False

        if skip:
            continue

        node_data = {}
        node_data["type"] = getattr(node.spec, "type", "")
        node_data["name"] = getattr(node.spec, "name", "")
        node_data["node_id"] = getattr(node, "node_id", "")

        if node.type == RunTargetType.Role:
            rolecall = node
            node_data["name"] = rolecall.spec.name
            node_data["spec"] = rolecall.spec
        elif node.type == RunTargetType.TaskFile:
            pass
        elif node.type == RunTargetType.Task:
            taskcall = node
            node_data["spec"] = taskcall.spec
        wisdom_sequence.append(node_data)
    return wisdom_sequence


def make_yaml_before_task(ctx: AnsibleRunContext, task: Task) -> list:
    yaml_before_task = ""
    filepath_of_this_task = task.defined_in
    for node in ctx:
        if not isinstance(node.spec, Playbook) and not isinstance(node.spec, TaskFile):
            continue
        if node.spec.defined_in != filepath_of_this_task:
            continue

        file_obj = node.spec
        if not hasattr(file_obj, "yaml_lines"):
            # if the file does not have `yaml_lines`, give up here
            break
        
        if not task.line_num_in_file or len(task.line_num_in_file) != 2:
            # if the task does not have `line_num_in_file`, give up here
            break

        # the num of line where the task starts
        task_line_num = task.line_num_in_file[0]

        lines = file_obj.yaml_lines.splitlines()
        if len(lines) < task_line_num:
            # if file lines are less than the task_line_num, give up here
            break

        yaml_before_task = "\n".join(lines[:task_line_num-1])
        break
    return yaml_before_task

def get_variables(task):
    all_vars = {}
    for var_name in task.variable_set:
        var_object = task.variable_set[var_name][-1]
        var_name == var_object.name
        var_value = var_object.value
        if var_object.type == VariableType.RegisteredVars:
            var_value = None
        all_vars[var_name] = var_value
        for e in var_object.elements:
            if e not in all_vars:
                all_vars[e] = None
    return all_vars

@dataclass
class PreProcessingRule(Rule):
    rule_id: str = "PP004"
    description: str = "get a task list including all context information"
    enabled: bool = True
    name: str = "GetFullContext"
    version: str = "v0.0.1"
    severity: Severity = Severity.NONE
    tags: tuple = ("wisdom")
    precedence: int = 1

    license_whitelist: list = field(default_factory=list)
    license_blacklist: list = field(default_factory=list)
    license_nillist: list = field(default_factory=list)

    _char_remove_list: tuple = ("[","]","'",'"','(',')')

    save_filepath: str = default_filepath
    data_buffer: list = field(default_factory=list)
    buffer_size: int = 1000
    
    def __post_init__(self):

        self.license_whitelist = self.load_license_list("license_whitelist.txt")
        self.license_blacklist = self.load_license_list("license_blacklist.txt")
        self.license_nillist = self.load_license_list("license_nillist.txt")

        if os.path.exists(self.save_filepath):
            os.remove(self.save_filepath)

    def load_license_list(self, filename):
        here = os.path.dirname(__file__)
        filepath = os.path.join(here, filename)
        license_list = []
        with open(filepath, "r") as file:
            license_list = [self.norm_license(line.strip()) for line in file.readlines()]
        return license_list

    # Normalize a license label as a string value, removing specific characters and lowercasing
    # Ref: https://github.ibm.com/ai4code-wisdom/datasets/blob/ \
    #        main/legal_compliance/utils/license_filter.py#L80
    def norm_license(self, license) -> str:
        license = str(license).lower()
        for char in self._char_remove_list:
            license=license.replace(char, "")
        return license

    # return "approved", "not-approved" or "unknown"
    def license_check(self, license: str):
        normed = self.norm_license(license)
        if normed in self.license_whitelist:
            return "approved"
        elif normed in self.license_nillist:
            # nil should be approved
            # Ref: https://github.ibm.com/ai4code-wisdom/datasets/blob/ \
            #        main/legal_compliance/utils/license_filter_test.py#L12-L14
            return "approved"
        elif normed in self.license_blacklist:
            return "not-approved"
        
        return "unknown"
    
    def save_data(self):
        filepath = self.save_filepath

        dirpath = os.path.dirname(filepath)
        if not os.path.exists(dirpath):
            os.makedirs(name=dirpath, mode=0o777, exist_ok=True)
        
        with open(filepath, "a+") as file:
            for line in self.data_buffer:
                file.write(line + "\n")
        
        self.data_buffer = []
        return

    def match(self, ctx: AnsibleRunContext) -> bool:
        return ctx.current.type == RunTargetType.Task

    def process(self, ctx: AnsibleRunContext):
        task = ctx.current
        
        parent_of_task = task.spec.collection or task.spec.role
        context_parent = ""
        if isinstance(ctx.parent, Collection):
            context_parent = ctx.parent.name
        elif isinstance(ctx.parent, Role):
            context_parent = ctx.parent.fqcn
        if context_parent != parent_of_task:
            return RuleResult(verdict=verdict, detail=detail, file=task.file_info(), rule=self.get_metadata())

        verdict = True
        detail = {}

        wisdom_sequence = []

        current_id = task.node_id  # e.g) 0.1.2
        current_depth = task.depth  # e.g) 3

        ctx_1 = ctx.copy()  # --> reset current
        wisdom_sequence = make_sequence(ctx_1, current_depth, current_id)

        all_vars = get_variables(task)

        wisdom_context = {}
        wisdom_context["sequence"] = wisdom_sequence 
        wisdom_context["variables"] = all_vars

        yaml_before_task = make_yaml_before_task(ctx_1, task.spec)

        train = {
            "license": "",
            "license_check": "",
            "source": "",
            "path": "",
            "repo_name": "",
            "type": "",
            "prompt": "",
            "input_script": "",
            "output_script": "",
            "token_count": 0,
            "op_token_count": 0,
            "sample_type": 0,
            "context_len": 0,
            "module_name": "",
            "id": 0,
            "prompt_key": ""
        }

        module = task.get_annotation("module.correct_fqcn", "")

        if not module and task.spec.module:
            short_name = task.spec.module.split(".")[-1]
            if short_name == "include_role":
                module = "ansible.builtin.include_role"
            elif short_name == "import_role":
                module = "ansible.builtin.import_role"
            elif short_name == "include_tasks":
                module = "ansible.builtin.include_tasks"
            elif short_name == "import_tasks":
                module = "ansible.builtin.import_tasks"
            elif short_name == "include":
                module = "ansible.builtin.include"

        if module.endswith("assert"):
            return RuleResult(verdict=verdict, detail=detail, file=task.file_info(), rule=self.get_metadata())

        repo_name, license, source = find_repo_info(ctx_1)
        train["input_script"] = json.dumps(wisdom_context, default=serialize)
        train["context_len"] = len(wisdom_context["sequence"])
        train["yaml_before_task"] = yaml_before_task
        train["license"] = license
        train["license_check"] = self.license_check(license)
        train["source"] = source
        train["path"] = getattr(task.spec, "defined_in", "")
        train["repo_name"] = repo_name
        train["type"] = getattr(task.spec, "type", "")
        train["output_script"] = getattr(task.spec, "yaml_lines", "")
        train["module_name"] = module
        train["id"] = f"{current_id}-{current_depth}"  # <ari_node_id> - <ari_node_depth>
        train["ari_task_key"] = task.spec.key
        train["ari_task_spec"] = jsonpickle.encode(task.spec, make_refs=False, unpicklable=False)
        
        prompt = ""
        yamllines = getattr(task.spec, "yaml_lines", "").split("\n")
        for yl in yamllines:
            yl2 = yl.replace(" ", "")
            if yl2.startswith("-name:"):
                prompt = yl
                break
        train["prompt"] = prompt
        lp = prompt.replace("- name:", "").lower()
        train["prompt_key"] = re.sub(r"[^a-zA-Z]", "", lp)

        detail = train

        is_last_node_for_this_parent = False
        if ctx.last_item and ctx.is_last_task(task):
            is_last_node_for_this_parent = True

        self.data_buffer.append(json.dumps(detail, default=serialize))
        if len(self.data_buffer) >= self.buffer_size or is_last_node_for_this_parent:
            self.save_data()

        return RuleResult(verdict=verdict, detail=detail, file=task.file_info(), rule=self.get_metadata())


# NOTE: This is irreversible serialization
def serialize(obj):
    if isinstance(obj, date):
        serial = obj.isoformat()
        return serial

    if isinstance(obj, time):
        serial = obj.isoformat()
        return serial
    
    if isinstance(obj, bytes):
        return str(obj)

    if hasattr(obj, "__dict__"):
        return obj.__dict__

    return obj