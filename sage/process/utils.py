from sage.models import SageObject, SageProject, Playbook, TaskFile, Play, Task, Role
from sage.process.variable_resolver import VariableResolver
from ansible_risk_insight.models import Annotation


# find all tasks defined in the specified playbook from SageProject
def get_tasks_in_playbook(playbook: Playbook, project: SageProject=None):
    play_keys = playbook.plays
    tasks = []
    for p_key in play_keys:
        play = project.get_object(key=p_key)
        if not play:
            continue
        p_tasks = get_tasks_in_play(play, project)
        tasks.extend(p_tasks)
    return tasks


# find all tasks defined in the specified play from SageProject
def get_tasks_in_play(play: Play, project: SageProject=None):
    task_keys = play.pre_tasks + play.tasks + play.post_tasks
    tasks = []
    for t_key in task_keys:
        task = project.get_object(key=t_key)
        if not task:
            continue
        tasks.append(task)
    return tasks


# find all tasks defined in the specified taskfile from SageProject
def get_tasks_in_taskfile(taskfile: TaskFile, project: SageProject=None):
    task_keys = taskfile.tasks
    tasks = []
    for t_key in task_keys:
        task = project.get_object(key=t_key)
        if not task:
            continue
        tasks.append(task)
    return tasks


# find all tasks defined in the specified playbook or taskfile from SageProject
def get_tasks_in_file(target: Playbook|TaskFile=None, project: SageProject=None):
    tasks = []
    if isinstance(target, Playbook):
        tasks = get_tasks_in_playbook(target, project)
    elif isinstance(target, TaskFile):
        tasks = get_tasks_in_taskfile(target, project)
    return tasks


# find all tasks defined in the specified playbook or taskfile from SageProject
# if `root` is an object key, get the object from SageProject first
def get_tasks(root: str | SageObject, project: SageProject=None):
    root_obj = root
    if isinstance(root, str):
        root_obj = project.get_object(key=root)
    return get_tasks_in_file(target=root_obj, project=project)


# find all plays defined in the specified playbook from SageProject
def get_plays(playbook: Playbook, project: SageProject):
    play_keys = playbook.plays
    plays = []
    for p_key in play_keys:
        play = project.get_object(key=p_key)
        if not play:
            continue
        if not isinstance(play, Play):
            continue
        plays.append(play)
    return plays


# find all taskfiles in the speciifed role from SageProject
def get_taskfiles_in_role(role: Role, project: SageProject):
    taskfile_keys = role.taskfiles
    taskfiles = []
    for tf_key in taskfile_keys:
        taskfile = project.get_object(key=tf_key)
        if not taskfile:
            continue
        if not isinstance(taskfile, TaskFile):
            continue
        taskfiles.append(taskfile)
    return taskfiles


# find a parent role for the specified taskfile if it exists
def find_parent_role(taskfile: TaskFile, project: SageProject):
    for role in project.roles:
        taskfile_keys = role.taskfiles
        if taskfile.key in taskfile_keys:
            return role
    return None


# get all call sequences found in the SageProject
# call sequence is a sequence of objects executed by an entrypoint
# e.g.) Playbook --> Play 1 -> Task 1a -> Task 1b -> Play 2 -> Task 2a 
def get_all_call_sequences(project: SageProject):
    return project.get_all_call_sequences()


# get a call sequence which contains the specified task
def get_call_sequence_for_task(task: Task, project: SageProject):
    return project.get_call_sequence_for_task(task)


# get call sequence which starts from the specified entrypoint
def get_call_sequence_by_entrypoint(entrypoint: Playbook|Role|TaskFile, project: SageProject):
    return project.get_call_sequence_by_entrypoint(entrypoint)


# get task sequence which starts from the specified entrypoint
def get_task_sequence_by_entrypoint(entrypoint: Playbook|Role|TaskFile, project: SageProject):
    call_seq = get_call_sequence_by_entrypoint(entrypoint, project)
    if not call_seq:
        return None
    return [obj for obj in call_seq if isinstance(obj, Task)]


# get a task sequence which starts from the specified playbook
def get_task_sequence_for_playbook(playbook: Playbook, project: SageProject):
    return get_task_sequence_by_entrypoint(playbook, project)


# get a task sequences which starts from the specified role
# this returns a list of task sequences; each sequence starts from a single taskfile in the role
def get_task_sequences_for_role(role: Role, project: SageProject):
    taskfiles = get_taskfiles_in_role(role, project)
    task_seq_list = []
    for taskfile in taskfiles:
        task_seq = get_task_sequence_by_entrypoint(taskfile, project)
        if not task_seq:
            continue
        task_seq_list.append(task_seq)
    return task_seq_list


# get a task sequences which starts from the specified taskfile
def get_task_sequence_for_taskfile(taskfile: TaskFile, project: SageProject):
    return get_task_sequence_by_entrypoint(taskfile, project)


# embed `defined_vars` annotation to all objects in a call sequence
def set_defined_vars(call_seq: list):
    resolver = VariableResolver(call_seq=call_seq)
    obj_and_vars_list = resolver.set_defined_vars()
    call_seq = resolver.call_seq
    return obj_and_vars_list


# get defined vars for the specified object
# if object is a TaskFile, this returnes defined vars of a Role which contains the TaskFile if found
def get_defined_vars(object: SageObject, project: SageProject):
    target = object
    obj_list = [object]
    if isinstance(object, TaskFile):
        role = find_parent_role(object, project)
        if role:
            target = role
            obj_list = [role, object]

    resolver = VariableResolver(call_seq=obj_list)
    return resolver.get_defined_vars(object=target)


# returns all entrypoint objects
# playbooks, roles and independent taskfiles (=not in a role) can be an entrypoint
def list_entrypoints(project: SageProject):
    entrypoints = []
    entrypoints.extend(project.playbooks)
    entrypoints.extend(project.roles)
    # only independent taskfiles; skip taskfiles in role
    entrypoints.extend([tf for tf in project.taskfiles if not tf.role])
    return entrypoints
