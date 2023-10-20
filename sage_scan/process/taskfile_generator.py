from dataclasses import dataclass, field
from sage_scan.models import Playbook, Task
import ansible_risk_insight.yaml as ariyaml


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
class TaskfileGenerator(object):
    tasks: list = field(default_factory=list)
    
    _yaml: str = ""

    def yaml(self):
        tasks = [task_obj_to_data(t) for t in self.tasks]
        taskfile_data = [tasks]

        # to pass ansible-lint indentation rule, we need offset config
        ariyaml.indent(sequence=4, offset=2)

        yaml_str = ariyaml.dump(taskfile_data)
        # but the first play block should not have any offsets for ansible-lint, so we remove here
        yaml_str = _remove_top_level_offset(yaml_str)
        self._yaml = yaml_str
        return self._yaml