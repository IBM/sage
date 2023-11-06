from dataclasses import dataclass, field
from sage_scan.models import Task
from ansible_risk_insight.models import RoleInPlay
import ansible_risk_insight.yaml as ariyaml
from ruamel.yaml.scalarstring import DoubleQuotedScalarString


def recursive_str_to_ruamel_quotated_str(v: any):
    if isinstance(v, dict):
        for key, val in v.items():
            new_val = recursive_str_to_ruamel_quotated_str(val)
            v[key] = new_val
    elif isinstance(v, list):
        for i, val in enumerate(v):
            new_val = recursive_str_to_ruamel_quotated_str(val)
            v[i] = new_val
    elif isinstance(v, str):
        if v.startswith("{{") and v.endswith("}}"):
            v = DoubleQuotedScalarString(v)
    else:
        pass
    return v


def task_obj_to_data(task: Task):
    data = {}
    if task.name:
        data["name"] = task.name
    
    module_name = task.module
    if task.annotations and isinstance(task.annotations, dict):
        module_name = task.annotations.get("module_fqcn", module_name)
    
    if module_name:
        data[module_name] = task.module_options    

    if task.options and isinstance(task.options, dict):
        for k, v in task.options.items():
            if k == "name":
                continue
            data[k] = v
    return data


def role_in_play_obj_to_data(rip: RoleInPlay):
    data = {}
    if rip.options and isinstance(rip.options, dict):
        data["role"] = rip.name
        for k, v in rip.options.items():
            if k not in data:
                data[k] = v
    else:
        data = rip.name
    return data


def _remove_top_level_offset(txt: str):
    lines = txt.splitlines()
    if len(lines) == 0:
        return txt
    top_level_offset = len(lines[0]) - len(lines[0].lstrip())
    new_lines = []
    for line in lines:
        if len(line) <= top_level_offset:
            new_lines.append("")
        else:
            new_line = line[top_level_offset:]
            new_lines.append(new_line)
    return "\n".join(new_lines)


@dataclass
class PlaybookGenerator(object):
    
    plays_and_tasks: list = field(default_factory=list)
    vars: dict = field(default_factory=dict)
    
    _yaml: str = ""

    def yaml(self):

        playbook_data = []
        for (play, tasks, pre_tasks, post_tasks, handler_tasks) in self.plays_and_tasks:

            play_data = {}
            if play.name:
                play_data["name"] = play.name
            play_data.update(play.options)
            vars = {}
            if play.variables:
                vars = play.variables
            for k, v in self.vars.items():
                vars[k] = v
            if vars:
                play_data["vars"] = vars
            pre_tasks = [task_obj_to_data(t) for t in pre_tasks]
            if pre_tasks:
                play_data["pre_tasks"] = pre_tasks
            tasks = [task_obj_to_data(t) for t in tasks]
            if tasks:
                play_data["tasks"] = tasks
            post_tasks = [task_obj_to_data(t) for t in post_tasks]
            if post_tasks:
                play_data["post_tasks"] = post_tasks
            handler_tasks = [task_obj_to_data(t) for t in handler_tasks]
            if handler_tasks:
                play_data["handlers"] = handler_tasks

            roles = [role_in_play_obj_to_data(rip) for rip in play.roles]
            roles = [r for r in roles if r]
            if roles:       
                play_data["roles"] = roles

            if play.import_playbook:
                play_data["import_playbook"] = play.import_playbook

            if play_data:
                playbook_data.append(play_data)
        playbook_data = recursive_str_to_ruamel_quotated_str(playbook_data)

        # to pass ansible-lint indentation rule, we need offset config
        ariyaml.indent(sequence=4, offset=2)

        yaml_str = ariyaml.dump(playbook_data)
        # but the first play block should not have any offsets for ansible-lint, so we remove here
        yaml_str = _remove_top_level_offset(yaml_str)
        self._yaml = yaml_str
        return self._yaml