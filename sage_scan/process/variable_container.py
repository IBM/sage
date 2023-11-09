import argparse
from dataclasses import dataclass, field

from sage_scan.models import load_objects
from sage_scan.process.utils import list_entrypoints, get_taskfiles_in_role
from sage_scan.models import Playbook, TaskFile, Play, Task, Role, PlaybookData, TaskFileData
from sage_scan.process.variable_resolver import extract_variable_names
import json
import os
import copy
import re

magic_vars = []
vars_file = os.getenv("VARS_FILE", os.path.join(os.path.dirname(__file__),"ansible_variables.txt"))
with open(vars_file, "r") as f:
    magic_vars = f.read().splitlines() 


@dataclass
class VarCont:
    obj_key: str = ""
    filepath: str = ""
    used_vars: {} = field(default_factory=dict)
    # set_vars: field(default_factory=dict)
    set_scoped_vars: {} = field(default_factory=dict) # available in children
    set_explicit_scoped_vars: {} = field(default_factory=dict) # available in children
    set_local_vars: {} = field(default_factory=dict) # available in local

    def accum(self, vc):
        self.set_explicit_scoped_vars |= vc.set_explicit_scoped_vars
        self.set_scoped_vars |= vc.set_scoped_vars
        self.used_vars |= vc.used_vars
        return 
    
    def get_used_vars(self):
        return self.used_vars
    
    def get_set_vars_in_obj(self):
        set_vars = {}
        set_vars |= self.set_explicit_scoped_vars
        set_vars |= self.set_scoped_vars
        set_vars |= self.set_local_vars
        return set_vars


# generate VarCont from sage obj
def to_vc(obj):
    vc = None
    if isinstance(obj, Playbook):
        vc = get_vc_from_playbook(obj)
    elif isinstance(obj, Play):
        vc = get_vc_from_play(obj)
    elif isinstance(obj, Role):
        vc = get_vc_from_role(obj)
    elif isinstance(obj, TaskFile):
        vc = get_vc_from_taskfile(obj)
    elif isinstance(obj, Task):
        vc = get_vc_from_task(obj)
    return vc


# return VarCont list
def make_vc_arr(call_seq):
    vc_arr = {}
    for obj in call_seq:
        vc = to_vc(obj)
        if vc is not None:
            vc_arr[vc.obj_key] = vc
    return vc_arr


# return if a variable v1 is defined in an another variable v2.
def check_if_defined(used_var, defined_var):
    if used_var == defined_var or used_var.startswith(defined_var):
        return True 
    return False


def check_if_defined_explicitly(used_var, defined_var):
    if used_var == defined_var:
        return True 
    return False


def check_if_magic_vars(used_var):
    if "." in used_var:
        used_var = used_var.split(".")[0]
    if used_var in magic_vars:
        return True
    if used_var.startswith("ansible_"):
        return True
    if used_var == "default(omit)" or used_var == "default(false)":
        return True
    return False


# return all vars in vc.used_vars but not in accum_vc.set_vars
def find_undefined_vars(vc: VarCont, accum_vc: VarCont):
    undefined_vars = {}
    for v1_name, v1_val in vc.used_vars.items():
        in_scoped_vars = False
        in_local_vars = False
        in_set_vars = False  # check with set vars in the same task when vars is used in 'failed_when'
        if check_if_magic_vars(v1_name):
            continue
        for v2 in accum_vc.set_scoped_vars:
            if check_if_defined(v1_name, v2):
                in_scoped_vars = True
                break
        if in_scoped_vars:
            continue
        for v2 in accum_vc.set_explicit_scoped_vars:
            if check_if_defined_explicitly(v1_name, v2):
                in_scoped_vars = True
                break
        if in_scoped_vars:
            continue
        for v2 in vc.set_local_vars:
            if check_if_defined(v1_name, v2):
                in_local_vars = True
                break
        if in_local_vars:
            continue
        if v1_name in vc.set_scoped_vars:
            set_value = vc.set_scoped_vars[v1_name]
            if type(set_value) is str and v1_name in set_value:
                # this supports the case like (x = x + y)
                continue
        if v1_val.get("in_failed_when", False):
            for v2 in vc.set_scoped_vars:
                if check_if_defined(v1_name, v2):
                    in_set_vars = True
                    break
            if in_set_vars:
                continue
        undefined_vars[v1_name] = v1_val
    return undefined_vars, vc.used_vars


