from sage_data_pipeline.pipeline import DataPipeline
import os
import argparse


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-d", "--dir", help='root direcotry for scan')
    parser.add_argument("--rule", default="PP006", help="rule id (default to \"PP006\")")
    parser.add_argument("-o", "--out-dir", default="", help="output directory for the rule evaluation result")
    args = parser.parse_args()

    dp = DataPipeline(
        ari_kb_data_dir=os.getenv("ARI_KB_DATA_DIR", "<PATH/TO/YOUR/ARI_KB_DATA_DIR>"),
        ari_rules_dir=os.path.join(os.path.dirname(__file__), "rules"),
    )
    os.environ['SAGE_CONTENT_ANALYSIS_OUT_DIR'] = args.out_dir
    dp.run(
        target_dir=args.dir,
        output_dir=args.out_dir,
    )
