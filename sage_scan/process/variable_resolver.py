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

import re
import copy
from pathlib import Path
from dataclasses import dataclass, field
from sage_scan.models import (
    Collection,
    Playbook,
    Play,
    TaskFile,
    Role,
    Task,
    SageObject,
    SageProject,
)
from sage_scan.process.annotations import (
    ARGUMENTS_ANNOTATION_KEY,
    VARIABLES_SET_ANNOTATION_KEY,
    VARIABLES_USED_ANNOTATION_KEY,
    is_loop_var,
)
from ansible_risk_insight.models import (
    Variable,
    VariableType,
    BecomeInfo,
    InventoryType,
    Arguments,
    ArgumentsType,
    immutable_var_types,
)


variable_block_re = re.compile(r"{{[^}]+}}")
p = Path(__file__).resolve().parent
ansible_special_variables = [line.replace("\n", "") for line in open(p / "ansible_variables.txt", "r").read().splitlines()]
variable_block_re = re.compile(r"{{[^}]+}}")


@dataclass
class VariableResolver(object):

    def resolve_all_vars_in_project(self, project: SageProject):
        all_call_sequences = project.get_all_call_sequences()
        for call_seq in all_call_sequences:
            self.traverse(call_seq=call_seq)
        return project

    def get_defined_vars(self, object: SageObject, call_seq: list):
        obj_and_vars_list = self.set_defined_vars(call_seq=call_seq)
        for obj, defnied_vars, _ in obj_and_vars_list:
            if obj.key == object.key:
                return defnied_vars
        return {}
    
    def get_used_vars(self, object: SageObject, call_seq: list):
        obj_and_vars_list = self.set_used_vars(call_seq=call_seq)
        for obj, _, used_vars in obj_and_vars_list:
            if obj.key == object.key:
                return used_vars
        return {}

    def set_defined_vars(self, call_seq: list):
        obj_and_vars_list = self.traverse(call_seq=call_seq)
        return obj_and_vars_list
    
    def set_used_vars(self, call_seq: list):
        obj_and_vars_list = self.traverse(call_seq=call_seq)
        return obj_and_vars_list

    def traverse(self, call_seq: list):
        context = VariableContext()
        obj_and_vars_list = []
        for obj in call_seq:
            context.add(obj)
            if isinstance(obj, Task):
                task = obj
                resolved = resolve_module_options(context, task)
                resolved_module_options = resolved[0]
                resolved_variables = resolved[1]
                used_variables = resolved[3]

                _vars = []
                is_mutable = False
                for rv in resolved_variables:
                    v_name = rv.get("key", "")
                    v_value = rv.get("value", "")
                    v_type = rv.get("type", VariableType.Unknown)
                    elements = []
                    if v_name in used_variables:
                        if not isinstance(used_variables[v_name], dict):
                            continue
                        for u_v_name, info in used_variables[v_name].items():
                            if u_v_name == v_name:
                                continue
                            u_v_value = info.get("value", "")
                            u_v_type = info.get("type", VariableType.Unknown)
                            u_v = Variable(
                                name=u_v_name,
                                value=u_v_value,
                                type=u_v_type,
                                used_in=task.key,
                            )
                            elements.append(u_v)
                    v = Variable(
                        name=v_name,
                        value=v_value,
                        type=v_type,
                        elements=elements,
                        used_in=task.key,
                    )
                    _vars.append(v)
                    if v.is_mutable:
                        is_mutable = True

                for v in _vars:
                    history = context.var_use_history.get(v.name, [])
                    history.append(v)
                    context.var_use_history[v.name] = history

                m_opts = task.module_options
                if isinstance(m_opts, list):
                    args_type = ArgumentsType.LIST
                elif isinstance(m_opts, dict):
                    args_type = ArgumentsType.DICT
                else:
                    args_type = ArgumentsType.SIMPLE
                arguments = Arguments(
                    type=args_type,
                    raw=m_opts,
                    vars=_vars,
                    resolved=True,  # TODO: False if not resolved
                    templated=resolved_module_options,
                    is_mutable=is_mutable,
                )
                # deep copy the history here because the context is updated by subsequent taskcalls
                defined_vars = copy.deepcopy(context.var_set_history)
                used_vars = copy.deepcopy(context.var_use_history)
                task.set_annotation(VARIABLES_SET_ANNOTATION_KEY, defined_vars)
                task.set_annotation(VARIABLES_USED_ANNOTATION_KEY, used_vars)
                task.set_annotation(ARGUMENTS_ANNOTATION_KEY, arguments)

                defined_vars_key_value = {k: v[0].value for k, v in defined_vars.items() if v and isinstance(v[0], Variable)}
                used_vars_key_value = {}
                for k, v in used_vars.items():
                    if not v:
                        continue
                    _var = v[0]
                    if not isinstance(_var, Variable):
                        continue

                    # skip if this var is registered one
                    parent_var_name = _var.name
                    if "." in parent_var_name:
                        parent_var_name = parent_var_name.split(".")[0]
                    is_registered_var = False
                    for p, q in defined_vars.items():
                        if not q:
                            continue
                        _var_q = q[0]
                        if not isinstance(_var_q, Variable):
                            continue
                        if _var_q.name == parent_var_name and _var_q.type == VariableType.RegisteredVars:
                            is_registered_var = True
                            break
                    if is_registered_var:
                        continue

                    # skip loop var by type
                    if _var.type == VariableType.LoopVars:
                        continue

                    # skip loop var by name
                    # (this may be removed in the future because the type check above could be enough)
                    var_block = "{{ " + k + " }}"
                    if is_loop_var(var_block, task):
                        continue
                    
                    value = _var.value
                    if _var.type == VariableType.Unknown:
                        value = make_value_placeholder(k)
                    used_vars_key_value[k] = value
                    
                obj_and_vars_list.append((obj, defined_vars_key_value, used_vars_key_value))
            else:
                last_defined = {}
                last_used = {}
                if obj_and_vars_list:
                    _, last_defined, last_used = obj_and_vars_list[-1]
                obj_and_vars_list.append((obj, last_defined, last_used))
        return obj_and_vars_list
    
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


