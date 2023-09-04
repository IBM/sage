import re
from dataclasses import dataclass, field
from sage.models import Playbook, Play, TaskFile, Role, Task, SageObject
from ansible_risk_insight.models import VariableType


variable_block_re = re.compile(r"{{[^}]+}}")


@dataclass
class VariableResolver(object):
    call_seq: list = field(default_factory=list)

    def get_defined_vars(self, object: SageObject):
        obj_and_vars_list = self.set_defined_vars()
        for obj, defnied_vars, _ in obj_and_vars_list:
            if obj.key == object.key:
                return defnied_vars
        return None
    
    def get_used_vars(self, object: SageObject):
        obj_and_vars_list = self.set_used_vars()
        for obj, _, used_vars in obj_and_vars_list:
            if obj.key == object.key:
                return used_vars
        return None

    def set_defined_vars(self, set_annotation=False):
        obj_and_vars_list = self.traverse(resolve_value=False, set_annotation=set_annotation)
        return obj_and_vars_list
    
    def set_used_vars(self, set_annotation=False):
        obj_and_vars_list = self.traverse(resolve_value=True, set_annotation=set_annotation)
        return obj_and_vars_list

    def update_defined_vars(self, vars_dict, variables, precedence):
        if not variables:
            return
        if not isinstance(variables, dict):
            return
        for key, value in variables.items():
            if key in vars_dict:
                current_precedence = vars_dict[key][1]
                if precedence >= current_precedence:
                    vars_dict[key] = (value, precedence)
            else:
                vars_dict[key] = (value, precedence)
        return

    def traverse(self, resolve_value=False, set_annotation=False):
        defined_vars = {}
        registered_vars = {}
        used_vars = {}
        obj_and_vars_list = []
        for obj in self.call_seq:
            # defined variables
            if isinstance(obj, Playbook):
                self.update_defined_vars(defined_vars, obj.variables, VariableType.PlaybookGroupVarsAll)
            elif isinstance(obj, Play):
                self.update_defined_vars(defined_vars, obj.variables, VariableType.PlayVars)
            elif isinstance(obj, Role):
                self.update_defined_vars(defined_vars, obj.default_variables, VariableType.RoleDefaults)
                self.update_defined_vars(defined_vars, obj.variables, VariableType.RoleVars)
            elif isinstance(obj, TaskFile):
                pass
                # self.update_defined_vars(defined_vars, obj.variables, VariableType.TaskVars)
            elif isinstance(obj, Task):
                self.update_defined_vars(defined_vars, obj.variables, VariableType.TaskVars)
                self.update_defined_vars(defined_vars, obj.set_facts, VariableType.SetFacts)
                registered_vars.update(obj.registered_variables)

            # used variables
            new_used_vars = {}
            if isinstance(obj, Task):
                used_vars_in_task = extract_variables(obj.module_options)
                for var_name in used_vars_in_task:
                    if var_name not in used_vars:
                        new_used_vars[var_name] = None
                
            # make a copy of defined_vars because it is updated by the next object in the sequence
            # and we remove precedence info here
            defined_vars_key_value = {k: v[0] for k, v in defined_vars.items()}

            if resolve_value:
                resolved_new_used_vars = self.resolve(new_used_vars, defined_vars_key_value, registered_vars)
                used_vars.update(resolved_new_used_vars)

            obj_and_vars_list.append((obj, defined_vars_key_value, used_vars))

            if set_annotation:
                obj.annotations["defined_vars"] = defined_vars_key_value
                obj.annotations["used_vars"] = used_vars
        return obj_and_vars_list
    

    def resolve(self, used_vars, defined_vars, registered_vars=None):
        resolved_used_vars = {}
        flat_vars_dict = flatten_vars_dict(defined_vars)
        for var_name in used_vars:
            var_value, found, skip = resolve_var(var_name, flat_vars_dict, registered_vars)

            if not found:
                var_value = make_value_placeholder(var_name)

            if not skip:
                resolved_used_vars = self.update_resolved_vars_dict(resolved_used_vars, var_name, var_value)
        return resolved_used_vars
    
    def update_resolved_vars_dict(self, vars_dict, var_name, var_value):
        def _recursive_update(d, keys, value):
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
                new_d[key] = _recursive_update(new_d[key], rest_keys, value)
            return new_d

        updated = vars_dict.copy()
        if "." in var_name:
            parts = var_name.split(".")
            updated = _recursive_update(updated, parts, var_value)
        else:
            updated[var_name] = var_value
        return updated


