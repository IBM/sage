from sage.pipeline import SagePipeline
import os
import argparse


ARI_KB_DATA_DIR = os.getenv("ARI_KB_DATA_DIR", None)

if ARI_KB_DATA_DIR is None:
    raise ValueError(f"Please specify an existing ARI KB dir by an env param:\n$ export ARI_KB_DATA_DIR=<PATH/TO/ARI_KB_DATA_DIR>")

if not os.path.exists(ARI_KB_DATA_DIR):
    raise ValueError(f"the ARI_KB_DATA_DIR does not exist: {ARI_KB_DATA_DIR}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-d", "--dir", help='root direcotry for scan')
    parser.add_argument("-t", "--source-type", help='source type (e.g."GitHub-RHIBM")')
    parser.add_argument("-r", "--repo-name", help='repo name (e.g."IBM/Ansible-OpsnShift-Provisioning")')
    parser.add_argument("-o", "--out-dir", default="", help="output directory for the rule evaluation result")
    args = parser.parse_args()

    source = {}
    if args.source_type:
        source["type"] = args.source_type
    if args.repo_name:
        source["repo_name"] = args.repo_name

    dp = SagePipeline(
        ari_kb_data_dir=ARI_KB_DATA_DIR,
    )
    os.environ['SAGE_CONTENT_ANALYSIS_OUT_DIR'] = args.out_dir
    result = dp.run(
        target_dir=args.dir,
        output_dir=args.out_dir,
        source=source,
    )