# return accum vc based on call tree
def compute_accum_vc(call_tree, vc_arr, obj_key, obj_filepath):
    parents=[]
    parents = traverse_and_get_parents(obj_key, call_tree, parents)
    parents.reverse()
    accum_vc = VarCont()
    for p in parents:
        pvc = vc_arr[p]
        if pvc.filepath != obj_filepath:
            continue
        accum_vc.accum(pvc)
    return accum_vc


# return the list of parent obj key
def traverse_and_get_parents(node_key, call_tree, parent_nodes):
    sibling = []
    for parent, child in call_tree:
        # sibling
        key_parts = child.key.rsplit('#', 1)
        p1 = key_parts[0]
        p2 = key_parts[-1]
        n_key_parts = node_key.rsplit('#', 1)
        np1 = n_key_parts[0]
        np2 = n_key_parts[-1]
        if "task:" in p2 and "task:" in np2:
            p2_num = int(p2.replace("task:[", "").replace("]", ""))
            np2_num = int(np2.replace("task:[", "").replace("]", ""))
            if p1 == np1 and p2_num < np2_num:
                sibling.insert(0, child.key)
    for parent, child in call_tree:
        # parent
        if child.key == node_key:
            parent_nodes.extend(sibling)
            parent_nodes.append(parent.key)
            traverse_and_get_parents(parent.key, call_tree, parent_nodes)
            break
    # parent_nodes.reverse()
    return parent_nodes


# return VarCont at a playbook level
def get_vc_from_playbook(playbook: Playbook):
    vc = VarCont()
    vc.obj_key = playbook.key
    return vc


# return VarCont at a play level
def get_vc_from_play(play: Play):
    vc = VarCont()
    vc.obj_key = play.key
    vc.filepath = play.filepath
    vars = flatten_dict(play.variables)
    for name, val in vars.items():
        if isinstance(val, str) and "{{" in val:
            vc.set_scoped_vars[name] = val
        else:
            vc.set_explicit_scoped_vars[name] = val
    # TODO: support vars_prompt
    return vc


# return VarCont at a role level
def get_vc_from_role(role: Role):
    vc = VarCont()
    vc.obj_key = role.key
    vc.filepath = role.filepath
    vc.set_explicit_scoped_vars |= role.default_variables
    vc.set_explicit_scoped_vars |= role.variables
    return vc


# return VarCont at a taskfile level
def get_vc_from_taskfile(taskfile: TaskFile):
    vc = VarCont()
    vc.obj_key = taskfile.key
    vc.filepath = taskfile.filepath
    vc.set_explicit_scoped_vars |= taskfile.variables
    return vc


# return VarCont at a task level
def get_vc_from_task(task: Task):
    vc = VarCont()
    vc.obj_key = task.key
    vc.filepath = task.filepath
    vc.set_scoped_vars |= task.set_facts
    vc.set_scoped_vars |= task.registered_variables
    vc.set_local_vars |= task.variables
    vc.set_local_vars |= task.loop
    vc.used_vars = used_vars_in_task(task)
    return vc


# return used vars in a task
def used_vars_in_task(task: Task):
    name = task.name
    options = task.options
    module_options = task.module_options
    flat_options = flatten_dict_list(options)
    flat_module_options = flatten_dict_list(module_options)
    vars_in_options = extract_var_parts(flat_options)
    special_vars = check_when_option(options)
    vars_in_module_options = extract_var_parts(flat_module_options)
    vars_in_name = extract_var_parts(name)
    all_used_vars = {}
    all_used_vars |= vars_in_options
    all_used_vars |= vars_in_module_options
    all_used_vars |= special_vars
    all_used_vars |= vars_in_name
    return all_used_vars


