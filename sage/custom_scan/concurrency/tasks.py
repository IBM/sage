from sage.pipeline import SagePipeline
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
