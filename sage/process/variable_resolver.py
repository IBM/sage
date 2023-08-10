from dataclasses import dataclass, field
from sage.models import Playbook, Play, TaskFile, Role, Task, SageObject
from ansible_risk_insight.models import VariableType


@dataclass
class VariableResolver(object):
    call_seq: list = field(default_factory=list)

    def get_defined_vars(self, object: SageObject):
        obj_and_vars_list = self.set_defined_vars()
        for obj, defnied_vars in obj_and_vars_list:
            if obj.key == object.key:
                return defnied_vars
        return None

    def set_defined_vars(self, set_annotation=False):
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
        obj_and_vars_list = []
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

            # make a copy of defined_vars because it is updated by the next object in the sequence
            # and we remove precedence info here
            defined_vars_key_value = {k: v[0] for k, v in defined_vars.items()}
            obj_and_vars_list.append((obj, defined_vars_key_value))

            if set_annotation:
                obj.annotations["defined_vars"] = defined_vars_key_value
        return obj_and_vars_list

    def resolve(self):
        pass
