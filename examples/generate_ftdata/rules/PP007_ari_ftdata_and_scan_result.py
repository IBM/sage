import json
import jsonpickle
import threading
import distutils
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
    Variable,
    VariableType,
)
import os
import re

import yaml
try:
    # if `libyaml` is available, use C based loader for performance
    import _yaml  # noqa: F401
    from yaml import CSafeDumper as Dumper
except Exception:
    # otherwise, use Python based loader
    from yaml import SafeDumper as Dumper

# Set default representer
def default_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', serialize(data))
yaml.representer.SafeRepresenter.add_representer(None, default_representer)


thread_id = threading.get_native_id()
in_parallel = distutils.util.strtobool(os.getenv("SAGE_CONTENT_ANALYSIS_PARALLEL", "False"))
out_dir = os.getenv("SAGE_CONTENT_ANALYSIS_OUT_DIR", "/tmp/ftdata")
file_suffix = f"_{thread_id}" if in_parallel else ""
default_task_context_data_filepath = os.path.join(out_dir, f"task_context_data{file_suffix}.json")
default_scan_res_filepath = os.path.join(out_dir, f"scan_result{file_suffix}.json")

vars_json_length_threshold = 1000
max_context_node_size = 50
max_yaml_str_size = 3000


def find_repo_info(ctx: AnsibleRunContext):
    ctx_1 = ctx.copy()  # --> reset current

    scan_data = ctx_1.scan_metadata
    scan_type = scan_data.get("type")
    scan_path = scan_data.get("name")

    src_path_list_file = os.getenv('FTDATA_SRC_PATH_LIST')

    with open(src_path_list_file, "r") as file:
        lines = file.readlines()

    input_list = []
    for line in lines:
        data = json.loads(line)
        input_list.append(data)

    repo_name = ""
    repo_type = ""
    license = ""
    source = ""
    path = ""

    for input in input_list:
        input_type = input.get("type")
        if scan_type != input_type:
            continue
        
        input_path = ""
        if scan_type == "role":
            input_path = input.get("role_path")
        else:
            input_path = input.get("target_file")
        if scan_path.endswith(input_path):
            repo_name = input.get("_repo_name")
            repo_type = input.get("_repo_type")
            source = input.get("_source")
            license = input.get("_license")
            path = input.get("_path")

    return repo_type, repo_name, license, source, path


def make_yaml_before_task(ctx: AnsibleRunContext, task: Task) -> list:
    ctx_1 = ctx.copy()  # --> reset current
    yaml_before_task = ""
    filepath_of_this_task = task.defined_in
    for node in ctx_1:
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

    # we omit yaml_before_task if it is huge so that we can avoid data size issue
    if len(yaml_before_task) > max_yaml_str_size:
        yaml_before_task = ""
    return yaml_before_task


def get_used_modules(ctx, task):
    ctx_1 = ctx.copy()  # --> reset current
    used_modules = []
    for node in ctx_1:
        # skip non-task node
        if node.type != RunTargetType.Task:
            continue
        # if node is the target task, exit loop
        if node.spec.key == task.spec.key:
            break
        
        module = get_module_name(node)
         # if the module is empty, skip it
        if not module:
            continue
        # if the module is ansible.builtin one, skip it
        if module.startswith("ansible.builtin."):
            continue
        # skip assert (it is covered by ansible.builtin condition though)
        if module.endswith("assert"):
            continue
        # if the module is already in used_modules, skip it
        if module in used_modules:
            continue
        used_modules.append(module)
    return used_modules


def get_name_sequence(ctx, task):
    ctx_1 = ctx.copy()  # --> reset current
    task_node_id = task.node_id
    def get_parent_node_id(node_id):
        if "." in node_id:
            return node_id.rsplit(".", 1)[0]
        # if node_id is like "3", then we regard "" (empty string) as the parent id
        return ""
    task_parent_node_id = get_parent_node_id(task_node_id)
    task_node_depth = task.depth
    name_seq = []
    for node in ctx_1:
        skip = True
        if node.depth < task_node_depth:
            if task_node_id.startswith(node.node_id):
                skip = False
        elif node.depth == task_node_depth:
            if get_parent_node_id(node.node_id) == task_parent_node_id:
                skip = False
        
        if skip:
            continue

        name = ""
        if node.type == RunTargetType.Role:
            if isinstance(node.spec.metadata, dict):
                name = node.spec.metadata.get("galaxy_info", {}).get("description", "")
        elif node.type == RunTargetType.Play:
            name = node.spec.name
        elif node.type == RunTargetType.Task:
            name = node.spec.name
        if node.spec.key == task.spec.key:
            break
        if not name:
            continue
        name_seq.append(name)

    # we truncate older context if the name sequence is too large
    if len(name_seq) > max_context_node_size:
        name_seq = name_seq[-max_context_node_size:]
    
    return name_seq