def extract_variable_names(txt):
    if not variable_block_re.search(txt):
        return []
    found_var_blocks = variable_block_re.findall(txt)
    blocks = []
    for b in found_var_blocks:
        if "lookup(" in b.replace(" ", ""):
            continue
        parts = b.split("|")
        var_name = ""
        default_var_name = ""
        for i, p in enumerate(parts):
            if i == 0:
                var_name = p.replace("{{", "").replace("}}", "")
                if " if " in var_name and " else " in var_name:
                    # this block is not just a variable, but an expression
                    # we need to split this with a space to get its elements
                    skip_elements = ["if", "else", "+", "is", "defined"]
                    sub_parts = var_name.split(" ")
                    for sp in sub_parts:
                        if not sp:
                            continue
                        if sp and sp in skip_elements:
                            continue
                        if sp and sp[0] in ['"', "'"]:
                            continue
                        var_name = sp
                        break
                var_name = var_name.replace(" ", "")
                if "lookup(" in var_name and "first_found" in var_name:
                    var_name = var_name.split(",")[-1].replace(")", "")
                if var_name and var_name[0] == "(":
                    var_name = var_name.split(")")[0].replace("(", "")
                if "+" in var_name:
                    sub_parts = var_name.split("+")
                    for sp in sub_parts:
                        if not sp:
                            continue
                        if sp and sp[0] in ['"', "'"]:
                            continue
                        var_name = sp
                        break
                if "[" in var_name and "." not in var_name:
                    # extract dict/list name
                    dict_pattern = r'(\w+)\[(\'|").*(\'|")\]'
                    match = re.search(dict_pattern, var_name)
                    if match:
                        matched_str = match.group(1)
                        var_name = matched_str.split("[")[0]
                    list_pattern = r'(\w+)\[\-?\d+\]'
                    match = re.search(list_pattern, var_name)
                    if match:
                        matched_str = match.group(1)
                        var_name = matched_str.split("[")[0]
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


