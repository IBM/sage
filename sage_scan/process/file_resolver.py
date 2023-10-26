import argparse
from dataclasses import dataclass, field

import jsonpickle
from sage_scan.models import load_objects
from sage_scan.models import Task, File
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
def find_file_obj(fc: FileCont, objects):
    for obj in objects:
        if not isinstance(obj, File):
            continue
        current_dir = os.path.dirname(fc.current_filepath)
        relative_path = os.path.relpath(obj.filepath, current_dir)
        norm_used_file = os.path.normpath(fc.used_file)
        if norm_used_file == relative_path:
            return obj
    return None


# generate FileCont from sage obj
def to_fc(obj):
    fc = None
    # TODO: support play vars file
    # if isinstance(obj, Play):
    if isinstance(obj, Task):
        fc = get_fc_from_task(obj)
    return fc


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


# return fc with file obj
def resolve_file(obj, file_objects):
    fc = to_fc(obj)
    if fc is None:
        return None
    found_obj = find_file_obj(fc, file_objects)
    fc.file_obj = found_obj
    return fc


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
            fc = resolve_file(task, file_objs)
            if fc:
                results.append(jsonpickle.encode(fc,make_refs=False) + "\n")

    with open(args.output, "w") as f:
        f.write("".join(results))

if __name__ == "__main__":
    main()
