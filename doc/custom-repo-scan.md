# Creating training data specific to a customer

![custom-repo-scan](./images/custom-repo-scan.png)

- b1: In this step, all the YAML files in the directory are scanned. The content of each YAML file is parsed with YAML parser, and one of the following content type is identified
  - playbook
  - taskfile
  - other (requirement.yml, role-related YAML files etc.)

  Then, from those YAML files, role root directories are identified by finding a role directory patterns (e.g. “tasks/xxxx.yml” and  other files in “vars/main.yml”, “defaults/main.yml”, “meta/main.yml”, etc.)
- b2: After YAML file inventory, all files are parsed as Ansible content and an object tree is produced (saved as scan result). Tasks are the leafs of the tree and already analyzed like
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
- b3: Based on the scan result above, custom logic (E.g. [gen_ftdata.py](../sage/process/gen_ftdata.py)) can be applied to process the data. For example, fine-tuning dataset can be exported by using a script above. The record includes
  - prompt
  - input_script (context)
  - output_script (task spec)

  In this step, any scripts including ARI rules can be inserted to process the data. For example, data cleaning like post-processing can be applied before writing the record. Customers can also extend it by adding any scripts to manipulate the dataset. 