def resolved_vars_contains(resolved_vars, new_var):
    if not isinstance(new_var, dict):
        return False
    new_var_key = new_var.get("key", "")
    if new_var_key == "":
        return False
    if not isinstance(resolved_vars, list):
        return False
    for var in resolved_vars:
        if not isinstance(var, dict):
            continue
        var_key = var.get("key", "")
        if var_key == "":
            continue
        if var_key == new_var_key:
            return True
    return False


@dataclass
class VariableContext:
    keep_obj: bool = False
    variables: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    inventories: list = field(default_factory=list)
    role_defaults: list = field(default_factory=list)
    role_vars: list = field(default_factory=list)
    registered_vars: list = field(default_factory=list)
    set_facts: list = field(default_factory=list)
    task_vars: list = field(default_factory=list)

    become: BecomeInfo = None
    module_defaults: dict = field(default_factory=dict)

    var_set_history: dict = field(default_factory=dict)
    var_use_history: dict = field(default_factory=dict)

    _flat_vars: dict = field(default_factory=dict)

    def add(self, obj):
        _spec = None
        if isinstance(obj, SageObject):
            _spec = obj
        # variables
        if isinstance(_spec, Playbook):
            self.variables.update(_spec.variables)
            self.update_flat_vars(_spec.variables)
            for key, val in _spec.variables.items():
                current = self.var_set_history.get(key, [])
                current.append(Variable(name=key, value=val, type=VariableType.PlaybookGroupVarsAll, setter=_spec.key))
                self.var_set_history[key] = current
        elif isinstance(_spec, Play):
            self.variables.update(_spec.variables)
            self.update_flat_vars(_spec.variables)
            for key, val in _spec.variables.items():
                current = self.var_set_history.get(key, [])
                current.append(Variable(name=key, value=val, type=VariableType.PlayVars, setter=_spec.key))
                self.var_set_history[key] = current
            if _spec.become:
                self.become = _spec.become
            if _spec.module_defaults:
                self.module_defaults = _spec.module_defaults
        elif isinstance(_spec, Role):
            self.variables.update(_spec.default_variables)
            self.update_flat_vars(_spec.default_variables)
            self.variables.update(_spec.variables)
            self.update_flat_vars(_spec.variables)
            for var_name in _spec.default_variables:
                self.role_defaults.append(var_name)
            for var_name in _spec.variables:
                self.role_vars.append(var_name)
            for key, val in _spec.default_variables.items():
                current = self.var_set_history.get(key, [])
                current.append(Variable(name=key, value=val, type=VariableType.RoleDefaults, setter=_spec.key))
                self.var_set_history[key] = current
            for key, val in _spec.variables.items():
                current = self.var_set_history.get(key, [])
                current.append(Variable(name=key, value=val, type=VariableType.RoleVars, setter=_spec.key))
                self.var_set_history[key] = current
        elif isinstance(_spec, Collection):
            self.variables.update(_spec.variables)
            self.update_flat_vars(_spec.variables)
        elif isinstance(_spec, TaskFile):
            self.variables.update(_spec.variables)
            self.update_flat_vars(_spec.variables)
        elif isinstance(_spec, Task):
            self.variables.update(_spec.variables)
            self.update_flat_vars(_spec.variables)
            self.variables.update(_spec.registered_variables)
            self.update_flat_vars(_spec.registered_variables)
            self.variables.update(_spec.set_facts)
            self.update_flat_vars(_spec.set_facts)
            for var_name in _spec.registered_variables:
                self.registered_vars.append(var_name)
            for var_name in _spec.set_facts:
                self.set_facts.append(var_name)
            for key, val in _spec.variables.items():
                current = self.var_set_history.get(key, [])
                current.append(Variable(name=key, value=val, type=VariableType.TaskVars, setter=_spec.key))
                self.var_set_history[key] = current
            for key, val in _spec.registered_variables.items():
                current = self.var_set_history.get(key, [])
                current.append(Variable(name=key, value=val, type=VariableType.RegisteredVars, setter=_spec.key))
                self.var_set_history[key] = current
            for key, val in _spec.set_facts.items():
                current = self.var_set_history.get(key, [])
                current.append(Variable(name=key, value=val, type=VariableType.SetFacts, setter=_spec.key))
                self.var_set_history[key] = current
            if _spec.become:
                self.become = _spec.become
            if _spec.module_defaults:
                self.module_defaults = _spec.module_defaults
        else:
            # Module
            return
        self.options.update(_spec.options)

    def resolve_variable(self, var_name, resolve_history={}):
        if var_name in resolve_history:
            val = resolve_history[var_name].get("value", None)
            v_type = resolve_history[var_name].get("type", VariableType.Unknown)
            return val, v_type, resolve_history

        _resolve_history = resolve_history.copy()

        v_type = None
        if var_name in ansible_special_variables:
            v_type = VariableType.HostFacts
            return None, v_type, resolve_history

        if var_name in self.role_vars:
            v_type = VariableType.RoleVars
        elif var_name in self.role_defaults:
            v_type = VariableType.RoleDefaults
        elif var_name in self.registered_vars:
            v_type = VariableType.RegisteredVars
        elif var_name in self.set_facts:
            v_type = VariableType.SetFacts
        else:
            v_type = VariableType.TaskVars

        val = self.variables.get(var_name, None)
        if val is not None:
            _resolve_history[var_name] = {"value": val, "type": v_type}

            if isinstance(val, str):
                resolved_val, _resolve_history = self.resolve_single_variable(val, _resolve_history)
                return resolved_val, v_type, _resolve_history
            elif isinstance(val, list):
                resolved_val_list = []
                for vi in val:
                    resolved_val, _resolve_history = self.resolve_single_variable(vi, _resolve_history)
                    resolved_val_list.append(resolved_val)
                return resolved_val_list, v_type, _resolve_history
            else:
                return val, v_type, _resolve_history

        val = self._flat_vars.get(var_name, None)
        if val is not None:
            _resolve_history[var_name] = {"value": val, "type": v_type}

            if isinstance(val, str):
                resolved_val, _resolve_history = self.resolve_single_variable(val, _resolve_history)
                return resolved_val, v_type, _resolve_history
            elif isinstance(val, list):
                resolved_val_list = []
                for vi in val:
                    resolved_val, _resolve_history = self.resolve_single_variable(vi, _resolve_history)
                    resolved_val_list.append(resolved_val)
                return resolved_val_list, v_type, _resolve_history
            else:
                return val, v_type, _resolve_history

        # TODO: consider group
        inventory_for_all = [iv for iv in self.inventories if iv.inventory_type == InventoryType.GROUP_VARS_TYPE and iv.name == "all"]
        for iv in inventory_for_all:
            iv_var_dict = flatten_vars_dict(iv.variables)
            val = iv_var_dict.get(var_name, None)

            if val is not None:
                _resolve_history[var_name] = {"value": val, "type": v_type}
                v_type = VariableType.InventoryGroupVarsAll
                if isinstance(val, str):
                    resolved_val, _resolve_history = self.resolve_single_variable(val, _resolve_history)
                    return resolved_val, v_type, _resolve_history
                elif isinstance(val, list):
                    resolved_val_list = []
                    for vi in val:
                        resolved_val, _resolve_history = self.resolve_single_variable(vi, _resolve_history)
                        resolved_val_list.append(resolved_val)
                    return resolved_val_list, v_type, _resolve_history
                else:
                    return val, v_type, _resolve_history

        _resolve_history[var_name] = {"value": None, "type": VariableType.Unknown}

        return None, VariableType.Unknown, _resolve_history

    def resolve_single_variable(self, txt, resolve_history=[]):
        new_history = resolve_history.copy()
        if not isinstance(txt, str):
            return txt, new_history
        if "{{" in txt:
            var_names_in_txt = extract_variable_names(txt)
            if len(var_names_in_txt) == 0:
                return txt, new_history
            resolved_txt = txt
            for var_name_in_txt in var_names_in_txt:
                original_block = var_name_in_txt.get("original", "")
                var_name = var_name_in_txt.get("name", "")
                default_var_name = var_name_in_txt.get("default", "")
                var_val_in_txt, _, new_history = self.resolve_variable(var_name, new_history)
                if var_val_in_txt is None and default_var_name != "":
                    var_val_in_txt, _, new_history = self.resolve_variable(default_var_name, new_history)
                if var_val_in_txt is None:
                    return resolved_txt, new_history
                if txt == original_block:
                    return var_val_in_txt, new_history
                resolved_txt = resolved_txt.replace(original_block, str(var_val_in_txt))
            return resolved_txt, new_history
        else:
            return txt, new_history

    def update_flat_vars(self, new_vars: dict, _prefix: str = ""):
        for k, v in new_vars.items():
            if isinstance(v, dict):
                flat_var_name = f"{_prefix}{k}"
                self._flat_vars.update({flat_var_name: v})
                new_prefix = f"{flat_var_name}."
                self.update_flat_vars(v, new_prefix)
            else:
                flat_key = f"{_prefix}{k}"
                self._flat_vars.update({flat_key: v})
        return

    def copy(self):
        return VariableContext(
            keep_obj=self.keep_obj,
            variables=copy.copy(self.variables),
            options=copy.copy(self.options),
            inventories=copy.copy(self.inventories),
            role_defaults=copy.copy(self.role_defaults),
            role_vars=copy.copy(self.role_vars),
            registered_vars=copy.copy(self.registered_vars),
        )
        # return copy.deepcopy(self)



