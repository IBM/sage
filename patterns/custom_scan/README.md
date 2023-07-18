# Custom Scan with SagePipeline

## Running custom scan

1. Install this project
    ```
    $ git clone https://github.ibm.com/ansible-risk-insight/sage.git
    $ cd sage
    $ pip install -e .
    ```

2. Preapre ARI KB Data and set the KB dir to environment variable
     
    ```
    $ export ARI_KB_DATA_DIR=<PATH/TO/YOUR/ARI_KB_DATA_DIR>
    ```
3. Run the following command

    #### 2 arguments in the command below
    
    - `PATH/TO/PROJECT` ... Path to your target project to be processed with the pipeline. The directory can be an ansible project(repository), collection or role.
    
    - `OUTPUT_DIR` ... Path to the output directory. This will be created if it does not exist.

    ```
    $ python patterns/custom_scan/custom_scan.py -d <PATH/TO/PROJECT> -o <OUTPUT_DIR>
    ```

4. Confirm the output files

    The following 3 output files should be created in the specfied output directory.

    ```
    $ ls -l <OUTPUT_DIR>
    total 36992
    -rw-r--r--  1 root  wheel   1515326  7 14 15:27 ftdata.json
    -rw-r--r--  1 root  wheel  17361977  7 14 15:27 scan_result.json
    -rw-r--r--  1 root  wheel     58618  7 14 15:27 yml_inventory.json
    ```

    - `ftdata.json` ... Each line is task data JSON which is scanned by ARI. It is in the same format as FT Data and it has the same attributes such as `input_script` and `prompt`. Some additional field like `ari_new_context` or `ari_task_key` are added by the custom rule.
    - `scan_result.json` ... Each line is a task object JSON. All the scanned tasks are saved as ARI's Task object here.
    - `yml_inventory.json` ... All the found YAML files are recorded as a JSON string in each line. The pipeline adds some metadata about the file such as the file type like `playbook` and `taskfile` and the role info if the file is inside a role.