# return var names
def extract_var_parts(options: dict|str):
    vars_in_option = {}
    if isinstance(options, str):
        if "{{" in options:
            vars = extract_variable_names(options)
            for v in vars:
                vars_in_option[v["name"]] = v
    elif isinstance(options, dict):
        for _, ov in options.items():
            if type(ov) != str:
                continue
            if "{{" in ov:
                vars = extract_variable_names(ov)
                for v in vars:
                    vars_in_option[v["name"]] = v
    return vars_in_option


# return used vars in when option
def check_when_option(options):
    used_vars = {}
    if "when" not in options and "failed_when" not in options:
        return used_vars
    when_value = options.get("when", "")
    failed_when_value = options.get("failed_when", "")
    all_values = []
    if type(when_value) == list:
        all_values.extend(when_value)
            
    elif type(when_value) == dict:
        for v in when_value.values():
            all_values.append(v)
    else:
        all_values.append(when_value)

    _used_vars = extract_when_option_var_name(all_values)
    used_vars |= _used_vars

    all_values = []
    if type(failed_when_value) == list:
        all_values.extend(failed_when_value)
    elif type(failed_when_value) == dict:
        for v in failed_when_value.values():
            all_values.append(v)
    else:
        all_values.append(failed_when_value)
        # all_values = re.split('[ |]', f"{failed_when_value}")
    _used_vars = extract_when_option_var_name(all_values, is_failed_when=True)
    used_vars |= _used_vars
    return used_vars


def extract_when_option_var_name(option_parts, is_failed_when=False):
    option_parts = _split_values(option_parts)
    used_vars = {}
    ignore_words = ["defined", "undefined", "is", "not", "and", "or", "|", "in", "none", "+", "vars"]
    boolean_vars = ["True", "true", "t", "yes", 'y', 'on', "False", "false", 'f', 'no', 'n', 'off']
    data_type_words = ["bool", "float", "int", "length", "string"]
    for p in option_parts:
        if "match(" in p or "default(" in p:
            continue
        p = p.replace(")","").replace("(","").replace("{", "").replace("}", "")
        if not p:
            continue
        if "=" in p or "<" in p or ">" in p:
            continue
        if p in ignore_words:
            continue
        if p in boolean_vars:
            continue
        if p in data_type_words:
            continue
        if p.startswith('"') or p.startswith("'"):
            continue
        if p.startswith("[") or p.startswith("]"):
            continue
        if p.startswith("item"):
            continue
        if "[" in p:
            # extract var part from dict format like "hostvars[inventory_hostname]"
            all_parts = re.split('[\[]', f"{p}")
            if "[" not in all_parts[0]:
                p = all_parts[0]
        p = p.replace("\"", "")
        if is_num(p):
            continue
        if check_if_magic_vars(p):
            continue
        if is_failed_when:
            used_vars[p] = {"original": p, "name": p, "in_failed_when": True}
        else:
            used_vars[p] = {"original": p, "name": p}
    return used_vars


def _split_values(all_values):
    all_parts = []
    for val in all_values:
        # identify string enclosed in (") or (') to support the following case
        # when: result.failed or 'Server API protected' not in result.content
        double_quoted_strings = re.findall(r'"(.*?)"', f"{val}")
        single_quoted_strings = re.findall(r"'(.*?)'", f"{val}")
        for quoted_str in double_quoted_strings:
            if quoted_str != "" and quoted_str != " ":
                val = val.replace(quoted_str, " ")
        for quoted_str in single_quoted_strings:
            if quoted_str != '' and quoted_str != ' ':
                val = val.replace(quoted_str, " ")
        all_parts.extend(re.split('[ |]', f"{val}"))
    return all_parts


