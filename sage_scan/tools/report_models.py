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

import json
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from typing import List


def dict_join(dict1, dict2):
    dic = dict1.copy()
    for k in dict2:
        if k in dic:
            dic[k] = dic[k] + dict2[k]
        else:
            dic[k] = dict2[k]
    return dic

@dataclass_json
@dataclass
class FileResult(object):
    filepath: str = ""
    path_in_project: str = ""
    type: str = ""
    role: str = ""
    role_path: str = ""
    error: str = ""
    skip_reason: str = ""
    in_scope: bool = False
    scanned: bool = False
    warning: str = ""
    name_count: int = 0
    scanned_task_count : int = 0
  

@dataclass_json
@dataclass
class ScanCount(object):
    total: int = 0
    scanned: int = 0
    skipped: int = 0
    skip_reasons: dict = field(default_factory=dict)
    scan_error: int = 0
    scan_err_msgs: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, obj):
        c = cls()
        c.total = obj.get("total", 0)
        c.scanned = obj.get("scanned", 0)
        c.skipped = obj.get("skipped", 0)
        c.skip_reasons = obj.get("skip_reasons", {})
        c.scan_error = obj.get("scan_error", 0)
        c.scan_err_msgs = obj.get("scan_err_msgs", {})
        return c

    def merge(self, obj):
        if not isinstance(obj, ScanCount):
            raise Exception(f"incompatible type: {type(obj)}")
        obj2 = ScanCount()
        obj2.total = self.total + obj.total
        obj2.scanned = self.scanned + obj.scanned
        obj2.skipped = self.skipped + obj.skipped
        obj2.skip_reasons = dict_join(self.skip_reasons, obj.skip_reasons)
        obj2.scan_error = self.scan_error + obj.scan_error
        obj2.scan_err_msgs = dict_join(self.scan_err_msgs, obj.scan_err_msgs)
        return obj2


@dataclass_json
@dataclass
class OtherCount(object):
    total: int = 0
    reason: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, obj):
        c = cls()
        c.total = obj.get("total", 0)
        c.reason = obj.get("reason", {})
        return c

    def merge(self, obj):
        if not isinstance(obj, OtherCount):
            raise Exception(f"incompatible type: {type(obj)}")
        obj2 = OtherCount()
        obj2.total = self.total + obj.total
        obj2.reason = dict_join(self.reason, obj.reason)
        return obj2


@dataclass_json
@dataclass
class ErrorCount(object):
    total: int = 0
    err_msgs: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, obj):
        c = cls()
        c.total = obj.get("total", 0)
        c.err_msgs = obj.get("err_msgs", {})
        return c

    def merge(self, obj):
        if not isinstance(obj, ErrorCount):
            raise Exception(f"incompatible type: {type(obj)}")
        obj2 = ErrorCount()
        obj2.total = self.total + obj.total
        obj2.err_msgs = dict_join(self.err_msgs, obj.err_msgs)
        return obj2


@dataclass_json
@dataclass
class FileCount(object):
    total: int = 0
    scan_failures: int = 0
    playbooks: ScanCount = field(default_factory=ScanCount)
    taskfiles: ScanCount = field(default_factory=ScanCount)
    others: OtherCount = field(default_factory=OtherCount)
    errors: ErrorCount = field(default_factory=ErrorCount)

    @classmethod
    def from_dict(cls, obj):
        c = cls()
        c.total = obj.get("total", 0)
        c.scan_failures = obj.get("scan_failures", 0)
        c.playbooks = ScanCount.from_dict(obj.get("playbooks", {}))
        c.taskfiles = ScanCount.from_dict(obj.get("taskfiles", {}))
        c.others = OtherCount.from_dict(obj.get("others", {}))
        c.errors = ErrorCount.from_dict(obj.get("errors", {}))
        return c

    def merge(self, obj):
        if not isinstance(obj, FileCount):
            raise Exception(f"incompatible type: {type(obj)}")
        obj2 = FileCount()
        obj2.total = self.total + obj.total
        obj2.scan_failures = self.scan_failures + obj.scan_failures
        obj2.playbooks = self.playbooks.merge(obj.playbooks)
        obj2.taskfiles = self.taskfiles.merge(obj.taskfiles)
        obj2.others = self.others.merge(obj.others)
        obj2.errors = self.errors.merge(obj.errors)
        return obj2


