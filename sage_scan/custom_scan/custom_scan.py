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

from sage_scan.pipeline import SagePipeline
import os
import argparse


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

    dp = SagePipeline()
    os.environ['SAGE_CONTENT_ANALYSIS_OUT_DIR'] = args.out_dir
    result = dp.run(
        target_dir=args.dir,
        output_dir=args.out_dir,
        source=source,
    )
