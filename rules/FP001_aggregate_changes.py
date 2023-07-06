import re
from dataclasses import dataclass

from ansible_risk_insight.models import (
    AnsibleRunContext,
    RunTargetType,
    Rule,
    RuleResult,
    Severity,
    Annotation,
)



@dataclass
class FTDataPipelineRule(Rule):
    rule_id: str = "FP001"
    description: str = "aggregate changes by other rules"
    enabled: bool = True
    name: str = "AggregateChanges"
    version: str = "v0.0.1"
    severity: Severity = Severity.NONE
    tags: tuple = "wisdom"
    precedence: int = 20

    def match(self, ctx: AnsibleRunContext) -> bool:
        return ctx.current.type == RunTargetType.Task

    def process(self, ctx: AnsibleRunContext):
        task = ctx.current

        verdict = True

        # detail
        detail = {}

        changes = {}
        change_annotation_pattern = "[a-zA-Z0-9]+\.applied_changes"
        for annotation in task.annotations:
            if not isinstance(annotation, Annotation):
                continue
            anno_key = annotation.key
            if not re.match(change_annotation_pattern, anno_key):
                continue
            if not isinstance(annotation.value, dict):
                continue
            
            changes.update(annotation.value)

        detail["changes"] = changes
        return RuleResult(
            verdict=verdict,
            detail=detail,
            file=task.file_info(),
            rule=self.get_metadata(),
        )