def make_value_placeholder(var_name: str):
    if "." in var_name:
        var_name = var_name.replace(".", "_")
    return "{{ " + var_name + " }}"
    

def resolve_var(var_name, flat_vars_dict, registered_vars=None):
    var_value = None
    found = False
    skip = False
    if var_name in flat_vars_dict:
        var_value = flat_vars_dict[var_name]
        found = True
    
    if found:
        if isinstance(var_value, str):
            var_value, skip = render_variable(var_value, flat_vars_dict, registered_vars)
            # var_value, skip = render_variable(var_value, flat_vars_dict)
    else:
        root_var_name = var_name.split(".")[0]
        root_var_value = None
        if root_var_name in flat_vars_dict:
            root_var_value = flat_vars_dict[root_var_name]
        if isinstance(registered_vars, dict):
            # if root_var is a registered_var, this variable should be skipped
            if root_var_name in registered_vars:
                skip = True
            else:
                # if root_var is using a registered_var, this variable should be skipped
                if isinstance(root_var_value, str):
                    _, using_reg_var = render_variable(root_var_value, flat_vars_dict, registered_vars)
                    if using_reg_var:
                        skip = True

    return var_value, found, skip
        

def flatten_vars_dict(vars_dict: dict, _prefix: str = ""):
    flat_vars_dict = {}
    for k, v in vars_dict.items():
        if isinstance(v, dict):
            flat_var_name = f"{_prefix}{k}"
            flat_vars_dict.update({flat_var_name: v})
            new_prefix = f"{flat_var_name}."
            _tmp = flatten_vars_dict(v, new_prefix)
            flat_vars_dict.update(_tmp)
        else:
            flat_key = f"{_prefix}{k}"
            flat_vars_dict.update({flat_key: v})
    return flat_vars_dict


def extract_variables(data: any):
    variables = []
    str_arg_values = list_str_values(data)
    for txt in str_arg_values:
        var_block_info_list = extract_variable_names(txt)
        for var_info in var_block_info_list:
            if not isinstance(var_info, dict):
                continue
            var_name = var_info.get("name", None)
            if not var_name:
                continue
            if var_name not in variables:
                variables.append(var_name)
    return variables


def list_str_values(data: any):
    str_values = []
    if isinstance(data, dict):
        for v in data.values():
            _tmp = list_str_values(v)
            str_values.extend(_tmp)
    elif isinstance(data, list):
        for v in data:
            _tmp = list_str_values(v)
            str_values.extend(_tmp)
    elif isinstance(data, str):
        str_values.append(data)
    else:
        pass
    return str_values


def render_variable(txt, flat_vars_dict, registered_vars=None):
    original_txt = f"{txt}"
    processing_txt = f"{txt}"
    var_block_info_list = extract_variable_names(processing_txt)
    skip = False
    for var_info in var_block_info_list:
        if not isinstance(var_info, dict):
            continue
        orig_var_str = var_info.get("original", None)
        if not orig_var_str:
            continue
        var_name = var_info.get("name", None)

        root_var_name = var_name.split(".")[0]
        if isinstance(registered_vars, dict):
            if root_var_name in registered_vars:
                skip = True
        
        if var_name not in flat_vars_dict:
            continue
        var_value = flat_vars_dict[var_name]
        var_value_str = f"{var_value}"
        processing_txt = processing_txt.replace(orig_var_str, var_value_str)
    if processing_txt == original_txt:
        return processing_txt, skip
    if "{{" in processing_txt:
        return render_variable(processing_txt, flat_vars_dict)
    return processing_txt, skip
    

def extract_variable_names(txt):
    if not variable_block_re.search(txt):
        return []
    found_var_blocks = variable_block_re.findall(txt)
    blocks = []
    for b in found_var_blocks:
        parts = b.split("|")
        var_name = ""
        default_var_name = ""
        for i, p in enumerate(parts):
            if i == 0:
                var_name = p.replace("{{", "").replace("}}", "").replace(" ", "")
                if "lookup(" in var_name and "first_found" in var_name:
                    var_name = var_name.split(",")[-1].replace(")", "")
            else:
                if "default(" in p and ")" in p:
                    default_var = p.replace("}}", "").replace("default(", "").replace(")", "").replace(" ", "")
                    if not default_var.startswith('"') and not default_var.startswith("'") and not re.compile(r"[0-9].*").match(default_var):
                        default_var_name = default_var
        tmp_b = {
            "original": b,
        }
        if var_name == "":
            continue
        tmp_b["name"] = var_name
        if default_var_name != "":
            tmp_b["default"] = default_var_name
        blocks.append(tmp_b)
    return blocks