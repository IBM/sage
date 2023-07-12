# sage-data-pipeline

This project is a data pipeline framework and practical examples for generating/processing task data like the fine-tuning data for various purposes.

The pipeline framework utilizes Ansible Risk Insight to parse Ansible content in YAML files (or prompt string in an existing FT data) and to apply configured rules for processing data depending on use-cases.

## Installation

Run the following command after `git clone`.

```
$ pip install -e .
```

## Use-cases

You can find some exmaples use-cases in [examples](./examples/).

### 1. Generate fine-tuning data from source directories

By inputting a path list of source directories (roles, collections, projects and etc.), the pipeline executes ARI scan for them and the ARI rules (found [here](examples/generate_ftdata/rules/)) generate the FT data for the scanned Ansible objects.

Each line is a task data processed by the rules in JSON format like the "original" FT data.

### 2. Detect deprecated modules in an existing FT data

By inputting an existing FT data, the pipeline triggers ARI scan on the YAML in each entry, then it detects deprecated modules. 

Then the pipeline adds an additional metadata `is_deprecated` into FT data which indicates whether any deprecated modules are used in the task or not, and `alternative_for_deprecated` is a string configured in the module documentation like [this](https://github.com/ansible-collections/ibm.qradar/blob/main/plugins/modules/log_source_management.py#L19) 

### 3. Improve data quality of an existing FT data (WIP)

Apply post-processing rules that are currently available for ansible-wisdom-service to an existing FT data