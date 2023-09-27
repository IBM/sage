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

from sage_scan.models import (
    Task,
    Module,
)
from ansible_risk_insight.models import (
    ExecutableType,
    Module as ARIModule,
    ActionGroupMetadata,
    VariableType,
    ArgumentsType,
)

ARGUMENTS_ANNOTATION_KEY = "arguments"
VARIABLES_SET_ANNOTATION_KEY = "variables_set"
VARIABLES_USED_ANNOTATION_KEY = "variables_used"
MODULE_OBJECT_ANNOTATION_KEY = "module_object"


# P001 rule in ARI
def set_module_spec_annotations(task: Task):
    resolved_fqcn = ""
    wrong_module_name = ""
    not_exist = False
    correct_fqcn = ""
    need_correction = False
    module = task.get_annotation(MODULE_OBJECT_ANNOTATION_KEY)
    if module:
        resolved_fqcn = module.fqcn
        correct_fqcn = module.fqcn
    else:
        wrong_module_name = task.module
        not_exist = True

    if correct_fqcn != task.module or not_exist:
        need_correction = True

    module_examples = ""
    if module:
        module_examples = module.examples

    task.set_annotation("module.resolved_fqcn", resolved_fqcn)
    task.set_annotation("module.wrong_module_name", wrong_module_name)
    task.set_annotation("module.not_exist", not_exist)
    task.set_annotation("module.correct_fqcn", correct_fqcn)
    task.set_annotation("module.need_correction", need_correction)
    task.set_annotation("module.examples", module_examples)
    return task


# P002 rule in ARI
def set_module_arg_key_annotations(task: Task, knowledge_base=None):
    module = task.get_annotation(MODULE_OBJECT_ANNOTATION_KEY)
    if task.executable_type == ExecutableType.MODULE_TYPE and module and module.arguments:

        mo = task.module_options
        module_fqcn = module.fqcn
        module_short = ""
        if module_fqcn:
            parts = module_fqcn.split(".")
            if len(parts) <= 2:
                module_short = module_fqcn.split(".")[-1]
            elif len(parts) > 2:
                module_short = ".".join(module_fqcn.split(".")[2:])
        default_args = {}
        if module_short and module_short in task.module_defaults:
            default_args = task.module_defaults[module_short]
        elif module_fqcn and module_fqcn in task.module_defaults:
            default_args = task.module_defaults[module_fqcn]
        else:
            for group_name in task.module_defaults:
                tmp_args = task.module_defaults[group_name]
                found = False
                if not group_name.startswith("group/"):
                    continue
                if knowledge_base:
                    groups = knowledge_base.kb_client.search_action_group(group_name)
                    if not groups:
                        continue
                    for group_dict in groups:
                        if not group_dict:
                            continue
                        if not isinstance(group_dict, dict):
                            continue
                        group = ActionGroupMetadata.from_dict(group_dict)
                        if module_short and module_short in group.group_modules:
                            found = True
                            default_args = tmp_args
                            break
                        elif module_fqcn and module_fqcn in group.group_modules:
                            found = True
                            default_args = tmp_args
                            break
                if found:
                    break

        used_keys = []
        if isinstance(mo, dict):
            used_keys = list(mo.keys())

        available_keys = []
        required_keys = []
        alias_reverse_map = {}
        available_args = None
        wrong_keys = []
        missing_required_keys = []
        if not is_set_fact(module_fqcn):
            if module:
                for arg in module.arguments:
                    available_keys.extend(arg.available_keys())
                    if arg.required:
                        aliases = arg.aliases if arg.aliases else []
                        req_k = {"key": arg.name, "aliases": aliases}
                        required_keys.append(req_k)
                    if arg.aliases:
                        for al in arg.aliases:
                            alias_reverse_map[al] = arg.name
                available_args = module.arguments

            wrong_keys = [key for key in used_keys if key not in available_keys]

            for k in required_keys:
                name = k.get("key", "")
                aliases = k.get("aliases", [])
                if name in used_keys:
                    continue
                if name in default_args:
                    continue
                if aliases:
                    found = False
                    for a_k in aliases:
                        if a_k in used_keys:
                            found = True
                            break
                        if a_k in default_args:
                            found = True
                            break
                    if found:
                        continue
                # here, the required key was not found
                missing_required_keys.append(name)

        used_alias_and_real_keys = []
        for k in used_keys:
            if k not in alias_reverse_map:
                continue
            real_name = alias_reverse_map[k]
            used_alias_and_real_keys.append(
                {
                    "used_alias": k,
                    "real_key": real_name,
                }
            )

        task.set_annotation("module.wrong_arg_keys", wrong_keys)
        task.set_annotation("module.available_arg_keys", available_keys)
        task.set_annotation("module.required_arg_keys", required_keys)
        task.set_annotation("module.missing_required_arg_keys", missing_required_keys)
        # task.set_annotation("module.available_args", available_args)
        # task.set_annotation("module.default_args", default_args)
        task.set_annotation("module.used_alias_and_real_keys", used_alias_and_real_keys)
    return task


