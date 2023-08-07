from dataclasses import dataclass, field
from sage.models import Playbook, Task
import ansible_risk_insight.yaml as ariyaml


def task_obj_to_data(task: Task):
    data = {}
    if task.name:
        data["name"] = task.name
    
    module_name = task.module
    if task.annotations and isinstance(task.annotations, dict):
        module_name = task.annotations.get("correct_fqcn", module_name)

    data[module_name] = task.module_options    

    if task.options and isinstance(task.options, dict):
        for k, v in task.options.items():
            if k == "name":
                continue
            data[k] = v
    return data


@dataclass
class PlaybookGenerator(object):
    
    name: str = ""
    options: dict = field(default_factory=dict)
    vars: list = field(default_factory=list)
    tasks: list = field(default_factory=list)
    
    _yaml: str = ""

    def yaml(self):
        play_data = {
            "name": self.name
        }
        play_data.update(self.options)
        vars = {}
        for v in self.vars:
            v_name = v
            v_value = "{{ " + v_name + " }}"
            vars[v_name] = v_value
        play_data["vars"] = vars
        play_data["tasks"] = [task_obj_to_data(t) for t in self.tasks]

        playbook_data = [play_data]

        self._yaml = ariyaml.dump(playbook_data)
        return self._yaml