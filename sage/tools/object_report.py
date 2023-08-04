from mdutils.mdutils import MdUtils
from pathlib import Path
import os
import json
import argparse
from dataclasses import dataclass, field
import glob
import tempfile
import os
import collections
import jsonpickle
from report_models import ScanReport, ProjectSource, TaskCount, FileCount, \
    OtherCount, ScanCount, ErrorCount, RoleCount, FileResult, StateCount

OBJ_FILE="sage-objects.json"
META_FILE="sage-metadata.json"

class Data_Splitter:
    def __init__(self, out_dir, filename) -> None:
        self.out_dir = out_dir
        self._buffer = {}
        self.max_buffer = 100
        self.filename = filename

    def _get_lines(self, src_type, repo_name, init=False):
        if src_type is None or repo_name is None:
            return None

        v1 = None
        if src_type not in self._buffer:
            if init:
                v1 = {}
                self._buffer[src_type] = v1
            else:
                return None
        else:
            v1 = self._buffer[src_type]

        v2 = None
        if repo_name not in v1:
            if init:
                v2 = []
                v1[repo_name] = v2
            else:
                return None
        else:
            v2 = v1[repo_name]

        return v2

    def save_to_buffer(self, src_type=None, repo_name=None, str=None):
        if src_type is None or repo_name is None or str is None:
            return

        lines = self._get_lines(src_type, repo_name, init=True)
        lines.append(str)

        if len(lines) > self.max_buffer:
            self._dump_buffer(src_type, repo_name)

    def _dump_buffer(self, src_type, repo_name):
        os.makedirs(os.path.join(self.out_dir, src_type, repo_name), exist_ok=True)
        file = os.path.join(self.out_dir, src_type, repo_name, self.filename)
        lines = self._get_lines(src_type, repo_name)
        with open(file, mode="a") as f:
            for line in lines:
                f.write(f"{line.rstrip()}\n")
        self._buffer[src_type][repo_name] = []

    def save_all(self):
        for src_type in self._buffer:
            for repo_name in self._buffer[src_type]:
                self._dump_buffer(src_type, repo_name)

    def get_repo_names(self, src_type):
        return self._buffer[src_type].keys()


