from sage.models import SageObject, SageProject, Playbook, TaskFile, Play, Task
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


# get all call sequences found in the SageProject
# call sequence is a sequence of objects executed by an entrypoint
# e.g.) Playbook --> Play 1 -> Task 1a -> Task 1b -> Play 2 -> Task 2a 
def get_all_call_sequences(project: SageProject):
    return project.get_all_call_sequences()


# get a call sequence which contains the specified task
def get_call_sequence_for_task(task: Task, project: SageProject):
    return project.get_call_sequence_for_task(task)


# embed `defined_vars` annotation to all objects in a call sequence
def set_defined_vars(call_seq: list):
    resolver = VariableResolver(call_seq=call_seq)
    resolver.set_defined_vars()
    call_seq = resolver.call_seq
    return