from dataclasses import dataclass

from ansible_risk_insight.models import (
    AnsibleRunContext,
    RunTargetType,
    Rule,
    RuleResult,
    Severity,
)

import re


def find_repo_info(ctx: AnsibleRunContext, role):
    repo_name = ""
    license = ""
    source = "Galaxy"
    for node in ctx:
        if node.type == RunTargetType.Role:
            rolecall = node
            if role != rolecall.spec.name:
                continue
            license = rolecall.spec.metadata.get("galaxy_info", {}).get("license", "")
            repo_name = rolecall.spec.fqcn
    return repo_name, license, source  


def make_sequence(ctx: AnsibleRunContext, current_depth, current_id) -> list:
    wisdom_sequence = []
    for node in ctx:
        skip = True
        if node.depth < current_depth:
            if current_id.startswith(node.node_id):  # 0.1
                skip = False
        elif node.depth == current_depth:
            sid = str(node.node_id)
            scid = str(current_id)
            if sid[:-1] == scid[:-1] and int(sid[-1]) < int(scid[-1]):
                skip = False

        if skip:
            continue

        node_data = {}
        node_data["type"] = getattr(node.spec, "type", "")
        node_data["name"] = getattr(node.spec, "name", "")
        node_data["node_id"] = getattr(node, "node_id", "")

        if node.type == RunTargetType.Role:
            rolecall = node
            node_data["name"] = rolecall.spec.name
            node_data["spec"] = rolecall.spec
        elif node.type == RunTargetType.TaskFile:
            pass
        elif node.type == RunTargetType.Task:
            taskcall = node
            node_data["spec"] = taskcall.spec
        wisdom_sequence.append(node_data)
    return wisdom_sequence


@dataclass
class PreProcessingRule(Rule):
    rule_id: str = "PP003"
    description: str = "get a task list including all context information"
    enabled: bool = True
    name: str = "GetFullContext"
    version: str = "v0.0.1"
    severity: Severity = Severity.NONE
    tags: tuple = ("wisdom")
    precedence: int = 1

    def match(self, ctx: AnsibleRunContext) -> bool:
        return ctx.current.type == RunTargetType.Task

    def process(self, ctx: AnsibleRunContext):
        task = ctx.current

        verdict = True
        detail = {}

        wisdom_sequence = []

        current_id = task.node_id  # e.g) 0.1.2
        current_depth = task.depth  # e.g) 3

        ctx_1 = ctx.copy()  # --> reset current
        wisdom_sequence = make_sequence(ctx_1, current_depth, current_id)

        all_vars = {}
        for var_name in task.variable_set:
            var_object = task.variable_set[var_name][-1]
            var_name == var_object.name
            var_value = var_object.value
            all_vars[var_name] = var_value

        wisdom_context = {}
        wisdom_context["sequence"] = wisdom_sequence 
        wisdom_context["variables"] = all_vars

        train = {
            "license": "",
            "source": "",
            "path": "",
            "repo_name": "",
            "type": "",
            "prompt": "",
            "input_script": "",
            "output_script": "",
            "token_count": 0,
            "op_token_count": 0,
            "sample_type": 0,
            "context_len": 0,
            "module_name": "",
            "id": 0,
            "prompt_key": ""
        }

        module = task.get_annotation("module.correct_fqcn", "")
        role = getattr(task.spec, "role")
        repo_name, license, source = find_repo_info(ctx_1, role)
        train["input_script"] = wisdom_context
        train["license"] = license
        train["source"] = source
        train["path"] = getattr(task.spec, "defined_in", "")
        train["repo_name"] = repo_name
        train["type"] = getattr(task.spec, "type", "")
        train["output_script"] = getattr(task.spec, "yaml_lines", "")
        train["module_name"] = module
        train["id"] = f"{current_id}-{current_depth}"  # <ari_node_id> - <ari_node_depth>
        
        prompt = ""
        yamllines = getattr(task.spec, "yaml_lines", "").split("\n")
        for yl in yamllines:
            if yl.startswith("- name:"):
                prompt = yl
                break
        train["prompt"] = prompt
        lp = prompt.replace("- name:", "").lower()
        train["prompt_key"] = re.sub(r"[^a-zA-Z]", "", lp)

        detail = train

        return RuleResult(verdict=verdict, detail=detail, file=task.file_info(), rule=self.get_metadata())
