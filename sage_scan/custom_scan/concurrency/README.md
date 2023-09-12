# Concurrent Custom Scan

## Prerequisites

1. `docker` and `docker-compose` command
2. ARI KB data on your machine
3. GitHub Personal Access Token for github.**ibm**.com with read permission for this repository

## Usage

### 1. Clone this repository and move to `concurrency` directory

```bash
$ git clone https://github.ibm.com/ansible-risk-insight/sage.git

$ cd sage_scan/custom_scan/concurrency
```

### 2. Export these 2 environment variables

```bash
$ export ARI_KB_DATA_DIR=<PATH/TO/YOUR_ARI_KB_DATA_DIR>

$ export GIT_ACCESS_TOKEN=<YOUR_GIT_ACCESS_TOKEN>
```

### 3. Run backends by `docker-compose` command

```bash
$ docker-compose up
```

### 4. Register tasks by `register.py`

After the step 3, you can register tasks by the following command.

NOTE: you will need another terminal window/tab for this step because the step 3 keeps showing docker-compose logs.

```bash
# specify `-t <soruce_type>` & `-s <src_json_file>`
$ python register.py -t GitHub-AC -s ~/Downloads/ansible-collections-dataset.json

--> Then, the worker container automatically detects the registered tasks and starts scanning.
    You will see some logs like the below in the docker-compose logs.

concurrency-worker-1     | [2023-08-16 00:42:42,470: INFO/ForkPoolWorker-3] Running data pipeline
concurrency-worker-1     | [2023-08-16 00:42:42,472: INFO/MainProcess] Task tasks.scan[a032d28f-d93b-4b2e-ae5d-cb6b7d37929f] received
concurrency-worker-1     | [2023-08-16 00:42:45,334: INFO/ForkPoolWorker-3] Start scanning for 1 projects (total 472 files)
concurrency-worker-1     | [2023-08-16 00:43:20,144: INFO/ForkPoolWorker-3] Done
```

### 5. Check scanning progress in the dashboard

open http://localhost:5556 in your browser


Also, you can check redis database directly if you have `redis-cli` command.

If `LLEN queue` returns `0`, it means that all registered scanning tasks are finished.

```bash
$ redis-cli

127.0.0.1:6379> LLEN queue
(integer) 0
```


### 6. Stop & remove containers

```bash
$ docker-compose down
```

