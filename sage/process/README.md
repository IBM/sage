
## `sage.process` package

This package has some utility functions that can be used for processing output objects from Sage such as `sage-objects.json`.

### Utils

Functions and descriptions

- `get_tasks_in_playbook`: Find all task objects in the specified playbook

- `get_tasks_in_play`: Find all task objects in the specified play

- `get_tasks_in_taskfile`: Find all task objects in the specified taskfile

- `get_tasks`: Find all task objects in the specified playbook or taskfile (input can be an object id)

- `get_plays`: Find all play objects in the specified playbook

- `get_all_call_sequences`: Get all call sequences found in the project
   ```
   NOTE) A call sequence is a sequence of objects executed by an entrypoint
         e.g.) Playbook --> Play 1 -> Task 1a -> Task 1b -> Play 2 -> Task 2a

         Sage assumes that playbooks, roles and taskfiles can be entrypoints 
   ```

- `get_call_sequence_for_task`: Get a call sequence which contains the specified task

- `set_defined_vars`: Set `defined_vars` annotation to all objects in a call sequence