def flatten_dict_list(d, parent_key='', sep='.'):
    items = {}
    if d is None:
        return items
    if type(d) == list:
        for i, v in enumerate(d):
            items[i] = v
        return items
    elif type(d) == dict:
        for key, value in d.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            if isinstance(value, dict):
                items.update(flatten_dict_list(value, new_key, sep=sep))
            elif isinstance(value, list):
                for v in value:
                    list_new_key = f"{new_key}[{value.index(v)}]"
                    if isinstance(v, dict):
                        items.update(flatten_dict_list(v, list_new_key, sep=sep))
                    else:
                        items[list_new_key] = v
            else:
                items[new_key] = value
    else:
        items["value"] = d
        return items
    return items


def flatten_dict(d, parent_key='', sep='.'):
    items = {}
    if type(d) == str:
        items["value"] = d
        return items
    if type(d) == list:
        for i, v in enumerate(d):
            items[i] = v
        return items
    for key, value in d.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            # add current key and value
            items[key] = value
            # handle child dict
            items.update(flatten_dict(value, new_key, sep=sep))
        else:
            items[new_key] = value
    return items


# make dict from key parts
def recursive_update(d, keys, value):
    if not isinstance(d, dict):
        d = {}
    new_d = d.copy()

    if not keys:
        return {}
    key = keys[0]
    if len(keys) <= 1:
        new_d[key] = value
    else:
        rest_keys = keys[1:]
        if key not in new_d or not isinstance(new_d[key], dict):
            new_d[key] = {}
        new_d[key] = recursive_update(new_d[key], rest_keys, value)
    return new_d


# if single child element, flatten that part. if multiple child elements, keep nest structure.
def flatten_single_child_in_dict(d, parent_key='', sep='.'):
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            if len(v) == 1:
                nested_key, nested_value = v.popitem()
                items.update(flatten_dict({f"{new_key}{sep}{nested_key}": nested_value}))
            else:
                items[new_key] = flatten_dict(v)
        else:
            items[new_key] = v
    return items


def is_num(s):
    try:
        float(s)
    except ValueError:
        return False
    else:
        return True


def filter_complex_name_vars(used_vars):
    simple_used_vars = copy.copy(used_vars)
    for var_name in used_vars:
        if not var_name in simple_used_vars:
            continue
        if "[" in var_name:
            simple_used_vars.pop(var_name)
        elif "(" in var_name:
            simple_used_vars.pop(var_name)
        elif "=" in var_name:
            simple_used_vars.pop(var_name)
    return simple_used_vars


# def check_possibility_to_flatten_vars(set_vars, used_vars):
#     return


# replace vars in task
def replace_vars_in_task(task: Task, change_vars):
    new_task = copy.copy(task)
    yaml_lines = task.yaml_lines
    for var, to_be_var in change_vars.items():
        new_task.module_options = replace_vars(new_task.module_options, var, to_be_var)
        new_task.options = replace_vars(new_task.options, var, to_be_var)
        yaml_lines = yaml_lines.replace(var, to_be_var)
    new_task.yaml_lines = yaml_lines
    return new_task


# return new data with to_be value
def replace_vars(data, current, to_be):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                data[key] = value.replace(current, to_be)
            else:
                replace_vars(value, current, to_be)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, str):
                data[i] = item.replace(current, to_be)
            else:
                replace_vars(item, current, to_be)
    elif isinstance(data, str):
        data = data.replace(current, to_be)
    return data


# return all undefined vars
def find_all_undefined_vars(call_tree, vc_arr, target_filepath):
    undefined_vars = {}
    used_vars = {}

    accum_vc = VarCont()
    for vc in vc_arr.values():
        if target_filepath and vc.filepath != target_filepath:
            continue
        accum_vc = compute_accum_vc(call_tree, vc_arr, vc.obj_key, vc.filepath)
        und_vars, _used_vars = find_undefined_vars(vc, accum_vc)
        undefined_vars |= und_vars
        used_vars |= _used_vars

    return undefined_vars, used_vars


