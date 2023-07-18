from mdutils.mdutils import MdUtils
from pathlib import Path
import os
import json
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    # parser.add_argument("-f", "--file", help='source yaml file')
    # parser.add_argument("-t", "--type", help='type of data source')
    # parser.add_argument("-d", "--dir", help='tmp dir to recreate source dir')
    # parser.add_argument("-o", "--out-file", help="output directory for the rule evaluation result")
    args = parser.parse_args()

    path_list_dir = "/tmp/batch/path_list"
    results = "/tmp/batch/results"
    ftdata_dir = "/tmp/batch/data"
    tmp_dir = "/tmp/batch/tmp"
    src_dir = "/tmp/batch/src_rb"

    # path_list_dirの中をあさって、 repo_nameごとのファイル数を調べる
    src_repos = {}
    for f in Path(path_list_dir).rglob("path-list-*.txt"):
        if Path.is_file(f):
            fname = os.path.splitext(os.path.basename(f))[0]
            src_type = fname.removeprefix("path-list-")
            repos = {}
            src_repos[src_type] = repos
            with open(f, "r") as fr:
                for line in fr:
                    jo = json.loads(line)
                    rn = jo.get("repo_name")
                    if rn in repos:
                        repos[rn] += 1
                    else:
                        repos[rn] = 1

    print(json.dumps(src_repos))

    export_path = "/tmp/aaaa1"
    mdFile = MdUtils(file_name=export_path, title='Sage Data Scan Report')

    mdFile.new_header(level=1, title='Path-List')
    
    for st in src_repos:
        mdFile.new_line(f"source={st}")
        cells = ["repo_name", "file count"]
        repos = src_repos[st]
        for rn, fc in repos.items():
            cells.append(rn)
            cells.append(fc)
        mdFile.new_table(columns=2, rows=len(repos) + 1, text=cells, text_align='left')

    # ファイルを生成する
    mdFile.create_md_file()


