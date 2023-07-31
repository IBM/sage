import os
import argparse
import json
import yaml
from sage.process.utils import get_tasks
from sage.models import Task, Playbook, TaskFile, Play, SageProject, load_objects


def extract_play_names(task: Task, parent: Playbook | TaskFile, project: SageProject):

    _type = ""
    play_names = []
    if isinstance(parent, Playbook):
        _type = "playbook"
        for play_key in parent.plays:
            play = project.get_object(key=play_key)
            if play and isinstance(play, Play):
                play_names.append(play.name)
    elif isinstance(parent, TaskFile):
        _type = "task"

    has_valid_play_name = len([pn for pn in play_names if pn]) > 0

    task_name = task.name
    yaml_lines = task.yaml_lines

    prompt = ""
    output_script = yaml_lines
    if task_name:
        separator = task_name
        if task_name not in yaml_lines and task_name[-1] == ".":
            separator = task_name[:-1]
        parts = yaml_lines.split(separator)
        if len(parts) >= 2:
            prompt = parts[0] + task_name
            output_script = parts[1].lstrip(" ").lstrip("\n")

    parent_yaml = parent.yaml_lines
    if task.line_num_in_file:
        task_line_num = task.line_num_in_file[0]
        context = "\n".join(parent_yaml.splitlines()[:task_line_num-1])
    else:
        context = parent_yaml
    context_prompt = context + "\n" + prompt
    play_without_tasks = get_play_without_tasks(context)

    data = {
        "context_prompt": context_prompt,
        "context": context,
        "prompt": prompt,
        "play": play_without_tasks,
        "type": _type,
        "play_names": play_names,
        "has_valid_play_name": has_valid_play_name,
    }
    return data


def get_play_without_tasks(context):
    data = None
    err = None
    try:
        data = yaml.safe_load(context)
    except Exception as exc:
        err = exc
    if err:
        return context
    
    if not data:
        return context
    if not isinstance(data, list):
        return context
    if not isinstance(data[0], dict):
        return context
    
    if "tasks" in data[0]:
        data[0].pop("tasks")
    if "pre_tasks" in data[0]:
        data[0].pop("pre_tasks")
    if "post_tasks" in data[0]:
        data[0].pop("post_tasks")
    
    play_without_tasks = ""
    try:
        play_without_tasks = yaml.safe_dump(data, sort_keys=False)
    except Exception as exc:
        err = exc
    
    if err:
        return context
    
    return play_without_tasks


def main():
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--file", help='input json file')
    parser.add_argument("-o", "--output", help='output json file')
    args = parser.parse_args()

    fpath = args.file

    sage_objects = load_objects(fpath)
    projects = sage_objects.projects()
    lines = []

    uniq_plays = set()
    for project in projects:
        playbooks = project.playbooks
        taskfiles = project.taskfiles

        for p in playbooks:
            tasks = get_tasks(root=p, project=project)
            for t in tasks:
                data = extract_play_names(task=t, parent=p, project=project)
                play_without_tasks = data["play"]
                if play_without_tasks and play_without_tasks in uniq_plays:
                    continue
                lines.append(json.dumps(data) + "\n")

        for tf in taskfiles:
            tasks = get_tasks(root=tf, project=project)
            for t in tasks:
                data = extract_play_names(task=t, parent=tf, project=project)
                play_without_tasks = data["play"]
                if play_without_tasks and play_without_tasks in uniq_plays:
                    continue
                lines.append(json.dumps(data) + "\n")

    output_path = args.output
    if output_path:
        with open(output_path, "w") as file:
            file.write("".join(lines))    


if __name__ == "__main__":
    main()