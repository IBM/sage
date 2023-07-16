from sage_data_pipeline.pipeline import DataPipeline
import os
import json
import argparse
from sage_data_pipeline.tools.src_rebuilder import write_result, prepare_source_dir

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-t", "--source_type", help='source type (e.g."GitHub-RHIBM")')
    parser.add_argument("-i", "--source_json", help='source json file path (e.g. "/tmp/RH_IBM_FT_data_GH_api.json")')
    parser.add_argument("-o", "--out-dir", help="output directory")
    args = parser.parse_args()

    work_dir = args.out_dir
    src_type = args.source_type
    src_json = args.source_json
    src_rb_dir = os.path.join(work_dir, "src_rb")
    path_list_dir = os.path.join(work_dir, "path_list")
    result_dir = os.path.join(work_dir, "results")
    adir = os.path.join(src_rb_dir, src_type)
    outfile = os.path.join(path_list_dir, f"path-list-{src_type}.txt")

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(src_rb_dir, exist_ok=True)
    os.makedirs(path_list_dir, exist_ok=True)
    os.makedirs(result_dir, exist_ok=True)

    path_list = prepare_source_dir(adir, "project", src_json)
    write_result(outfile, path_list)

    with open(src_json, "r") as f:
        records = f.readlines()
    repo_names = set()
    for record in records:
        r = json.loads(record)
        if "repo_name" in r:
            repo_names.add(r.get("repo_name"))

    dp = DataPipeline(
        ari_kb_data_dir=os.getenv("ARI_KB_DATA_DIR", "<PATH/TO/YOUR/ARI_KB_DATA_DIR>"),
        ari_rules_dir=os.path.join(os.path.dirname(__file__), "rules"),
    )

    for repo_name in repo_names:
        if repo_name != "IBM/Ansible-OpenShift-Provisioning":
            continue

        tdir = os.path.join(src_rb_dir, src_type, repo_name)
        odir = os.path.join(result_dir, src_type, repo_name)

        # why needed?
        os.environ["SAGE_CONTENT_ANALYSIS_OUT_DIR"] = odir

        dp.run(
            target_dir=tdir,
            output_dir=odir,
        )
