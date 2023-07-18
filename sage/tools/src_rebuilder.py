import argparse
import json
import glob
import jsonpickle
import os
from dataclasses import dataclass, field


def prepare_source_dir(root_dir, type, yaml_file):
    path_list = []
    if not os.path.exists(root_dir):
        os.makedirs(root_dir)

    yaml_file_contents = load_json_data(yaml_file)
    for content in yaml_file_contents:
        if "namespace_name" in content:
            type = "collection_role"
        else:
            type = "project"

        if type == "project":
            repo_name = content.get("repo_name")
            path = content.get("path")
            text = content.get("content")
            license = content.get("license")
            target_dir = os.path.join(root_dir, repo_name)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            target_file = os.path.join(target_dir, path.lstrip("/"))
            print(f"exporting yaml file {target_file}")
            target_file_dir = extract_directory(target_file)
            try:
                if not os.path.exists(target_file_dir):
                    os.makedirs(target_file_dir)
                with open(target_file, "w") as file:
                    file.write(text)
                path_list.append({
                    "repo_type": type,
                    "repo_name": repo_name,
                    "source": "",
                    "license": license,
                    "path": path,
                })
            except Exception as e:
                print(e)
        if type == "collection_role":
            namespace_name = content.get("namespace_name")
            path = content.get("path")
            text = content.get("text")
            source = content.get("source")
            license = content.get("license")
            path_list.append({
                "repo_type": type,
                "repo_name": namespace_name,
                "source": source,
                "license": license,
                "path": path,
            })
            target_dir = os.path.join(root_dir, namespace_name)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            target_file = os.path.join(target_dir, path)
            target_file_dir = extract_directory(target_file)
            if not os.path.exists(target_file_dir):
                os.makedirs(target_file_dir)
            with open(target_file, "w") as file:
                # print(f"exporting yaml file {target_file}")
                file.write(text)
    return path_list

def extract_directory(file_path):
    directory = os.path.dirname(file_path)
    return directory

def load_json_data(filepath):
    with open(filepath, "r") as file:
        records = file.readlines()
    trains = []
    for record in records:
        train = json.loads(record)
        trains.append(train)
    return trains

def write_result(filepath, results):
    with open(filepath, "w") as file:
        if type(results) == list:
            for result in results:
                json_str = jsonpickle.encode(result, make_refs=False, unpicklable=False)
                file.write(f"{json_str}\n")
        else:
            json_str = jsonpickle.encode(results, make_refs=False, unpicklable=False)
            file.write(f"{json_str}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-f", "--file", help='source yaml file')
    parser.add_argument("-t", "--type", help='type of data source')
    parser.add_argument("-d", "--dir", help='tmp dir to recreate source dir')
    parser.add_argument("-o", "--out-file", help="output directory for the rule evaluation result")
    args = parser.parse_args()

    path_list = prepare_source_dir(args.dir, args.type, args.file)
    write_result(args.out_file, path_list)