# return all declared vars
def find_all_set_vars(pd: PlaybookData|TaskFileData, call_tree, vc_arr, check_point=None):
    if not call_tree:
        return {}, {}

    all_set_vars = {}
    role_vars = {}
    if not check_point:
        check_point = call_tree[-1][1]
    accum_vc = compute_accum_vc(call_tree, vc_arr, check_point.key, pd.object.filepath)
    if isinstance(pd, TaskFileData):
        if pd.role:
            parent_role = pd.role
            r_vc = get_vc_from_role(parent_role)
            accum_vc.accum(r_vc)
            role_vars |= r_vc.set_explicit_scoped_vars
            role_vars |= r_vc.set_scoped_vars
    all_set_vars |= accum_vc.set_explicit_scoped_vars
    all_set_vars |= accum_vc.set_scoped_vars
    return all_set_vars, role_vars


# return undefined var's value if the variable is defined in role_vars etc.
def get_undefined_vars_value(set_vars, undefined_vars):
    defined_in_parents = {}
    no_value_vars = {}
    for ud_name, val in undefined_vars.items():
        if ud_name in set_vars:
            _val = copy.copy(val)
            _val["value"] = set_vars[ud_name]
            defined_in_parents[ud_name] = _val
        else:
            no_value_vars[ud_name] = None
    return defined_in_parents, no_value_vars


def get_play_vars_from_data(pd: PlaybookData|TaskFileData):
    set_vars = {}
    call_seq = pd.call_seq
    for obj in call_seq:
        if isinstance(obj, Play):
            vc = get_vc_from_play(obj)
            set_vars = vc.get_set_vars_in_obj()
    return set_vars


# return declared vars in the file and role vars
def get_set_vars_from_data(pd: PlaybookData|TaskFileData):
    call_tree = pd.call_tree
    call_seq = pd.call_seq
    vc_arr = make_vc_arr(call_seq)
    set_vars, role_vars = find_all_set_vars(pd, call_tree, vc_arr)
    return set_vars, role_vars


def get_used_vars_from_data(pd: PlaybookData|TaskFileData):
    call_tree = pd.call_tree
    call_seq = pd.call_seq
    vc_arr = make_vc_arr(call_seq)
    _, used_vars = find_all_undefined_vars(call_tree, vc_arr, pd.object.filepath)
    return used_vars


def get_undefined_vars_in_obj_from_data(pd: PlaybookData|TaskFileData):
    call_tree = pd.call_tree
    call_seq = pd.call_seq
    vc_arr = make_vc_arr(call_seq)
    undefined_vars_in_obj, _ = find_all_undefined_vars(call_tree, vc_arr, pd.object.filepath)
    # TODO: this part will be removed when var name extraction becomes robust.
    undefined_vars_in_obj = filter_complex_name_vars(undefined_vars_in_obj)
    return undefined_vars_in_obj


def get_used_vars_with_no_value_from_data(pd: PlaybookData|TaskFileData):
    call_tree = pd.call_tree
    call_seq = pd.call_seq
    vc_arr = make_vc_arr(call_seq)
    set_vars = find_all_set_vars(pd, call_tree, vc_arr)
    undefined_vars_in_obj, _ = find_all_undefined_vars(call_tree, vc_arr, pd.object.filepath)
    _, no_value_vars = get_undefined_vars_value(set_vars, undefined_vars_in_obj)
    return no_value_vars


def get_undefined_vars_value_from_data(pd: PlaybookData|TaskFileData, extra_set_vars: dict={}):
    call_tree = pd.call_tree
    call_seq = pd.call_seq
    vc_arr = make_vc_arr(call_seq)
    set_vars, _ = find_all_set_vars(pd, call_tree, vc_arr)
    if extra_set_vars:
        set_vars.update(extra_set_vars)
    undefined_vars_in_obj, _ = find_all_undefined_vars(call_tree, vc_arr, pd.object.filepath)
    undefined_vars_value, _ = get_undefined_vars_value(set_vars, undefined_vars_in_obj)
    return undefined_vars_value


