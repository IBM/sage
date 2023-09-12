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
import time
import traceback
from celery import Celery



dp = SagePipeline()


REDIS_SERVER_URL = os.getenv("REDIS_SERVER_URL", 'localhost')
REDIS_SERVER_PORT = int(os.getenv("REDIS_SERVER_PORT", '6379'))
REDIS_SERVER_DB = int(os.getenv("REDIS_SERVER_DB", '0'))

SINGLE_SCAN_TIMEOUT = int(os.getenv("SINGLE_SCAN_TIMEOUT", '450'))

CELERY_BROKER_URL = f"redis://{REDIS_SERVER_URL}:{REDIS_SERVER_PORT}/1"
CELERY_RESULT_BACKEND = f"redis://{REDIS_SERVER_URL}:{REDIS_SERVER_PORT}/2"


celery = Celery(__name__)
celery.conf.broker_url = CELERY_BROKER_URL
celery.conf.result_backend = CELERY_RESULT_BACKEND


@celery.task(name='tasks.scan')
def scan(dir_path: str, source_type: str, repo_name: str, out_dir: str) -> dict:
    source = {
        "type": source_type,
        "repo_name": repo_name,
    }
    result = {
        "success": None,
        "error": None,
        "begin": time.time(),
        "end": None,
    }
    err = None
    try:
        _ = dp.run(
            target_dir=dir_path,
            output_dir=out_dir,
            source=source,
        )
    except Exception:
        err = traceback.format_exc()
    finally:
        success = False if err else True
        result["success"] = success
        if not success:
            result["error"] = err
        result["end"] = time.time()
    return result
