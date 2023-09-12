# Creating training data specific to a customer

![custom-repo-scan](./images/custom-repo-scan.png)

## Sage Scan

First, you can generate sage object files for any source repository by the following command.

```
$ python sage_scan/custom_scan/custom_scan.py -d <TARGET_DIR> -o <OUTPUT_DIR> -t <SOURCE> -r <REPO_NAME>
```

Descriptions for the arguments are:

- `TARGET_DIR`: A source directory to be scanned
- `OUTPUT_DIR`: An output directory
- `SOURCE`: Source type string like "Galaxy-C" and "GitHub-AC"
- `REPO_NAME`: A repo name of the target repository


#### Step: b1
- In this step, all the YAML files in the directory are scanned. The content of each YAML file is parsed with YAML parser, and one of the following content type is identified
  - playbook
  - taskfile
  - other (requirement.yml, role-related YAML files etc.)

  Then, from those YAML files, role root directories are identified by finding a role directory patterns (e.g. “tasks/xxxx.yml” and  other files in “vars/main.yml”, “defaults/main.yml”, “meta/main.yml”, etc.)

#### Step: b2
- After YAML file inventory, all files are parsed as Ansible content and an object tree is produced (saved as scan result). Tasks are the leafs of the tree and already analyzed like
  - name
  - task keywords (e.g. become, loop, register, etc.)
  - module name, FQCN, module spec (from ARI KB)
  - module arguments
  - file path in source
  - line in original source file
  - annotations
  - variables used in the task
  - variables defined before the task

  In addition to tasks, all other useful information is scanned, then new ARI KB can be created from it for the later update. 
  - modules
  - module-specs
  - metadata for collections and roles
  - external dependencies


## Sage Processing

#### Step: b3

Once, you get sage object files from the previous steps, you can process them to generate training dataset by using [gen_ftdata.py](https://github.ibm.com/ansible-risk-insight/sage-process/blob/main/sage_process/gen_ftdata.py) in [sage-process](https://github.ibm.com/ansible-risk-insight/sage-process) project. 

```
$ python sage_process/gen_ftdata.py -f <OBJECTS_FILE> -o <OUTPUT_FILE>
```

Descriptions for the arguments are:

- `OBJECTS_FILE`: A generated sage-objects.json from the previous step. This can be a combined file with multiple sage-objects.json files.
- `OUTPUT_FILE`: An output training dataset file
