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
import json
import redis
from sage_scan.tools.src_rebuilder import write_result, prepare_source_dir


REDIS_SERVER_URL = os.getenv("REDIS_SERVER_URL", 'localhost')
REDIS_SERVER_PORT = int(os.getenv("REDIS_SERVER_PORT", '6379'))
REDIS_SERVER_DB = int(os.getenv("REDIS_SERVER_DB", '0'))


def check_if_result_exists(result_dir: str, src_type: str, repo_name: str):
    objects_path = os.path.join(result_dir, src_type, repo_name, "sage-objects.json")
    exists = os.path.exists(objects_path)
    return exists


# TODO: imeplement this
def is_task_queued(redis_client: redis.Redis, queue_name: str, src_type: str, repo_name: str):
    # redis_client.lrange(queue_name, 0, -1)
    return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--filepath", default="", help="filepath to custom scan input JSON")
    

    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-t", "--source-type", help='source type (e.g."GitHub-RHIBM")')
    parser.add_argument("-s", "--source-json", help='source json file path (e.g. "/tmp/RH_IBM_FT_data_GH_api.json")')
    parser.add_argument("-o", "--out-dir", default="./sage_concurrency_work_dir", help="output directory")
    parser.add_argument("--timeout", help="timeout seconds")
    parser.add_argument("--resume", action="store_true", help="if true, only tasks without existing results are registered (queued tasks are also skipped)")
    parser.add_argument("--dry-run", action="store_true", help="if true, it does not register tasks actually (normally use this mode with `--save` option)")
    parser.add_argument("--save", action="store_true", help="if true, save a json file which is a list of registered projects")
    args = parser.parse_args()

    work_dir = args.out_dir
    in_container_work_dir = "/work_dir"
    src_type = args.source_type
    src_json = args.source_json
    src_rb_dir = os.path.join(work_dir, "src_rb")
    path_list_dir = os.path.join(work_dir, "path_list")
    result_dir = os.path.join(work_dir, "results")

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(src_rb_dir, exist_ok=True)
    os.makedirs(path_list_dir, exist_ok=True)
    os.makedirs(result_dir, exist_ok=True)

    adir = os.path.join(src_rb_dir, src_type)
    if not os.path.exists(adir) or len(os.listdir(adir)) == 0:
        outfile = os.path.join(path_list_dir, f"path-list-{src_type}.txt")
        path_list = prepare_source_dir(adir, src_json)
        write_result(outfile, path_list)

    repo_names = set()
    if src_json:
        with open(src_json, "r") as f:
            records = f.readlines()
        
        for record in records:
            r = json.loads(record)
            if "repo_name" in r:
                repo_names.add(r.get("repo_name"))
            elif "namespace_name" in r:
                repo_names.add(r.get("namespace_name"))

    redis_client = redis.Redis(
        host=REDIS_SERVER_URL,
        port=REDIS_SERVER_PORT,
        db=REDIS_SERVER_DB,
    )

    count = 0
    registerd_lines = []
    for repo_name in repo_names:
        if args.resume:
            if check_if_result_exists(result_dir, src_type, repo_name):
                # skip because the result exists
                continue
            # print(repo_name)
            
            # TODO: imeplement this
            # if is_task_queued(redis_client, "queue", src_type, repo_name):
            #     # skip because the task is found in the current queue
            #     continue

        target_dir = os.path.join(in_container_work_dir, "src_rb", src_type, repo_name)
        
        task_input = {
            "dir_path": target_dir,
            "source_type": src_type,
            "repo_name": repo_name,
        }
        if args.timeout:
            task_input["timeout"] = int(args.timeout)

        task_input_str = json.dumps(task_input)
        if not args.dry_run:
            redis_client.rpush("queue", task_input_str)
        count += 1
        registerd_lines.append(task_input_str + "\n")

    dry_run_msg = ""
    if args.dry_run:
        dry_run_msg = " [DRY_RUN]"

    print(f"scan for {count} projects has been registered.{dry_run_msg}")

    if args.save:
        registerd_file = "registered_projects.json"
        with open(registerd_file, "w") as file:
            file.write("".join(registerd_lines))
