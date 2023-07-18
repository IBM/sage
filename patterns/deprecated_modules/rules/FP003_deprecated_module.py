import sys
import yaml
from dataclasses import dataclass

from ansible_risk_insight.models import (
    AnsibleRunContext,
    RunTargetType,
    Rule,
    RuleResult,
    Severity,
    TaskCall,
)


@dataclass
class FTSagePipelineRule(Rule):
    rule_id: str = "FP003"
    description: str = "add module info about deprecation"
    enabled: bool = True
    name: str = "AddModuleDeprecationInfo"
    version: str = "v0.0.1"
    severity: Severity = Severity.NONE
    tags: tuple = "wisdom"

    def match(self, ctx: AnsibleRunContext) -> bool:
        return ctx.current.type == RunTargetType.Task

    def process(self, ctx: AnsibleRunContext):
        task = ctx.current

        detail = {}
        verdict = True

        changes = {}

        # add changes here

        deprecated = {}
        if isinstance(task, TaskCall):
            m = task.module
            if m and m.documentation:
                try:
                    module_doc_data = yaml.safe_load(m.documentation)
                    if isinstance(module_doc_data, dict):
                        deprecated = module_doc_data.get("deprecated", {})
                except Exception:
                    pass

        changes["is_deprecated"] = False
        changes["alternative_for_deprecated"] = ""
        if deprecated:
            changes["is_deprecated"] = True
            changes["alternative_for_deprecated"] = deprecated.get("alternative", "")

        detail["changes"] = changes
        task.set_annotation("fp003.applied_changes", changes, rule_id=self.rule_id)

        return RuleResult(
            verdict=verdict,
            detail=detail,
            file=task.file_info(),
            rule=self.get_metadata(),
        )


# TODO: implement test
if "pytest" in sys.modules:
    import os
    from ansible_risk_insight.scanner import ARIScanner, Config

    _rule_id = "FP003"
    _scanner = ARIScanner(
        config=Config(
            data_dir=os.path.normpath(os.path.join(os.path.dirname(__file__), "../test-kb")),
            rules_dir=os.path.dirname(__file__),
            rules=["P001", "P002", "P003", "P004", _rule_id],
        ),
        silent=True,
    )
    _update_result_data = False

    def test_fqcn_mutation():
        playbook_path = "examples/replace_short_name_with_fqcn.yml"
        result_path = "results/replace_short_name_with_fqcn_W001.yml"
        result = _scanner.evaluate(
            type="playbook",
            path=playbook_path,
            playbook_only=True,
        )
        playbook = result.playbook(path=playbook_path)
        task = playbook.tasks().nodes[-1]
        rule_result = task.find_result(rule_id=_rule_id)
        detail = rule_result.get_detail()
        changes = detail.get("applied_changes", None)
        assert changes["after"] == "amazon.aws.ec2_instance"

        mutated_yaml = detail.get("mutated_yaml", None)
        if _update_result_data:
            if mutated_yaml:
                with open(result_path, "w") as file:
                    file.write(mutated_yaml)
        else:
            with open(result_path, "r") as file:
                result_yaml = file.read()
                assert mutated_yaml == result_yaml
