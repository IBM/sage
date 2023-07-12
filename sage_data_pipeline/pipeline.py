from ansible_risk_insight.scanner import ARIScanner, config, Config
from ansible_risk_insight.models import NodeResult, RuleResult, TargetResult
from ansible_risk_insight.finder import (
    find_all_ymls,
    label_yml_file,
    get_role_info_from_path,
    get_project_info_for_file,
)
from ansible_risk_insight.risk_detector import load_rules
from ansible_risk_insight.utils import escape_local_path
from sage_data_pipeline.pipeline import DataPipeline
import os
import argparse
import time
import traceback
import joblib
import threading
import jsonpickle
import json



def get_rule_id_list(rules_dir=""):
    rules = load_rules(rules_dir=rules_dir)
    rule_id_list = [rule.rule_id for rule in rules]
    return rule_id_list


class Pipeline(object):
    args = None
    _scanner = None
    start = None
    aggregation_rule_id = "FP001"

    def __init__(self, args):
        self.args = args

        use_ansible_doc = True
        read_ram = True
        write_ram = False

        data_dir = "/Users/hiro/ari-kb/ram-generate/ram-all-20230704"
        self.data_dir = data_dir
        self._scanner = ARIScanner(
            Config(
                rules_dir=os.path.join(os.path.dirname(__file__), "rules"),
                # data_dir=config.data_dir,
                data_dir=data_dir,
                rules=[
                    "P001",
                    "P002",
                    "P003",
                    "P004",
                ] + get_rule_id_list(os.path.join(os.path.dirname(__file__), "rules")),
            ),
            silent=True,
            use_ansible_doc=use_ansible_doc,
            persist_dependency_cache=True,
            read_ram=read_ram,
            write_ram=write_ram,
        )

    def load_ftdata_file(self, fpath):
        data = []
        with open(fpath, "r") as file:
            for line in file:
                d = json.loads(line)
                data.append(d)
        return data

    def run(self, in_fpath, out_fpath, do_process=False):
        args = self.args
        resume = -1
        if args.resume:
            resume = int(args.resume)

        ftdata = self.load_ftdata_file(in_fpath)

        num = len(ftdata)
        resume_str = f"(resume from {resume})" if resume > 0 else ""
        total_str = f"{len(ftdata)} entries"

        print(f"Start scanning for {total_str} {resume_str}")

        _types = {
            "task": "taskfile",
            "playbook": "playbook",
        }

        def entry2input(i, entry):
            _type = _types[entry["type"]]
            _yaml = entry["input_script"] + entry["output_script"]
            source = entry["source"]
            repo_name = entry["repo_name"]
            path = entry["path"]
            _display_name = f"{source} - {repo_name} - {path}"
            return (i, num, _type, _yaml, _display_name, entry)

        input_list = [ entry2input(i, entry) for i, entry in enumerate(ftdata) ]

        i = 0
        self.start = time.time()
        updated_ftdata = []
        for (i, num, _type, yaml, display_name, entry) in input_list:
            updated_entry = self.scan(i, num, _type, yaml, display_name, entry)
            if updated_entry:
                updated_ftdata.append(updated_entry)
        
        self.save(out_fpath, updated_ftdata)

    def scan(self, i, num, type, yaml, display_name, entry):
        elapsed = round(time.time() - self.start, 2)
        start_of_this_scan = time.time()
        thread_id = threading.get_native_id()
        print(f"[{i+1}/{num}] start {display_name} ({elapsed} sec. elapsed) (thread: {thread_id})")

        result = None
        scandata = None
        try:
            result = self._scanner.evaluate(
                type=type,
                raw_yaml=yaml
            )
            scandata = self._scanner.get_last_scandata()
        except Exception:
            error = traceback.format_exc()
            self._scanner.save_error(error)
            if error:
                print(f"Failed to scan {display_name}: error detail: {error}")

        changes = {}
        if result:
            prompt = entry["prompt"].split("name: ")[-1]
            for target_result in result.targets:
                if not isinstance(target_result, TargetResult):
                    raise ValueError(f"target_result must be a TargetResult instance, but {type(target_result)}")
                
                node_result = target_result.task(name=prompt)
                if not node_result:
                    continue
                if not isinstance(node_result, NodeResult):
                    raise ValueError(f"node_result must be a NodeResult instance, but {type(node_result)}")
                rule_result = node_result.find_result(self.aggregation_rule_id)
                if not isinstance(rule_result, RuleResult):
                    raise ValueError(f"rule_result must be a RuleResult instance, but {type(rule_result)}")
                
                detail = rule_result.get_detail()
                changes = detail.get("changes", {})
        else:
            raise ValueError("no result returned")
        
        updated_entry = entry.copy()
        updated_entry.update(changes)

        elapsed_for_this_scan = round(time.time() - start_of_this_scan, 2)
        if elapsed_for_this_scan > 60:
            print(f"WARNING: It took {elapsed_for_this_scan} sec. to process [{i+1}/{num}] {display_name}")

        return updated_entry
    

    def save(self, fpath, ftdata):
        out_dir = os.path.dirname(fpath)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        
        lines = [json.dumps(d) + "\n" for d in ftdata]
        with open(fpath, "w") as file:
            file.write("".join(lines))
   

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--file", help='ftdata file path')
    parser.add_argument("-r", "--resume", help="line number to resume scanning")
    parser.add_argument("--serial", action="store_true", help="if true, do not parallelize ram generation")
    parser.add_argument("-o", "--output", default="", help="output file path for the rule evaluation result")
    args = parser.parse_args()

    pipeline = Pipeline(args=args)

    in_fpath = args.file
    out_fpath = args.output

    pipeline.run(in_fpath, out_fpath)