# P003 rule in ARI
def set_module_arg_value_annotations(task: Task):
    module = task.get_annotation(MODULE_OBJECT_ANNOTATION_KEY)
    if task.executable_type == ExecutableType.MODULE_TYPE and module and module.arguments:

        wrong_values = []
        undefined_values = []
        unknown_type_values = []
        module_options = task.module_options
        arguments = task.get_annotation(ARGUMENTS_ANNOTATION_KEY)
        if isinstance(module_options, dict):
            for key in module_options:
                raw_value = module_options[key]
                resolved_value = None
                if arguments and len(arguments.templated) >= 1:
                    resolved_value = arguments.templated[0][key]
                spec = None
                for arg_spec in module.arguments:
                    if key == arg_spec.name or (arg_spec.aliases and key in arg_spec.aliases):
                        spec = arg_spec
                        break
                if not spec:
                    continue

                d = {"key": key}
                wrong_val = False
                unknown_type_val = False
                if spec.type:
                    actual_type = ""
                    # if the raw_value is not a variable
                    if not isinstance(raw_value, str) or "{{" not in raw_value:
                        actual_type = type(raw_value).__name__
                    else:
                        # otherwise, check the resolved value
                        # if the variable could not be resovled successfully
                        if isinstance(resolved_value, str) and "{{" in resolved_value:
                            pass
                        elif is_loop_var(raw_value, task):
                            # if the variable is loop var, use the element type as actual type
                            resolved_element = None
                            if resolved_value:
                                if isinstance(resolved_value, list):
                                    resolved_element = resolved_value[0]
                                else:
                                    resolved_element = resolved_value
                            if resolved_element:
                                actual_type = type(resolved_element).__name__
                        else:
                            # otherwise, use the resolved value type as actual type
                            actual_type = type(resolved_value).__name__

                    if actual_type:
                        type_wrong = False
                        if spec.type != "any" and actual_type != spec.type:
                            type_wrong = True
                        elements_type_wrong = False
                        no_elements = False
                        if spec.elements:
                            if spec.elements != "any" and actual_type != spec.elements:
                                elements_type_wrong = True
                        else:
                            no_elements = True
                        if type_wrong and (elements_type_wrong or no_elements):
                            d["expected_type"] = spec.type
                            d["actual_type"] = actual_type
                            d["actual_value"] = raw_value
                            wrong_val = True
                    else:
                        d["expected_type"] = spec.type
                        d["unknown_type_value"] = resolved_value
                        unknown_type_val = True

                if wrong_val:
                    wrong_values.append(d)

                if unknown_type_val:
                    unknown_type_values.append(d)

                sub_args = None
                if arguments and isinstance(arguments, dict):
                    sub_args = arguments.get(key)
                if sub_args:
                    undefined_vars = [v.name for v in sub_args.vars if v and v.type == VariableType.Unknown]
                    if undefined_vars:
                        undefined_values.append({"key": key, "value": raw_value, "undefined_variables": undefined_vars})

        task.set_annotation("module.wrong_arg_values", wrong_values)
        task.set_annotation("module.undefined_values", undefined_values)
        task.set_annotation("module.unknown_type_values", unknown_type_values)
    return task


# P004 rule in ARI
def set_variable_annotations(task: Task):
    undefined_variables = []
    unknown_name_vars = []
    unnecessary_loop = []
    task_arg_keys = []
    arguments = task.get_annotation(ARGUMENTS_ANNOTATION_KEY)
    variable_use = task.get_annotation(VARIABLES_USED_ANNOTATION_KEY)
    if arguments and arguments.type == ArgumentsType.DICT:
        task_arg_keys = list(arguments.raw.keys())
    if variable_use:
        for v_name in variable_use:
            v = variable_use[v_name]
            if v and v[-1].type == VariableType.Unknown:
                if v_name not in undefined_variables:
                    undefined_variables.append(v_name)
                if v_name not in unknown_name_vars and v_name not in task_arg_keys:
                    unknown_name_vars.append(v_name)
                if v_name not in unnecessary_loop:
                    v_str = "{{ " + v_name + " }}"
                    if not is_loop_var(v_str, task):
                        unnecessary_loop.append({"name": v_name, "suggested": v_name.replace("item.", "")})

    task.set_annotation("variable.undefined_vars", undefined_variables)
    task.set_annotation("variable.unknown_name_vars", unknown_name_vars)
    task.set_annotation("variable.unnecessary_loop_vars", unnecessary_loop)
    return task


# remove temporary annotations (to remove large object data)
def omit_object_annotations(task: Task):
    task.delete_annotation(MODULE_OBJECT_ANNOTATION_KEY)
    task.delete_annotation(ARGUMENTS_ANNOTATION_KEY)
    return task


def is_set_fact(module_fqcn):
    return module_fqcn == "ansible.builtin.set_fact"


def is_loop_var(value, task):
    # `item` and alternative loop variable (if any) should not be replaced to avoid breaking loop
    skip_variables = ["item"]
    if task.loop and isinstance(task.loop, dict):
        skip_variables.extend(list(task.loop.keys()))

    _v = value.replace(" ", "")

    for var in skip_variables:
        for _prefix in ["}}", "|", "."]:
            pattern = "{{" + var + _prefix
            if pattern in _v:
                return True
    return False