from dataclasses import dataclass, field
from sage.models import Playbook, Play, TaskFile, Role, Task
from ansible_risk_insight.models import VariableType


@dataclass
class VariableResolver(object):
    call_seq: list = field(default_factory=list)

    def set_defined_vars(self):
        def _update(defined_dict, variables, precedence):
            if not variables:
                return
            if not isinstance(variables, dict):
                return
            for key, value in variables.items():
                if key in defined_dict:
                    current_precedence = defined_dict[key][1]
                    if precedence >= current_precedence:
                        defined_dict[key] = (value, precedence)
                else:
                    defined_dict[key] = (value, precedence)
            return
        
        defined_vars = {}
        for obj in self.call_seq:
            if isinstance(obj, Playbook):
                _update(defined_vars, obj.variables, VariableType.PlaybookGroupVarsAll)
            elif isinstance(obj, Play):
                _update(defined_vars, obj.variables, VariableType.PlayVars)
            elif isinstance(obj, Role):
                _update(defined_vars, obj.default_variables, VariableType.RoleDefaults)
                _update(defined_vars, obj.variables, VariableType.RoleVars)
            elif isinstance(obj, TaskFile):
                pass
                # _update(defined_vars, obj.variables, VariableType.TaskVars)
            elif isinstance(obj, Task):
                _update(defined_vars, obj.variables, VariableType.TaskVars)
                _update(defined_vars, obj.set_facts, VariableType.SetFacts)

            # save a copy of defined_vars because it is updated by the next object in the sequence
            # and we remove precedence info here
            obj.annotations["defined_vars"] = {k: v[0] for k, v in defined_vars.items()}
        return

    def resolve(self):
        pass