@dataclass_json
@dataclass
class RoleCount(object):
    total: int = 0

    @classmethod
    def from_dict(cls, obj):
        c = cls()
        c.total = obj.get("total", 0)
        return c

    def merge(self, obj):
        if not isinstance(obj, RoleCount):
            raise Exception(f"incompatible type: {type(obj)}")
        obj2 = RoleCount()
        obj2.total = self.total + obj.total
        return obj2


@dataclass_json
@dataclass
class TaskCount(object):
    total: int = 0
    names: int = 0

    @classmethod
    def from_dict(cls, obj):
        c = cls()
        c.total = obj.get("total", 0)
        c.names = obj.get("names", 0)
        return c

    def merge(self, obj):
        if not isinstance(obj, TaskCount):
            raise Exception(f"incompatible type: {type(obj)}")
        obj2 = TaskCount()
        obj2.total = self.total + obj.total
        obj2.names = self.names + obj.names
        return obj2

@dataclass_json
@dataclass
class StateCount(object):
    success: int = 0
    fail: int = 0
    unknown: int = 0

    @classmethod
    def from_dict(cls, obj):
        c = cls()
        c.success = obj.get("success", 0)
        c.fail = obj.get("fail", 0)
        c.unknown = obj.get("unknown", 0)
        return c

    def merge(self, obj):
        if not isinstance(obj, StateCount):
            raise Exception(f"incompatible type: {type(obj)}")
        obj2 = StateCount()
        obj2.success = self.success + obj.success
        obj2.fail = self.fail + obj.fail
        obj2.unknown = self.unknown + obj.unknown
        return obj2

@dataclass_json
@dataclass
class ProjectSource(object):
    source: str = ""
    repo_name: str = ""
    object_file: str = ""
    metadata_file: str = ""

    @classmethod
    def from_dict(cls, obj):
        c = cls()
        c.metadata_file = obj.get("metadata_file", "")
        c.object_file = obj.get("object_file", "")
        c.repo_name = obj.get("repo_name", "")
        c.source = obj.get("source", "")
        return c

    @classmethod
    def from_list(cls, obj):
        ps_list = []
        if isinstance(obj, list):
            for v in obj:
                ps = cls.from_dict(v)
                ps_list.append(ps)
        return ps_list


@dataclass_json
@dataclass
class ScanReport(object):
    project_count: int = 0
    projects: List[ProjectSource] = field(default_factory=list)
    file_count: FileCount = field(default_factory=FileCount)
    role_count: RoleCount = field(default_factory=RoleCount)
    task_count: TaskCount = field(default_factory=TaskCount)
    warning: dict = field(default_factory=dict)
    error: dict = field(default_factory=dict)
    state_count: StateCount = field(default_factory=StateCount)
    file_results: List[FileResult] = field(default_factory=list)

    @classmethod
    def from_dict(cls, obj):
        c = cls()
        c.total = obj.get("project_count", 0)
        c.projects = ProjectSource.from_list(obj.get("projects", []))
        c.file_count = FileCount.from_dict(obj.get("file_count", {}))
        c.role_count = RoleCount.from_dict(obj.get("role_count", {}))
        c.task_count = TaskCount.from_dict(obj.get("task_count", {}))
        c.warning = obj.get("warning", {})
        c.error = obj.get("error", {})
        c.state_count = StateCount.from_dict(obj.get("state_count", {}))
        c.file_results = FileResult.from_dict(obj.get("file_results", []))
        return c

    def merge(self, obj):
        if not isinstance(obj, ScanReport):
            raise Exception(f"incompatible type: {type(obj)}")
        obj2 = ScanReport()
        obj2.project_count = self.project_count + obj.project_count
        obj2.projects = self.projects + obj.projects
        obj2.file_count = self.file_count.merge(obj.file_count)
        obj2.role_count = self.role_count.merge(obj.role_count)
        obj2.task_count = self.task_count.merge(obj.task_count)
        obj2.warning = dict_join(self.warning, obj.warning)
        obj2.error = dict_join(self.error, obj.error)
        obj2.state_count = self.state_count.merge(obj.state_count)
        return obj2


if __name__ == "__main__":
    file1 = "sage_scan/tools/summary-sample.json"
    file2 = "sage_scan/tools/summary-sample.json"

    d1 = {}
    d2 = {}

    with open(file1, "r") as f1:
        d1 = json.load(f1)

    with open(file1, "r") as f2:
        d2 = json.load(f2)

    sr1 = ScanReport.from_dict(d1)
    sr2 = ScanReport.from_dict(d2)

    sr_merged = sr1.merge(sr2)
    print(sr_merged.to_json(ensure_ascii=False))