class ScanResultSummarizer:
    def __init__(self, outdir, json_dir, detail_repo_dir, input_dir) -> None:
        self.outdir = outdir
        self.json_outdir = json_dir
        self.md_outdir = detail_repo_dir
        self.objects_root_dir = input_dir

    def generate_repo_summary(self, obj_file):
        meta_file = obj_file.replace(OBJ_FILE, META_FILE)
        summary, file_results = self.compute_scan_report(obj_file, meta_file)
        _src_type = summary.projects[0].source
        _repo_name = summary.projects[0].repo_name
        result_json_dir = os.path.join(self.json_outdir, _src_type, _repo_name)
        os.makedirs(result_json_dir, exist_ok=True)
        json_path = os.path.join(result_json_dir, "summary.json")
        with open(json_path, "w") as file:
            file.write(summary.to_json(ensure_ascii=False))
        return json_path, file_results

    def compute_scan_report(self, object_json, meta_json):
        metadata = load_json_data(meta_json)
        objects =load_json_data(object_json)
        if len(objects) == 0:
            print(f"{object_json} is empty")
            ps = ProjectSource(metadata[0]["source"]["type"], metadata[0]["source"]["repo_name"], object_json, meta_json)
            error = {"EmptyObjectsJsonError": 1}
            state = StateCount()
            state.unknown = 1
            return ScanReport(project_count=1, projects=[ps], error=error, state_count=state), []
        # summarize yml inventory
        target_files = []
        out_scopes = []
        roles = []
        yml_files = metadata[0].get("yml_files", [])
        for yf in yml_files:
            path_from_root = yf.get("path_from_root", "")
            filepath = yf.get("filepath", "")
            _type = yf.get("label", "")
            role_info = yf.get("role_info", {})
            fr = FileResult(filepath=filepath, path_in_project=path_from_root, type=_type)
            fr.name_count = yf.get("name_count", 0)
            is_external_dependency = False
            if role_info:
                role_name = role_info["name"]
                role_path = role_info["path"]
                fr.role = role_name
                fr.role_path = role_path
                if role_info not in roles:
                    roles.append(role_info)
                is_external_dependency = role_info["is_external_dependency"]

            if _type == "error":
                error_info = yf.get("error", {})
                error_type = error_info.get("type", "")
                if error_type == "TooManyTasksError":
                    fr.skip_reason = "too many tasks"
                    fr.type = "others"
                elif error_type == "YAMLParseError":
                    fr.skip_reason = "invalid yml"
                    fr.type = "others"
                else:
                    fr.error = error_type 
                out_scopes.append(fr)
            elif _type == "others":
                fr.skip_reason = "other file"
                out_scopes.append(fr)
            elif is_external_dependency:
                fr.skip_reason = "external dependency"
                out_scopes.append(fr)
            else:
                target_files.append(fr)

        # summarize loaded objects
        obj_types = {}
        for obj in objects:
            filepath = obj.get("filepath", "")
            _type = obj.get("type", "")
            name = obj.get("name", "")
            type_sum = obj_types.get(_type, [])
            type_sum.append({"filepath": filepath, "name": name})
            obj_types[_type] = type_sum

        obj_res = {}
        for t, objs in obj_types.items():
            obj_res[t] = {
                "count": len(objs),
                "objects": objs
            }

        file_results = []
        for result in target_files:
            tt = result.type
            fp = result.path_in_project
            result.in_scope = True            
            # file
            t_objs = obj_res[tt]["objects"]
            is_scanned = False
            for to in t_objs:
                if to["filepath"] == fp:
                    is_scanned = True
            result.scanned = is_scanned
            if is_scanned:
                # task count
                if "task" in obj_res:
                    for tasks in obj_res["task"]["objects"]:
                        if fp == tasks["filepath"]:
                            result.scanned_task_count = result.scanned_task_count + 1
                if result.scanned_task_count == 0 and result.name_count != 0:
                    result.warning = "no task found in this file"
            else:
                skip = False
                if result.scanned_task_count == 0 and result.name_count == 0:
                    result.in_scope = False
                    result.skip_reason = "no task included"
                    skip = True
                # todo: invalid taskfile/playbook
                elif result.scanned_task_count == 0 and result.role:
                    path_from_role = result.filepath.replace(result.role_path, "").lstrip("/")
                    if not path_from_role.startswith("tasks") and not path_from_role.startswith("handlers") \
                        and not path_from_role.startswith("tests"): 
                            result.in_scope = False
                            result.skip_reason = f"invalid {result.type}"
                            skip = True
                if not skip:
                    result.error = "unknown"

            file_results.append(result)
        
        for result in out_scopes:
            result.in_scope = False
            result.scanned = False
            result.scanned_task_count = 0
            file_results.append(result)
        
        file_results = sorted(file_results, key=lambda x: x.path_in_project)

        # fail reason
        error_msgs = [res.error for res in file_results if res.error and not res.in_scope]
        p_error_msgs = [res.error for res in file_results if res.error and res.type == "playbook"]
        tf_error_msgs = [res.error for res in file_results if res.error and res.type == "taskfile"]
        error_msgs_count = dict(collections.Counter(error_msgs))
        p_error_msgs_count = dict(collections.Counter(p_error_msgs))
        tf_error_msgs_count = dict(collections.Counter(tf_error_msgs))
        p_skip_msgs = [res.skip_reason for res in file_results if res.skip_reason and res.type == "playbook"]
        tf_skip_msgs = [res.skip_reason for res in file_results if  res.skip_reason and res.type == "taskfile"]
        o_skip_msgs = [res.skip_reason for res in file_results if  res.skip_reason and res.type == "others"]
        p_skip_msgs_count = dict(collections.Counter(p_skip_msgs))
        tf_skip_msgs_count = dict(collections.Counter(tf_skip_msgs))
        o_skip_msgs_count = dict(collections.Counter(o_skip_msgs))
        warning_msgs = [res.warning for res in file_results]
        warning_msgs_count = dict(collections.Counter(warning_msgs))
        
        # playbook
        p_total = sum(1 for res in file_results if res.type == "playbook")
        p_scanned = sum(1 for res in file_results if res.type == "playbook" and res.scanned)
        p_skipped = sum(1 for res in file_results if res.type == "playbook" and not res.in_scope)
        p_scan_error = sum(1 for res in file_results if res.type == "playbook" and res.in_scope and not res.scanned)
        p_skip_reasons = p_skip_msgs_count
        p_scan_error_msgs = p_error_msgs_count
        playbooks = ScanCount(p_total, p_scanned, p_skipped, p_skip_reasons, p_scan_error, p_scan_error_msgs)

        # taskfile
        t_total = sum(1 for res in file_results if res.type == "taskfile")
        t_scanned = sum(1 for res in file_results if res.type == "taskfile" and res.scanned)
        t_skipped = sum(1 for res in file_results if res.type == "taskfile" and not res.in_scope)
        t_scan_error = sum(1 for res in file_results if res.type == "taskfile" and res.in_scope and not res.scanned)
        t_skip_reasons = tf_skip_msgs_count
        t_scan_error_msgs = tf_error_msgs_count
        taskfiles = ScanCount(t_total, t_scanned, t_skipped, t_skip_reasons, t_scan_error, t_scan_error_msgs)

        # others
        o_total = sum(1 for res in file_results if res.type == "others")
        others = OtherCount(total=o_total, reason=o_skip_msgs_count)
    
        # errors
        errors = {}
        e_total = sum(1 for res in file_results if res.type == "error")
        error_reasons = error_msgs_count
        errors = ErrorCount(e_total, error_reasons)

        # total
        fc_total = len(file_results)
        scan_failures = t_scan_error + p_scan_error
        fc = FileCount(fc_total, scan_failures, playbooks, taskfiles, others, errors)

        # task count
        nc = sum(v.name_count for v in file_results)
        tt = sum(v.scanned_task_count for v in file_results)
        tc = TaskCount(total=tt, names=nc)

        # warnings
        warnings = warning_msgs_count

        # role
        rc = RoleCount(len(roles))

        # project src
        _source = objects[0].get("source", {}).get("type", "")
        _repo_name = objects[0].get("source", {}).get("repo_name", "")
        ps = ProjectSource(_source, _repo_name, object_json, meta_json)

        state = StateCount()
        if fc.playbooks.scan_error == 0 and fc.taskfiles.scan_error == 0 and fc.errors.total == 0:
            state.success = 1
        else:
            state.fail = 1

        # compute scan result
        scan_result = ScanReport(
            project_count=1,
            projects=[ps],
            file_count=fc,
            role_count=rc,
            task_count=tc,
            warning=warnings,
            state_count=state
        )
        return scan_result, file_results
    
    def merge_repo_summary(self, target_dir):
        json_files = glob.glob(os.path.join(target_dir, "**", "summary.json"), recursive=True)
        merge_sr = ScanReport()
        for jf in json_files:
            if jf == os.path.join(target_dir, "summary.json"):
                continue
            jd = load_json_data(jf)
            sr = ScanReport.from_dict(jd[0])
            merge_sr = merge_sr.merge(sr)
        return merge_sr

    def merge_src_summary(self, target_dir):
        json_files = glob.glob(os.path.join(target_dir, "**", "summary.json"))
        merge_sr = ScanReport()
        for jf in json_files:
            if jf == os.path.join(target_dir, "summary.json"):
                continue
            jd = load_json_data(jf)
            sr = ScanReport.from_dict(jd[0])
            merge_sr = merge_sr.merge(sr)
        return merge_sr

    def merge_dicts(self, dict1, dict2):
        result_dict = {}
        for key in set(dict1.keys()).union(dict2.keys()):
            if key == "file_results":
                continue
            if isinstance(dict1.get(key), dict) and isinstance(dict2.get(key), dict):
                result_dict[key] = self.merge_dicts(dict1[key], dict2[key])
            else:
                # if type(dict1[key]) == int:
                value1 = dict1.get(key, 0)
                value2 = dict2.get(key, 0)
                # elif type(dict1[key]) == list:
                #     value1 = dict1.get(key, [])
                #     value2 = dict2.get(key, [])
                result_dict[key] = value1 + value2
        return result_dict
    
    def _gen_inventory_table(self, sr: ScanReport):
        # header = ["playbooks (scanned/total)", "taskfiles (scanned/total)", "others",  "ext. dependency", "parse error", "too many tasks", "total_num"]
        header = ["", "files", "scanned", "skipped", "error", "state", "skip_reasons", "error_reason"]
        c_num = len(header)
        r_num = 6
        cells = header
        # playbook
        state = ""
        if sr.file_count.playbooks.scan_error == 0:
            state = "✔"
        skip_reason = ""
        if sr.file_count.playbooks.skip_reasons:
            _r = []
            for key, count in sr.file_count.playbooks.skip_reasons.items():
                _r.append(f"{key} ({count})")
            skip_reason = ','.join(_r)
        err_reason = ""
        if sr.file_count.playbooks.scan_err_msgs:
            _r = []
            for key, count in sr.file_count.playbooks.scan_err_msgs.items():
                _r.append(f"{key} ({count})")
            err_reason = ','.join(_r)

        cells.append("playbook")
        cells.append(sr.file_count.playbooks.total)
        cells.append(sr.file_count.playbooks.scanned)
        cells.append(sr.file_count.playbooks.skipped)
        cells.append(sr.file_count.playbooks.scan_error)
        cells.append(state)
        cells.append(skip_reason)
        cells.append(err_reason)

        # taskfile
        state = ""
        if sr.file_count.taskfiles.scan_error == 0:
            state = "✔"
        skip_reason = ""
        if sr.file_count.taskfiles.skip_reasons:
            _r = []
            for key, count in sr.file_count.taskfiles.skip_reasons.items():
                _r.append(f"{key} ({count})")
            skip_reason = ','.join(_r)
        err_reason = ""
        if sr.file_count.taskfiles.scan_err_msgs:
            _r = []
            for key, count in sr.file_count.taskfiles.scan_err_msgs.items():
                _r.append(f"{key} ({count})")
            err_reason = ','.join(_r)

        cells.append("taskfile")
        cells.append(sr.file_count.taskfiles.total)
        cells.append(sr.file_count.taskfiles.scanned)
        cells.append(sr.file_count.taskfiles.skipped)
        cells.append(sr.file_count.taskfiles.scan_error)
        cells.append(state)
        cells.append(skip_reason)
        cells.append(err_reason)
        # others
        other_reason = ""
        if sr.file_count.others.reason:
            _r = []
            for key, count in sr.file_count.others.reason.items():
                _r.append(f"{key} ({count})")
            other_reason = ','.join(_r)
        cells.append("others")
        cells.append(sr.file_count.others.total)
        cells.append(0)
        cells.append(sr.file_count.others.total)
        cells.append(0)
        cells.append("✔")
        cells.append(other_reason)
        cells.append("")
        # errors
        err_reason = ""
        if sr.file_count.errors.err_msgs:
            _r = []
            for key, count in sr.file_count.errors.err_msgs.items():
                _r.append(f"{key} ({count})")
            err_reason = ','.join(_r)

        cells.append("errors")
        cells.append(sr.file_count.errors.total)
        cells.append(0)
        cells.append(0)
        cells.append(sr.file_count.errors.total)
        if sr.file_count.errors.total == 0:
            cells.append("✔")
        else:
            cells.append("")
        cells.append("")
        cells.append(err_reason)
        # total
        cells.append("Total")
        # files
        cells.append(sr.file_count.playbooks.total+sr.file_count.taskfiles.total+sr.file_count.others.total+sr.file_count.errors.total)
        # scanned
        cells.append(sr.file_count.playbooks.scanned+sr.file_count.taskfiles.scanned)
        # skipped
        cells.append(sr.file_count.playbooks.skipped+sr.file_count.taskfiles.skipped+sr.file_count.others.total)
        # error
        cells.append(sr.file_count.playbooks.scan_error+sr.file_count.taskfiles.scan_error+sr.file_count.errors.total)
        if sr.file_count.playbooks.scan_error+sr.file_count.taskfiles.scan_error+sr.file_count.errors.total == 0:
            cells.append("✔")
        else:
            cells.append("")
        cells.append("")
        cells.append("")
        return cells, c_num, r_num

    def _gen_project_result_table(self,  sr: ScanReport):
        header = ["passed", "error", "no result", "total"]
        c_num = len(header)
        r_num = 2
        cells = header
        cells.append(sr.state_count.success)
        cells.append(sr.state_count.fail)
        cells.append(sr.state_count.unknown)
        cells.append(sr.project_count)
        return cells, c_num, r_num

    def _gen_role_task_table(self, sr: ScanReport):
        header = ["roles", "tasks"]
        c_num = len(header)
        r_num = 2
        cells = header
        cells.append(sr.role_count.total)
        cells.append(sr.task_count.total)
        return cells, c_num, r_num

    def generate_repo_report(self, json_path, file_results):
        _data = load_json_data(json_path)
        sr = ScanReport.from_dict(_data[0])
        src_type = sr.projects[0].source
        repo_name = sr.projects[0].repo_name
        metadata_file = sr.projects[0].metadata_file
        object_file = sr.projects[0].object_file
        detail_repo_dir = os.path.join(self.md_outdir, src_type, repo_name)
        os.makedirs(detail_repo_dir, exist_ok=True)
        md_path = os.path.join(detail_repo_dir, "README.md")
        mdFile = MdUtils(file_name=md_path, title=f'Sage Scan Report : [{repo_name}](https://github.com/{repo_name})')

        top_md_path = os.path.join(self.outdir, "README.md")
        relative_path = os.path.relpath(top_md_path, detail_repo_dir)
        parent_md_path = os.path.join(self.md_outdir, src_type, "README.md")
        relative_parent_path = os.path.relpath(parent_md_path, detail_repo_dir)

        if sr.error:
            mdFile.new_line(f"[<< Top Report]({relative_path})")
            mdFile.new_line(f"[< Src Type Report]({relative_parent_path})")
            mdFile.new_header(level=1, title='Scan Error')
            mdFile.new_line(f"Error: {sr.error}")
            mdFile.new_line(f"metadata_file: {metadata_file.replace(self.objects_root_dir, '')}")
            mdFile.new_line(f"object_file: {object_file.replace(self.objects_root_dir, '')}")
            mdFile.create_md_file()
            return

        mdFile.new_line(f"[<< Top Report]({relative_path})")
        mdFile.new_line(f"[< Src Type Report]({relative_parent_path})")
        mdFile.new_line(f"metadata_file: {metadata_file.replace(self.objects_root_dir, '')}")
        mdFile.new_line(f"object_file: {object_file.replace(self.objects_root_dir, '')}")
        mdFile.new_header(level=1, title='Detail reports')
        mdFile.new_line("[Scan Result](#scan-result)")
        mdFile.new_line("[Yaml file inventory](#yaml-file-inventory)")
        mdFile.new_line("[File result](#file-result)")

        mdFile.new_header(level=1, title='Scan Result')
        header = ["file count", "task count", "role count"]
        cells = header
        cells.append(sr.file_count.total)
        cells.append(sr.task_count.total)
        cells.append(sr.role_count.total)
        mdFile.new_table(columns=3, rows=2, text=cells, text_align='left')

        mdFile.new_header(level=1, title='Yaml file inventory')
        cells, c_num, r_num = self._gen_inventory_table(sr)
        mdFile.new_table(columns=c_num, rows=r_num, text=cells, text_align='left')

        mdFile.new_header(level=1, title='File Result')
        header = ["file", "type", "status", "task count", "error", "skip_reason", "role"]
        cells = header
        for ty in file_results:
            status = "" # success or fail or skipped or others
            if not ty.in_scope:
                status = "✔"
            elif ty.in_scope and not ty.scanned:
                status = ""
            elif ty.scanned:
                status = "✔"
            # cells.append(f"[{ty.path_in_project}](https://github.com/{repo_name}/blob/main/{ty.path_in_project})")
            cells.append(ty.path_in_project)
            cells.append(ty.type)
            cells.append(status)
            cells.append(ty.scanned_task_count)
            cells.append(ty.error)
            cells.append(ty.skip_reason)
            cells.append(ty.role)
        mdFile.new_table(columns=7, rows=len(file_results)+1, text=cells, text_align='left')
        mdFile.create_md_file()
        return
    
    def generate_src_report(self, src_type, json_path):
        src_dir = os.path.join(self.md_outdir, src_type)
        md_path = os.path.join(src_dir, "README.md")
        os.makedirs(src_dir, exist_ok=True)
        mdFile = MdUtils(file_name=md_path, title=f'Sage Scan Report : {src_type}')

        top_md_path = os.path.join(self.outdir, "README.md")
        relative_path = os.path.relpath(top_md_path, src_dir)
        mdFile.new_line(f"[<< Top Report]({relative_path})")

        mdFile.new_line("")
        mdFile.new_line("[Project Result](#project-result)")
        mdFile.new_line("[Yaml inventory](#yaml-inventory)")
        mdFile.new_line("[File result](#file-result)")
        mdFile.new_line("[Role and Task](#role-and-task)")
        mdFile.new_line("[Project List](#project-list)")

        # summary
        _data = load_json_data(json_path)
        sr = ScanReport.from_dict(_data[0])
        # project
        mdFile.new_header(level=1, title='Project Result')
        cells, c_num, r_num = self._gen_project_result_table(sr)
        mdFile.new_table(columns=4, rows=2, text=cells, text_align='left')

        # ymls
        mdFile.new_header(level=1, title='Yaml Inventory')
        cells, c_num, r_num = self._gen_inventory_table(sr)
        mdFile.new_table(columns=c_num, rows=r_num, text=cells, text_align='left')

        # role and task
        mdFile.new_header(level=1, title='Role and Task')
        cells, c_num, r_num = self._gen_role_task_table(sr)
        mdFile.new_table(columns=c_num, rows=r_num, text=cells, text_align='left')

        # repo list
        mdFile.new_header(level=1, title='Project List')
        header = ["project", "state", "files", "playbooks (passed/total)", "taskfiles (passed/total)", "others", "skipped", "errors", "roles", "tasks"]
        cells = header
        json_files = glob.glob(os.path.join(self.json_outdir, src_type, "**", "summary.json"), recursive=True)
        row_count = 0
        for jf in json_files:
            if jf.endswith(os.path.join(self.json_outdir, src_type, "summary.json")):
                continue
            row_count += 1
            _data = load_json_data(jf)
            sr = ScanReport.from_dict(_data[0])
            src_type = sr.projects[0].source
            repo_name = sr.projects[0].repo_name
            repo_md_path = os.path.join(self.md_outdir, src_type, repo_name, "README.md")
            relative_path = os.path.relpath(repo_md_path, src_dir)

            state = ""
            if sr.state_count.fail != 0:
                state = ""
            elif sr.state_count.unknown != 0:
                state = "-"
            elif sr.state_count.fail == 0:
                state = "✔"

            cells.append(f"[{repo_name}]({relative_path})")
            cells.append(state)
            cells.append(sr.file_count.total)
            cells.append(f"{sr.file_count.playbooks.scanned}/{sr.file_count.playbooks.total - sr.file_count.playbooks.skipped}")
            cells.append(f"{sr.file_count.taskfiles.scanned}/{sr.file_count.taskfiles.total - sr.file_count.taskfiles.skipped}")
            cells.append(sr.file_count.others.total)
            cells.append(sr.file_count.playbooks.skipped+sr.file_count.taskfiles.skipped)
            cells.append(sr.file_count.errors.total+sr.file_count.playbooks.scan_error+sr.file_count.taskfiles.scan_error)
            cells.append(sr.role_count.total)
            cells.append(sr.task_count.total)
        mdFile.new_table(columns=10, rows=row_count+1, text=cells, text_align='left')
        mdFile.create_md_file()
        return

    def generate_top_report(self, json_path):
        md_path = os.path.join(self.outdir, "README.md")
        mdFile = MdUtils(file_name=md_path, title=f'Sage Scan Report')

        # summary
        _data = load_json_data(json_path)
        sr = ScanReport.from_dict(_data[0])

        # mdFile.new_header(level=1, title='Project Result')
        # cells, c_num, r_num = self._gen_project_result_table(sr)
        # mdFile.new_table(columns=4, rows=2, text=cells, text_align='left')

        mdFile.new_header(level=1, title='Yaml Inventory')
        cells, c_num, r_num = self._gen_inventory_table(sr)
        mdFile.new_table(columns=c_num, rows=r_num, text=cells, text_align='left')

        mdFile.new_header(level=1, title='Role and Task')
        cells, c_num, r_num = self._gen_role_task_table(sr)
        mdFile.new_table(columns=c_num, rows=r_num, text=cells, text_align='left')

        # src type result
        mdFile.new_header(level=1, title='Src Type List')
        header = ["src type", "state", "projects", "files", "playbooks (passed/total)", "taskfiles (passed/total)", "others", "skipped", "errors", "roles", "tasks"]
        cells = header

        json_files = glob.glob(os.path.join(self.json_outdir, "**", "summary.json"))
        row_count = 0
        for jf in json_files:
            row_count += 1
            _data = load_json_data(jf)
            sr = ScanReport.from_dict(_data[0])
            src_type = sr.projects[0].source
            repo_md_path = os.path.join(self.md_outdir, src_type, "README.md")
            relative_path = os.path.relpath(repo_md_path, self.outdir)
            
            state = ""
            if sr.state_count.fail != 0:
                state = ""
            elif sr.state_count.unknown != 0:
                state = "-"
            elif sr.state_count.fail == 0:
                state = "✔"

            cells.append(f"[{src_type}]({relative_path})")
            cells.append(state)
            cells.append(sr.project_count)
            cells.append(sr.file_count.total)
            cells.append(f"{sr.file_count.playbooks.scanned}/{sr.file_count.playbooks.total - sr.file_count.playbooks.skipped}")
            cells.append(f"{sr.file_count.taskfiles.scanned}/{sr.file_count.taskfiles.total - sr.file_count.taskfiles.skipped}")
            cells.append(sr.file_count.others.total)
            cells.append(sr.file_count.playbooks.skipped+sr.file_count.taskfiles.skipped)
            cells.append(sr.file_count.errors.total+sr.file_count.playbooks.scan_error+sr.file_count.taskfiles.scan_error)
            cells.append(sr.role_count.total)
            cells.append(sr.task_count.total)
        mdFile.new_table(columns=11, rows=row_count+1, text=cells, text_align='left')
        mdFile.create_md_file()
        return


