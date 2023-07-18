import argparse
import os
import json
import sys
from pathlib import Path

from add_enrich_context import Mapping, add_repo_info_from_inventory


def load_source_types(file):
    src_types = {}
    with open(file, "r") as f:
        for line in f:
            j_content = json.loads(line)
            source = j_content.get("source", None)
            repo_name = j_content.get("repo_name", None)
            if source and repo_name:
                if source not in src_types:
                    src_types[source] = [repo_name]
                elif repo_name not in src_types[source]:
                    src_types[source].append(repo_name)
    return src_types


class Repo_Writer:
    def __init__(self, out_dir) -> None:
        self.out_dir = out_dir
        self._buffer = {}
        self.max_buffer = 100

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
        os.makedirs(os.path.join(out_dir, src_type, repo_name), exist_ok=True)
        file = os.path.join(out_dir, src_type, repo_name, "org-ftdata.json")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-s", "--sage-dir", help="sage data dir (output dir from scan)")
    parser.add_argument("-f", "--ftdata", default=None, help='original ftdata file (e.g. "awft_v5.5.2_train.json")')
    parser.add_argument("-o", "--out-dir", help="result dir")
    parser.add_argument("-t", "--src-type", help='source type (e.g. "GitHub-RHIBM")')
    args = parser.parse_args()

    sage_dir = args.sage_dir
    if not os.path.isdir(sage_dir):
        print(f"no sage_dir exist: {sage_dir}")
        sys.exit()

    out_dir = args.out_dir
    target_src_type = args.src_type
    w_ftdata_file = args.ftdata

    repo_names = []
    if w_ftdata_file is not None and os.path.isfile(w_ftdata_file):
        src_types = load_source_types(w_ftdata_file)
        if target_src_type not in src_types:
            print(f"no src type found in ftdata {w_ftdata_file}")

        rw = Repo_Writer(out_dir)

        with open(w_ftdata_file, "r") as f:
            for line in f:
                j_content = json.loads(line)
                src_type = j_content.get("source", None)
                repo_name = j_content.get("repo_name", None)
                rw.save_to_buffer(src_type, repo_name, line)

        rw.save_all()
        repo_names = rw.get_repo_names(target_src_type)

    else:
        # for f in Path(out_dir).rglob('*/org-ftdata.json'):
        for f in Path(os.path.join(out_dir, target_src_type)).rglob("*/org-ftdata.json"):
            if Path.is_file(f):
                d1 = os.path.dirname(f)
                s1 = d1.removeprefix(out_dir)
                a1 = s1.split("/")
                st = a1[1]
                rn = "/".join(a1[2:])
                repo_names.append(rn)

    for repo_name in repo_names:
        print(f"adding context for {repo_name} in {target_src_type}")
        sage_repo_dir = os.path.join(sage_dir, target_src_type, repo_name)
        inventory_file = os.path.join(sage_repo_dir, "yml_inventory.json")
        sage_ftdata = os.path.join(sage_repo_dir, "ftdata.json")
        if not os.path.isfile(inventory_file):
            print(f"no inventory file {inventory_file}")
            continue
        if not os.path.isfile(sage_ftdata):
            print(f"no sage ftdata file {sage_ftdata}")
            continue

        tmp_sage_ftdata = os.path.join(sage_repo_dir, "ftdata-modified.json")  # with correct path
        wisdom_input = os.path.join(out_dir, target_src_type, repo_name, "org-ftdata.json")
        add_repo_info_from_inventory(inventory_file, sage_ftdata, tmp_sage_ftdata)
        output_dir = os.path.join(out_dir, target_src_type, repo_name)
        print(f"m.run():wisdom_input={wisdom_input},tmp_sage_ftdata={tmp_sage_ftdata},output_dir={output_dir}")
        m = Mapping(output_dir)
        m.run(tmp_sage_ftdata, wisdom_input, target_src_type, repo_name)
