import argparse
from typing import List
from dataclasses import dataclass, field

import jsonpickle
from sage_scan.models import load_objects
from sage_scan.models import Play, Task, File, PlaybookData, TaskFileData
import json
import os


@dataclass
class FileCont:
    obj_key: str = ""
    current_filepath: str = ""
    used_file: str = ""
    file_obj: File = field(default_factory=File)

    def resolve_file(self):
        return


# retrieve file obj from used_file path
def find_file_obj(fc_list: List[FileCont], objects):
    if not fc_list:
        return
    
    for i, fc in enumerate(fc_list):
        found = False
        for obj in objects:
            if not isinstance(obj, File):
                continue
            current_dir = os.path.dirname(fc.current_filepath)
            relative_path = os.path.relpath(obj.filepath, current_dir)
            norm_used_file = os.path.normpath(fc.used_file)
            if norm_used_file == relative_path:
                fc_list[i].file_obj = obj
                found = True
            if found:
                break
    return


# generate FileCont list from sage obj
def to_fc_list(obj):
    fc_list = []
    if isinstance(obj, Play):
        fc_list = get_fc_list_from_play(obj)
    elif isinstance(obj, Task):
        fc = get_fc_from_task(obj)
        fc_list = [fc]
    return fc_list


# return fc list from play obj
def get_fc_list_from_play(obj: Play):
    fc_list = []
    if obj.vars_files:
        for var_file in obj.vars_files:
            fc = FileCont()
            fc.obj_key = obj.key
            fc.current_filepath = obj.filepath
            fc.used_file = var_file
            fc_list.append(fc)
    return fc_list


# return fc from task obj
def get_fc_from_task(obj: Task):
    fc = None
    if obj.module.endswith("include_vars"):
        fc = FileCont()
        fc.obj_key = obj.key
        fc.current_filepath = obj.filepath
        mo = obj.module_options
        if isinstance(mo, str):
            fc.used_file = mo
        elif isinstance(mo, dict):
            if "file" in mo:
                fc.used_file = mo["file"]
            # TODO: support other args
    return fc


# return fc list with file obj
def resolve_file(obj, file_objects):
    fc_list = to_fc_list(obj)
    if not fc_list:
        return None
    find_file_obj(fc_list, file_objects)
    return fc_list


# return obj and fc list pairs in call_seq
def resolve_files_for_object_data(pd: PlaybookData|TaskFileData):
    call_seq = []
    file_objects = []
    if pd:
        call_seq = pd.call_seq
        file_objects = pd.project.files
    obj_fc_list_pairs = []
    for obj in call_seq:
        if not obj:
            continue
        fc_list = resolve_file(obj, file_objects)
        if not fc_list:
            continue
        obj_fc_list_pairs.append((obj, fc_list))
    return obj_fc_list_pairs


def main():
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--file", help="input sage object json file")
    parser.add_argument("-o", "--output", help="output json file")
    args = parser.parse_args()

    fpath = args.file

    sage_objects = load_objects(fpath)
    projects = sage_objects.projects()   

    results = []
    for project in projects:
        file_objs = project.files
        tasks = project.tasks
        for task in tasks:
            fc_list = resolve_file(task, file_objs)
            if fc_list:
                for fc in fc_list:
                    results.append(jsonpickle.encode(fc,make_refs=False) + "\n")

    with open(args.output, "w") as f:
        f.write("".join(results))

if __name__ == "__main__":
    main()
