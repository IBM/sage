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

import os
import argparse
import json
import redis
import time

from tasks import scan


REDIS_SERVER_URL = os.getenv("REDIS_SERVER_URL", 'localhost')
REDIS_SERVER_PORT = int(os.getenv("REDIS_SERVER_PORT", '6379'))
REDIS_SERVER_DB = int(os.getenv("REDIS_SERVER_DB", '0'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-o", "--out-dir", default="/work_dir/results", help="output directory for the rule evaluation result")
    args = parser.parse_args()

    os.environ['SAGE_CONTENT_ANALYSIS_OUT_DIR'] = args.out_dir

    redis_client = redis.Redis(
        host=REDIS_SERVER_URL,
        port=REDIS_SERVER_PORT,
        db=REDIS_SERVER_DB,
    )

    while True:
        task_input_str = redis_client.lpop('queue')
        if not task_input_str:
            time.sleep(3)
            continue
        task_input = json.loads(task_input_str)
        dir_path = task_input["dir_path"]
        source_type = task_input["source_type"]
        repo_name = task_input["repo_name"]
        out_dir = os.path.join(args.out_dir, source_type, repo_name)
        timeout = task_input.get("timeout", None)
        
        kwargs = {
            "dir_path": dir_path,
            "source_type": source_type,
            "repo_name": repo_name,
            "out_dir": out_dir,
        }

        if timeout:
            result = scan.apply_async(kwargs=kwargs, time_limit=timeout)
        else:
            result = scan.apply_async(kwargs=kwargs)