from sage.models import SageObject, SageProject, Playbook, TaskFile, Play, Task
from ansible_risk_insight.models import Annotation


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


def get_tasks_in_play(play: Play, project: SageProject=None):
    task_keys = play.pre_tasks + play.tasks + play.post_tasks
    tasks = []
    for t_key in task_keys:
        task = project.get_object(key=t_key)
        if not task:
            continue
        tasks.append(task)
    return tasks


def get_tasks_in_taskfile(taskfile: TaskFile, project: SageProject=None):
    task_keys = taskfile.tasks
    tasks = []
    for t_key in task_keys:
        task = project.get_object(key=t_key)
        if not task:
            continue
        tasks.append(task)
    return tasks


def get_tasks_in_file(target: SageObject=None, project: SageProject=None):
    tasks = []
    if isinstance(target, Playbook):
        tasks = get_tasks_in_playbook(target, project)
    elif isinstance(target, TaskFile):
        tasks = get_tasks_in_taskfile(target, project)
    return tasks


def get_tasks(root: str | SageObject, project: SageProject=None):
    root_obj = root
    if isinstance(root, str):
        root_obj = project.get_object(key=root)
    return get_tasks_in_file(target=root_obj, project=project)


def get_call_sequence(target: Task=None, project: SageProject=None):
    return project.get_call_sequence(target)


def get_annotation(obj: SageObject, name: str):
    for anno in obj.annotations:
        print(anno)
    return None