# return vars to be set in play
def make_set_vars_for_undefined_vars(pd: PlaybookData|TaskFileData, included_vars: dict={}, extra_set_vars: dict={}): 
    vars_to_set = {}
    used_undefined_vars = get_undefined_vars_in_obj_from_data(pd=pd)
    used_undefined_var_and_value = get_undefined_vars_value_from_data(pd=pd, extra_set_vars=extra_set_vars)
    for var_name in used_undefined_vars:
        if var_name in included_vars:
            continue
        value = ""
        if var_name in used_undefined_var_and_value:
            value = used_undefined_var_and_value[var_name].get("value", "")
        else:
            value = "{{ " + var_name.replace(".", "_") + " }}" 
        if "." in var_name:
            parts = var_name.split(".")
            vars_to_set = recursive_update(vars_to_set, parts, value)
        else:
            vars_to_set[var_name] = value
    vars_to_set = flatten_single_child_in_dict(vars_to_set)
    return vars_to_set


def resolve_variables(pd: PlaybookData|TaskFileData):
    call_tree = pd.call_tree
    call_seq = pd.call_seq
    vc_arr = make_vc_arr(call_seq)
    set_vars, role_vars = find_all_set_vars(pd, call_tree, vc_arr)
    undefined_vars_in_obj, used_vars = find_all_undefined_vars(call_tree, vc_arr, pd.object.filepath)
    undefined_vars_value, _ = get_undefined_vars_value(set_vars, undefined_vars_in_obj)
    vars_to_set = make_set_vars_for_undefined_vars(pd)
    return set_vars, role_vars, used_vars, undefined_vars_in_obj, undefined_vars_value, vars_to_set


def main():
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--file", help="input sage object json file")
    parser.add_argument("-o", "--output", help="output json file")
    args = parser.parse_args()

    fpath = args.file

    sage_objects = load_objects(fpath)
    projects = sage_objects.projects()   

    pbdata_arr = []
    for project in projects:
        entrypoints = list_entrypoints(project)
        for entrypoint in entrypoints:
            if isinstance(entrypoint, TaskFile):
                pbdata_for_this_entry = TaskFileData(object=entrypoint, project=project, follow_include_for_used_vars=False)
                if not pbdata_for_this_entry:
                    continue
                pbdata_arr.append(pbdata_for_this_entry)
            elif isinstance(entrypoint, Playbook):
                pbdata_for_this_entry = PlaybookData(object=entrypoint, project=project, follow_include_for_used_vars=False)
                if not pbdata_for_this_entry:
                    continue
                pbdata_arr.append(pbdata_for_this_entry)
            elif isinstance(entrypoint, Role):
                taskfiles = get_taskfiles_in_role(entrypoint, project)
                for taskfile in taskfiles:
                    pbdata_for_this_entry = TaskFileData(object=taskfile, project=project, follow_include_for_used_vars=False)
                    if not pbdata_for_this_entry:
                        continue
                    pbdata_arr.append(pbdata_for_this_entry)

    results = []
    for pd in pbdata_arr:
        set_vars, role_vars, used_vars, undefined_vars_in_obj, undefined_vars_value, vars_to_set = resolve_variables(pd)
        result = {
            "entrypoint": pd.object.key,
            "set_vars": set_vars,
            "role_vars": role_vars,
            "used_vars": used_vars,
            "undefined_vars_in_pddata": undefined_vars_in_obj,
            "undefined_vars_value": undefined_vars_value,
            "vars_to_set": vars_to_set 
        }
        results.append(json.dumps(result))

    with open(args.output, "w") as f:
        f.write("\n".join(results))

if __name__ == "__main__":
    main()