def get_used_vars(ctx, task):
    ctx_1 = ctx.copy()  # --> reset current

    # we don't use `task.variable_use` here because it contas vars used by the target task
    # instead, we use `variable_use` of the previous task if the one exist
    previous_task = None
    for node in ctx_1:
        if node.type != RunTargetType.Task:
            continue
        if node.spec.key == task.spec.key:
            break
        previous_task = node

    # if there is no task before the target, return no vars
    if not previous_task:
        return [], False
    
    used_var_names = list(previous_task.variable_use.keys())
    omitted = False
    used_var_names_str = json.dumps(used_var_names)
    if len(used_var_names_str) > vars_json_length_threshold:
        used_var_names = []
        omitted = True

    return used_var_names, omitted


def get_defined_vars(task):
    defined_var_names = list(task.variable_set.keys())
    omitted = False
    defined_var_names_str = json.dumps(defined_var_names)
    if len(defined_var_names_str) > vars_json_length_threshold:
        defined_var_names = []
        omitted = True

    return defined_var_names, omitted

def get_used_vars_in_target_task(task):
    var_names = []
    vars = task.args.vars
    for var in vars:
        var_names.append(var.name)
    return var_names

def get_dependency(ctx):
    parent = ctx.parent
    coll_dependencies = []
    role_dependencies = []
    if isinstance(parent, Collection):
        # there was a bug around "collection.dependency"
        # so we get dep info from metadata instead
        # dependency = parent.dependency
        original = parent.metadata.get("collection_info", {}).get("dependencies", {})
        if original:
            coll_dependencies = list(original.keys())
    elif isinstance(parent, Role):
        original = parent.dependency
        if original and isinstance(original, dict):
            coll_dependencies = original.get("collections", [])
            role_dependencies = original.get("roles", [])
    return coll_dependencies, role_dependencies


def get_module_name(task):
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

    if not module:
        module = task.spec.module

    return module


def get_metrics(ctx, task, module, used_modules, used_vars, defined_vars, coll_deps, role_deps):
    d = {
        "module_name": "",
        "module_parent": "",
        "vars_used_in_this_task": [],
        "num_of_vars_used_in_this_task": 0,
        "exact_match_in_used_modules": 0,
        "parent_match_in_used_modules": 0,
        "parent_found_in_dependencies": 0,
        "num_of_vars_found_in_used_vars": 0,
        "num_of_vars_found_in_defined_vars": 0,
        "num_of_vars_covered_by_context": 0,
    }
    d["module_name"] = module
    
    if "." not in module:
        return d
    
    parts = module.split(".")
    module_parent = ""
    if len(parts) == 2:
        module_parent = parts[0]
    elif len(parts) >= 3:
        module_parent = ".".join(parts[:2])
    d["module_parent"] = module_parent
    
    if module_parent == "ansible.builtin":
        return d
    
    exact_match = [um for um in used_modules if um == module]
    parent_match = [um for um in used_modules if um.startswith(f"{module_parent}.")]
    d["exact_match_in_used_modules"] = len(exact_match)
    d["parent_match_in_used_modules"] = len(parent_match)

    dep_count = 0
    if module_parent in coll_deps:
        dep_count = 1
    elif module_parent in role_deps:
        dep_count = 1

    d["parent_found_in_dependencies"] = dep_count

    if not task.args:
        return d

    vars_used_in_this_task = list(set([v.name.split(".")[0] for v in task.args.vars]))
    d["vars_used_in_this_task"] = vars_used_in_this_task
    num_of_vars_used_in_this_task = len(vars_used_in_this_task)
    d["num_of_vars_used_in_this_task"] = num_of_vars_used_in_this_task

    if num_of_vars_used_in_this_task == 0:
        return d
    
    found_used_var_count = 0
    found_defined_var_count = 0
    covered_var_count = 0
    for var_name in vars_used_in_this_task:
        covered = False
        if var_name in used_vars:
            found_used_var_count += 1
            covered = True
        
        if var_name in defined_vars:
            found_defined_var_count += 1
            covered = True

        if covered:
            covered_var_count += 1
        
    d["num_of_vars_found_in_used_vars"] = found_used_var_count
    d["num_of_vars_found_in_defined_vars"] = found_defined_var_count
    d["num_of_vars_covered_by_context"] = covered_var_count
    return d