def export_result(filepath, results):
    with open(filepath, "w") as file:
        if type(results) == list:
            for result in results:
                json_str = jsonpickle.encode(result, make_refs=False, unpicklable=False)
                file.write(f"{json_str}\n")
        else:
            json_str = jsonpickle.encode(results, make_refs=False, unpicklable=False)
            file.write(f"{json_str}\n")

def load_json_data(filepath):
    with open(filepath, "r") as file:
        records = file.readlines()
    data = []
    for record in records:
        d = json.loads(record)
        data.append(d)
    return data

def split_data(work_dir, obj_file, metadata_file):
    ds1 = Data_Splitter(work_dir, OBJ_FILE)
    with open(obj_file, "r") as f:
        for line in f:
            j_content = json.loads(line)
            source = j_content.get("source", {})
            src_type = source.get("type", None)
            repo_name = source.get("repo_name", None)
            ds1.save_to_buffer(src_type, repo_name, line)
    ds1.save_all()

    ds2 = Data_Splitter(work_dir, META_FILE)
    with open(metadata_file, "r") as f:
        for line in f:
            j_content = json.loads(line)
            source = j_content.get("source", {})
            src_type = source.get("type", None)
            repo_name = source.get("repo_name", None)
            ds2.save_to_buffer(src_type, repo_name, line)
    ds2.save_all()
    return

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-o", "--out-dir", help='e.g. /tmp/batch/report')
    parser.add_argument("-i", "--input-dir", help="e.g. /tmp/batch/results")
    parser.add_argument("-f", "--file", help="object file")
    parser.add_argument("-m", "--metadata-file", help="metadata file")
    parser.add_argument("-t", "--type", help="e.g. GitHub-RHIBM")

    args = parser.parse_args()
    outdir = args.out_dir
    obj_file = args.file
    metadata_file = args.metadata_file
    input_dir = args.input_dir
    src_type = args.type

    # if input are merged objects and metadata file, split data
    if obj_file and metadata_file and not input_dir:
        tmpdir = tempfile.TemporaryDirectory()
        tmp_dir = tmpdir.name
        split_data(tmp_dir, obj_file, metadata_file)
        objects_dir = tmp_dir

    objects_dir = os.path.join(input_dir, src_type)


    if not os.path.exists(outdir):
        os.makedirs(outdir)
    
    json_outdir = os.path.join(outdir, "result_json")
    os.makedirs(json_outdir, exist_ok=True)
    report_dir = os.path.join(outdir, "detail")
    os.makedirs(report_dir, exist_ok=True)
    

    summarizer = ScanResultSummarizer(outdir, json_outdir, report_dir, input_dir)

    files = glob.glob(os.path.join(objects_dir, "**", OBJ_FILE), recursive=True)

    src_type_summaries = {}
    for obj_file in files:
        print(f"computing repo scan result ... {obj_file}")
        json_path, file_results = summarizer.generate_repo_summary(obj_file)
        # per repo md file
        summarizer.generate_repo_report(json_path, file_results)

    print("summarizing src_type scan result")
    target_dir = os.path.join(json_outdir, src_type)
    src_type_summary = summarizer.merge_repo_summary(target_dir)
    with open(os.path.join(target_dir, "summary.json"), "w") as file:
        file.write(src_type_summary.to_json(ensure_ascii=False))
    # src_type md file
    summarizer.generate_src_report(src_type, os.path.join(target_dir, "summary.json"))

    print("generating scan result for all")
    all_summary = summarizer.merge_src_summary(json_outdir)
    with open(os.path.join(json_outdir, "summary.json"), "w") as file:
        file.write(all_summary.to_json(ensure_ascii=False))
    # top md file
    summarizer.generate_top_report(os.path.join(json_outdir, "summary.json"))