def resolve_module_options(context: VariableContext, task: Task):
    resolved_vars = []
    variables_in_loop = []
    used_variables = {}
    if len(task.loop) == 0:
        variables_in_loop = [{}]
    else:
        loop_key = list(task.loop.keys())[0]
        loop_values = task.loop.get(loop_key, [])
        new_var = {
            "key": loop_key,
            "value": loop_values,
            "type": VariableType.LoopVars,
        }
        if not resolved_vars_contains(resolved_vars, new_var):
            resolved_vars.append(new_var)
        if isinstance(loop_values, str):
            var_names = extract_variable_names(loop_values)
            if len(var_names) == 0:
                variables_in_loop.append({loop_key: loop_values})
            else:
                var_name = var_names[0].get("name", "")
                resolved_vars_in_item, v_type, resolve_history = context.resolve_variable(var_name)
                used_variables[var_name] = resolve_history
                new_var = {
                    "key": var_name,
                    "value": resolved_vars_in_item,
                    "type": v_type,
                }
                if not resolved_vars_contains(resolved_vars, new_var):
                    resolved_vars.append(new_var)
                if isinstance(resolved_vars_in_item, list):
                    for vi in resolved_vars_in_item:
                        variables_in_loop.append(
                            {
                                loop_key: vi,
                                "__v_type__": v_type,
                                "__v_name__": var_name,
                            }
                        )
                if isinstance(resolved_vars_in_item, dict):
                    for vi_key, vi_value in resolved_vars_in_item.items():
                        variables_in_loop.append(
                            {
                                loop_key + ".key": vi_key,
                                loop_key + ".value": vi_value,
                                "__v_type__": v_type,
                            }
                        )
                else:
                    variables_in_loop.append(
                        {
                            loop_key: resolved_vars_in_item,
                            "__v_type__": v_type,
                            "__v_name__": var_name,
                        }
                    )
        elif isinstance(loop_values, list):
            for v in loop_values:
                if isinstance(v, str) and variable_block_re.search(v):
                    var_names = extract_variable_names(v)
                    if len(var_names) == 0:
                        variables_in_loop.append({loop_key: v})
                        continue
                    var_name = var_names[0].get("name", "")
                    resolved_vars_in_item, v_type, resolve_history = context.resolve_variable(var_name)
                    used_variables[var_name] = resolve_history
                    new_var = {
                        "key": var_name,
                        "value": resolved_vars_in_item,
                        "type": v_type,
                    }
                    if not resolved_vars_contains(resolved_vars, new_var):
                        resolved_vars.append(new_var)
                    if not isinstance(resolved_vars_in_item, list):
                        variables_in_loop.append(
                            {
                                loop_key: resolved_vars_in_item,
                                "__v_type__": v_type,
                                "__v_name__": var_name,
                            }
                        )
                        continue
                    for vi in resolved_vars_in_item:
                        variables_in_loop.append(
                            {
                                loop_key: vi,
                                "__v_type__": v_type,
                                "__v_name__": var_name,
                            }
                        )
                else:
                    if isinstance(v, dict):
                        tmp_variables = {}
                        for k2, v2 in v.items():
                            key = "{}.{}".format(loop_key, k2)
                            tmp_variables.update({key: v2})
                        variables_in_loop.append(tmp_variables)
                    else:
                        variables_in_loop.append({loop_key: v})
        elif isinstance(loop_values, dict):
            tmp_variables = {}
            for k, v in loop_values.items():
                key = "{}.{}".format(loop_key, k)
                tmp_variables.update({key: v})
            variables_in_loop.append(tmp_variables)
        else:
            if loop_values:
                raise ValueError("loop_values of type {} is not supported yet".format(type(loop_values).__name__))

    resolved_opts_in_loop = []
    mutable_vars_per_mo = {}
    for variables in variables_in_loop:
        resolved_opts = None
        if isinstance(task.module_options, dict):
            resolved_opts = {}
            for (
                module_opt_key,
                module_opt_val,
            ) in task.module_options.items():
                if not isinstance(module_opt_val, str):
                    resolved_opts[module_opt_key] = module_opt_val
                    continue
                if not variable_block_re.search(module_opt_val):
                    resolved_opts[module_opt_key] = module_opt_val
                    continue
                # if variables are used in the module option value string
                var_names = extract_variable_names(module_opt_val)
                resolved_opt_val = module_opt_val
                for var_name_dict in var_names:
                    original_block = var_name_dict.get("original", "")
                    var_name = var_name_dict.get("name", "")
                    default_var_name = var_name_dict.get("default", "")
                    resolved_var_val = variables.get(var_name, None)
                    if resolved_var_val is not None:
                        loop_var_type = variables.get("__v_type__", VariableType.Unknown)
                        loop_var_name = variables.get("__v_name__", "")
                        if loop_var_type not in immutable_var_types:
                            if module_opt_key not in mutable_vars_per_mo:
                                mutable_vars_per_mo[module_opt_key] = []
                            mutable_vars_per_mo[module_opt_key].append(loop_var_name)
                    if resolved_var_val is None:
                        resolved_var_val, v_type, resolve_history = context.resolve_variable(var_name)
                        used_variables[var_name] = resolve_history
                        if resolved_var_val is not None:
                            new_var = {
                                "key": var_name,
                                "value": resolved_var_val,
                                "type": v_type,
                            }
                            if not resolved_vars_contains(resolved_vars, new_var):
                                resolved_vars.append(new_var)
                            if v_type not in immutable_var_types:
                                if module_opt_key not in mutable_vars_per_mo:
                                    mutable_vars_per_mo[module_opt_key] = []
                                mutable_vars_per_mo[module_opt_key].append(var_name)
                    if resolved_var_val is None and default_var_name != "":
                        resolved_var_val, v_type, resolve_history = context.resolve_variable(default_var_name)
                        used_variables[default_var_name] = resolve_history
                        if resolved_var_val is not None:
                            new_var = {
                                "key": default_var_name,
                                "value": resolved_var_val,
                                "type": v_type,
                            }
                            if not resolved_vars_contains(resolved_vars, new_var):
                                resolved_vars.append(new_var)
                            if v_type not in immutable_var_types:
                                if module_opt_key not in mutable_vars_per_mo:
                                    mutable_vars_per_mo[module_opt_key] = []
                                mutable_vars_per_mo[module_opt_key].append(var_name)
                    if resolved_var_val is None:
                        new_var = {
                            "key": var_name,
                            "value": None,
                            "type": v_type,
                        }
                        if not resolved_vars_contains(resolved_vars, new_var):
                            resolved_vars.append(new_var)
                        continue
                    if resolved_opt_val == original_block:
                        resolved_opt_val = resolved_var_val
                        break
                    resolved_opt_val = resolved_opt_val.replace(original_block, str(resolved_var_val))
                resolved_opts[module_opt_key] = resolved_opt_val
        elif isinstance(task.module_options, str):
            resolved_opt_val = task.module_options
            if variable_block_re.search(resolved_opt_val):
                var_names = extract_variable_names(task.module_options)
                for var_name_dict in var_names:
                    original_block = var_name_dict.get("original", "")
                    var_name = var_name_dict.get("name", "")
                    default_var_name = var_name_dict.get("default", "")
                    resolved_var_val = variables.get(var_name, None)
                    if resolved_var_val is not None:
                        loop_var_type = variables.get("__v_type__", VariableType.Unknown)
                        loop_var_name = variables.get("__v_name__", "")
                        if loop_var_type not in immutable_var_types:
                            if "" not in mutable_vars_per_mo:
                                mutable_vars_per_mo[""] = []
                            mutable_vars_per_mo[""].append(loop_var_name)
                    if resolved_var_val is None:
                        resolved_var_val, v_type, resolve_history = context.resolve_variable(var_name)
                        used_variables[var_name] = resolve_history
                        if resolved_var_val is not None:
                            new_var = {
                                "key": var_name,
                                "value": resolved_var_val,
                                "type": v_type,
                            }
                            if not resolved_vars_contains(resolved_vars, new_var):
                                resolved_vars.append(new_var)
                            if v_type not in immutable_var_types:
                                if "" not in mutable_vars_per_mo:
                                    mutable_vars_per_mo[""] = []
                                mutable_vars_per_mo[""].append(var_name)
                    if resolved_var_val is None and default_var_name != "":
                        resolved_var_val, v_type, resolve_history = context.resolve_variable(default_var_name)
                        used_variables[default_var_name] = resolve_history
                        if resolved_var_val is not None:
                            new_var = {
                                "key": default_var_name,
                                "value": resolved_var_val,
                                "type": v_type,
                            }
                            if not resolved_vars_contains(resolved_vars, new_var):
                                resolved_vars.append(new_var)
                            if v_type not in immutable_var_types:
                                if "" not in mutable_vars_per_mo:
                                    mutable_vars_per_mo[""] = []
                                mutable_vars_per_mo[""].append(var_name)
                    if resolved_var_val is None:
                        new_var = {
                            "key": var_name,
                            "value": None,
                            "type": v_type,
                        }
                        if not resolved_vars_contains(resolved_vars, new_var):
                            resolved_vars.append(new_var)
                        continue
                    if resolved_opt_val == original_block:
                        resolved_opt_val = resolved_var_val
                        break
                    resolved_opt_val = resolved_opt_val.replace(original_block, str(resolved_var_val))
            resolved_opts = resolved_opt_val
        else:
            resolved_opts = task.module_options
        resolved_opts_in_loop.append(resolved_opts)
    return resolved_opts_in_loop, resolved_vars, mutable_vars_per_mo, used_variables