@dataclass
class PreProcessingRule(Rule):
    rule_id: str = "PP007"
    description: str = "get a FT data and ari scan result"
    enabled: bool = True
    name: str = "GetFTDataAndScanResult"
    version: str = "v0.0.1"
    severity: Severity = Severity.NONE
    tags: tuple = ("wisdom")
    precedence: int = 1

    license_whitelist: list = field(default_factory=list)
    license_blacklist: list = field(default_factory=list)
    license_nillist: list = field(default_factory=list)

    _char_remove_list: tuple = ("[","]","'",'"','(',')')

    task_context_data_save_filepath: str = default_task_context_data_filepath
    scan_result_save_filepath: str = default_scan_res_filepath

    data_buffer_ftdata: list = field(default_factory=list)
    data_buffer_scan_result: list = field(default_factory=list)
    buffer_size: int = 1000
    
    def __post_init__(self):

        self.license_whitelist = self.load_license_list("license_whitelist.txt")
        self.license_blacklist = self.load_license_list("license_blacklist.txt")
        self.license_nillist = self.load_license_list("license_nillist.txt")

        if os.path.exists(self.task_context_data_save_filepath):
            os.remove(self.task_context_data_save_filepath)

        if os.path.exists(self.scan_result_save_filepath):
            os.remove(self.scan_result_save_filepath)

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
        # ftdata
        filepath = self.task_context_data_save_filepath

        dirpath = os.path.dirname(filepath)
        if not os.path.exists(dirpath):
            os.makedirs(name=dirpath, mode=0o777, exist_ok=True)
        
        with open(filepath, "a+") as file:
            for line in self.data_buffer_ftdata:
                file.write(line + "\n")
        
        self.data_buffer_ftdata = []

        # scan result
        filepath = self.scan_result_save_filepath

        dirpath = os.path.dirname(filepath)
        if not os.path.exists(dirpath):
            os.makedirs(name=dirpath, mode=0o777, exist_ok=True)
        
        with open(filepath, "a+") as file:
            for line in self.data_buffer_scan_result:
                file.write(line + "\n")

        self.data_buffer_scan_result = []
        return
    
    def make_task_format_context(self, context):
        context_tasks = []
        used_vars = context.get("used_vars")
        if used_vars:
            task = {}
            task["name"] = "set used variables"
            task["ansible.builtin.set_fact"] = {}
            context_tasks.append(task)

        defined_vars = context.get("defined_vars")
        if defined_vars:
            task = {}
            task["name"] = "define variables"
            task["ansible.builtin.set_fact"] = {}
            context_tasks.append(task)
        
        dependency_roles = context.get("dependency_roles")
        if dependency_roles:
            for role in dependency_roles:
                task = {}
                task["name"] = "import role"
                task["ansible.builtin.import_role"] = {}
                context_tasks.append(task)
        
        return

    def match(self, ctx: AnsibleRunContext) -> bool:
        return ctx.current.type == RunTargetType.Task

    def process(self, ctx: AnsibleRunContext):
        task = ctx.current
        
        verdict = False
        detail = {}

        parent_of_task = task.spec.collection or task.spec.role
        if "." in parent_of_task:
            context_parent = ""
            if isinstance(ctx.parent, Collection):
                context_parent = ctx.parent.name
            elif isinstance(ctx.parent, Role):
                context_parent = ctx.parent.fqcn
            if context_parent != parent_of_task:
                return RuleResult(verdict=verdict, detail=detail, file=task.file_info(), rule=self.get_metadata())

        verdict = True
        detail = {}

        current_id = task.node_id  # e.g) 0.1.2
        current_depth = task.depth  # e.g) 3

        module = get_module_name(task)

        used_modules = get_used_modules(ctx, task)
        name_sequence = get_name_sequence(ctx, task)
        used_vars, used_vars_omitted = get_used_vars(ctx, task)
        defined_vars, defined_vars_omitted = get_defined_vars(task)
        coll_deps, role_deps = get_dependency(ctx)
        metrics = get_metrics(ctx, task, module, used_modules, used_vars, defined_vars, coll_deps, role_deps)

        wisdom_context = {}

        wisdom_context["used_modules"] = used_modules
        wisdom_context["name_sequence"] = name_sequence
        wisdom_context["used_vars"] = used_vars
        wisdom_context["used_vars_omitted"] = used_vars_omitted
        wisdom_context["defined_vars"] = defined_vars
        wisdom_context["defined_vars_omitted"] = defined_vars_omitted
        wisdom_context["dependency_collections"] = coll_deps
        wisdom_context["dependency_roles"] = role_deps

        # context_tasks = self.make_task_format_context(wisdom_context)

        yaml_before_task = make_yaml_before_task(ctx, task.spec)

        train = {
            "license": "",
            "license_check": "",
            "source": "",
            "path": "",
            "repo_name": "",
            "type": "",
            "prompt": "",
            "input_script": "",
            "metrics": {},
            "output_script": "",
            "token_count": 0,
            "op_token_count": 0,
            "sample_type": 0,
            "context_len": 0,
            "module_name": "",
            "id": 0,
            "prompt_key": ""
        }

        # repo_type, repo_name, license, source, path = find_repo_info(ctx)

        # input_script = json.dumps(wisdom_context, default=serialize)
        input_script = yaml.dump(wisdom_context, sort_keys=False, Dumper=Dumper)
        train["input_script"] = input_script
        train["metrics"] = metrics
        train["context_len"] = len(input_script)
        train["yaml_before_task"] = yaml_before_task
        train["license"] = ""
        train["license_check"] = ""
        train["source"] = ""
        train["path"] = getattr(task.spec, "defined_in", "")
        train["repo_name"] = ""
        train["type"] = ""
        train["scan_type"] = getattr(task.spec, "type", "")
        train["output_script"] = getattr(task.spec, "yaml_lines", "")
        train["module_name"] = module
        train["id"] = f"{current_id}-{current_depth}"  # <ari_node_id> - <ari_node_depth>
        train["ari_task_key"] = task.spec.key
        scan_data = ctx.scan_metadata
        scan_type = scan_data.get("type")
        scan_path = scan_data.get("name")
        train["scan_type"] = scan_type
        train["scan_path"] = scan_path
        
        prompt = ""
        yamllines = getattr(task.spec, "yaml_lines", "").split("\n")
        for yl in yamllines:
            yl2 = yl.replace(" ", "")
            if yl2.startswith("-name:"):
                prompt = yl
                break
        train["prompt"] = prompt.lower()
        lp = prompt.replace("- name:", "").lower()
        train["prompt_key"] = re.sub(r"[^a-zA-Z]", "", lp)

        detail = train

        task_spec = vars(task.spec)
        annotations = {}
        annotations["correct_fqcn"] = task.get_annotation(key="module.correct_fqcn")
        annotations["need_correction"] = task.get_annotation(key="module.need_correction")
        annotations["wrong_module_name"] = task.get_annotation(key="module.wrong_module_name")
        annotations["suggested_fqcn"] = task.get_annotation(key="module.suggested_fqcn")
        annotations["suggested_dependency"] = task.get_annotation(key="module.suggested_dependency")
        annotations["resolved_fqcn"] = task.get_annotation(key="module.resolved_fqcn")
        annotations["not_exist"] = task.get_annotation(key="module.not_exist")
        annotations["wrong_arg_keys"] = task.get_annotation(key="module.wrong_arg_keys")
        annotations["available_arg_keys"] = task.get_annotation(key="module.available_arg_keys")
        annotations["required_arg_keys"] = task.get_annotation(key="module.required_arg_keys")
        annotations["available_args"] = task.get_annotation(key="module.default_args")
        annotations["default_args"] = task.get_annotation(key="module.available_args")
        annotations["used_alias_and_real_keys"] = task.get_annotation(key="module.used_alias_and_real_keys")
        annotations["available_args"] = task.get_annotation(key="module.available_args")
        annotations["wrong_arg_values"] = task.get_annotation(key="module.wrong_arg_values")
        annotations["undefined_values"] = task.get_annotation(key="module.undefined_values")
        annotations["unknown_type_values"] = task.get_annotation(key="module.unknown_type_values")
        annotations["undefined_vars"] = task.get_annotation(key="module.undefined_vars")
        annotations["unknown_name_vars"] = task.get_annotation(key="module.unknown_name_vars")
        annotations["unnecessary_loop_vars"] = task.get_annotation(key="module.unnecessary_loop_vars")
        annotations["vars_used_in_previous_tasks"] = used_vars
        annotations["vars_defined_in_previous_tasks"] = defined_vars
        annotations["vars_used_in_target_task"] = get_used_vars_in_target_task(task)

        task_spec["annotations"] = annotations


        is_last_node_for_this_parent = False
        if ctx.last_item and ctx.is_last_task(task):
            is_last_node_for_this_parent = True
        

        self.data_buffer_ftdata.append(json.dumps(detail, default=serialize))
        self.data_buffer_scan_result.append(jsonpickle.encode(task_spec, make_refs=False, unpicklable=False))
        if len(self.data_buffer_ftdata) >= self.buffer_size or is_last_node_for_this_parent:
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