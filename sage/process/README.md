
## `sage.process` package

This package has some utility functions that can be used for processing output objects from Sage such as `sage-objects.json`.

### Utils

Functions and descriptions

- `get_tasks_in_playbook`: Find all task objects in the specified playbook

- `get_tasks_in_play`: Find all task objects in the specified play

- `get_tasks_in_taskfile`: Find all task objects in the specified taskfile

- `get_tasks`: Find all task objects in the specified playbook or taskfile (input can be an object id)

- `get_plays`: Find all play objects in the specified playbook

- `get_taskfiles_in_role`: Find all taskfiles in the speciifed role from SageProject

- `find_parent_role`: Find a parent role for the specified taskfile if it exists

- `get_all_call_sequences`: Get all call sequences found in the project
   ```
   NOTE) A call sequence is a sequence of objects executed by an entrypoint
         e.g.) Playbook --> Play 1 -> Task 1a -> Task 1b -> Play 2 -> Task 2a

         Sage assumes that playbooks, roles and taskfiles can be entrypoints 
   ```

- `get_call_sequence_for_task`: Get a call sequence which contains the specified task

- `get_task_sequence_by_entrypoint`: Get task sequence which starts from the specified entrypoint

- `get_task_sequence_for_playbook`: Get a task sequence which starts from the specified playbook

- `get_task_sequences_for_role`: Get a task sequences which starts from the specified role

    ```
    NOTE) this returns a list of task sequences; each sequence starts from a single taskfile in the role
    ```

- `get_task_sequence_for_taskfile`: Get a task sequences which starts from the specified taskfile

- `set_defined_vars`: Set `defined_vars` annotation to all objects in a call sequence

- `get_defined_vars`: Get defined vars for the specified object

- `list_entrypoints`: Returns all entrypoint objects in SageProject
    ```
    NOTE) playbooks, roles and independent taskfiles (=not in a role) can be an entrypoint
    ```