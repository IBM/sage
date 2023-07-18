import argparse
import os
import json
import sys
from repo_writer import Repo_Writer

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--ftdata-file", default=None, help='original ftdata file (e.g. "awft_v5.5.2_train.json")')
    parser.add_argument("-d", "--ftdata-dir", help="ftdata dir")
    args = parser.parse_args()

    ftdata_dir = args.ftdata_dir
    ftdata_file = args.ftdata_file

    if ftdata_file is None or os.path.isfile(ftdata_file) is False:
        print(f"no ftdata exist: {ftdata_file}")
        sys.exit()

    rw = Repo_Writer(ftdata_dir)

    with open(ftdata_file, "r") as f:
        for line in f:
            j_content = json.loads(line)
            src_type = j_content.get("source", None)
            repo_name = j_content.get("repo_name", None)
            rw.save_to_buffer(src_type, repo_name, line)

    rw.save_all()
