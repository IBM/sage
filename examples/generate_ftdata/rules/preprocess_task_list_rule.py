from dataclasses import dataclass

from ansible_risk_insight.models import (
    AnsibleRunContext,
    RunTargetType,
    Rule,
    RuleResult,
    Severity,
)


@dataclass
class GetTaskListRule(Rule):
    rule_id: str = "PP002"
    description: str = "This is sample rule to get tasks in a project/role/playbook."
    enabled: bool = True
    name: str = "TaskList"
    version: str = "v0.0.1"
    severity: Severity = Severity.NONE
    tags: tuple = ("wisdom")

    def match(self, ctx: AnsibleRunContext) -> bool:
        return ctx.current.type == RunTargetType.Task

    def process(self, ctx: AnsibleRunContext):
        task = ctx.current

        verdict = True
        detail = {}
        detail = task.spec

        return RuleResult(verdict=verdict, detail=detail, file=task.file_info(), rule=self.get_metadata())
