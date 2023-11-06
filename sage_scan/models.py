# -*- mode:python; coding:utf-8 -*-

# Copyright (c) 2023 IBM Corp. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass, field
from typing import List, Dict
import logging
import json
import jsonpickle
from ansible_risk_insight.models import (
    Module as ARIModule,
    Task as ARITask,
    TaskFile as ARITaskFile,
    Role as ARIRole,
    Playbook as ARIPlaybook,
    Play as ARIPlay,
    Collection as ARICollection,
    File as ARIFile,
    Repository as ARIRepository,
    Annotation,
    BecomeInfo,
)
from ansible_risk_insight.findings import Findings as ARIFindings
from ansible_risk_insight.keyutil import get_obj_type, key_delimiter


logger = logging.getLogger(__name__)


@dataclass
class SageObject(object):
    type: str = ""
    key: str = ""
    name: str = ""
    source: dict = field(default_factory=dict)
    source_id: str = ""
    test_object: bool = False
    annotations: Dict[str, any] = field(default_factory=dict)

    @classmethod
    def from_ari_obj(cls, ari_obj, source: dict={}):
        sage_obj = cls()
        if not hasattr(ari_obj, "__dict__"):
            return sage_obj

        attr_mapping = {
            "defined_in": "filepath",
            "path": "filepath",
            "source": "ari_source",
        }
        for key, val in ari_obj.__dict__.items():
            attr_name = key
            if key in attr_mapping:
                attr_name = attr_mapping[key]
            
            if hasattr(sage_obj, attr_name):
                setattr(sage_obj, attr_name, val)

        type_mapping = {
            "repository": "project",
        }
        if sage_obj.type in type_mapping:
            sage_obj.type = type_mapping[sage_obj.type]

        sage_obj.set_source(source)
        return sage_obj
    
    @classmethod
    def to_ari_obj(cls, sage_obj):
        type_str = cls.__name__.lower()

        cls_mapping = {
            "module": ARIModule,
            "task": ARITask,
            "taskfile": ARITaskFile,
            "role": ARIRole,
            "playbook": ARIPlaybook,
            "play": ARIPlay,
            "collection": ARICollection,
            "file": ARIFile,
            "project": ARIRepository,
        }
        cls = cls_mapping.get(type_str, None)
        if not cls:
            return None
        
        ari_obj = cls()
        if not hasattr(sage_obj, "__dict__"):
            return ari_obj

        default_attr_mapping = {
            "filepath": "defined_in",
        }
        type_specific_attr_mapping = {
            "role": {
                "ari_source": "source",
            },
            "collection": {
                "filepath": "path",
            }
        }
        
        attr_mapping = default_attr_mapping.copy()
        if type_str:
            _attr_mapping = type_specific_attr_mapping.get(type_str, {})
            attr_mapping.update(_attr_mapping)

        for key, val in sage_obj.__dict__.items():
            attr_name = key
            if key in attr_mapping:
                attr_name = attr_mapping[key]
            
            if hasattr(ari_obj, attr_name):
                setattr(ari_obj, attr_name, val)

        type_mapping = {
            "project": "repository",
        }
        if ari_obj.type in type_mapping:
            ari_obj.type = type_mapping[ari_obj.type]

        return ari_obj
    
    def set_source(self, source: dict={}):
        self.source = source
        if source:
            self.source_id = json.dumps(source, separators=(',', ':'))
        return
    
    def set_annotation(self, key: str, value: any):
        self.annotations[key] = value
        return

    def get_annotation(self, key: str, __default: any = None):
        return self.annotations.get(key, __default)
    
    def delete_annotation(self, key: str):
        if key in self.annotations:
            self.annotations.pop(key)
        return


@dataclass
class Module(SageObject):
    type: str = "module"
    key: str = ""
    name: str = ""
    fqcn: str = ""
    collection: str = ""
    role: str = ""
    documentation: str = ""
    examples: str = ""
    arguments: list = field(default_factory=list)
    filepath: str = ""
    builtin: bool = False


@dataclass
class Task(SageObject):
    type: str = "task"
    key: str = ""
    name: str = ""
    
    module: str = ""
    index: int = -1
    play_index: int = -1
    filepath: str = ""
    
    role: str = ""
    collection: str = ""
    become: BecomeInfo = None
    variables: dict = field(default_factory=dict)
    module_defaults: dict = field(default_factory=dict)
    registered_variables: dict = field(default_factory=dict)
    set_facts: dict = field(default_factory=dict)
    loop: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    module_options: dict = field(default_factory=dict)
    executable: str = ""
    executable_type: str = ""
    collections_in_play: list = field(default_factory=list)

    yaml_lines: str = ""
    line_num_in_file: list = field(default_factory=list)  # [begin, end]

    # FQCN for Module and Role. Or a file path for TaskFile.  resolved later
    resolved_name: str = ""
    # candidates of resovled_name
    possible_candidates: list = field(default_factory=list)

    # embed these data when module/role/taskfile are resolved
    module_info: dict = field(default_factory=dict)
    include_info: dict = field(default_factory=dict)


@dataclass
class TaskFile(SageObject):
    type: str = "taskfile"
    key: str = ""
    name: str = ""
    filepath: str = ""
    tasks: list = field(default_factory=list)
    role: str = ""
    collection: str = ""
    yaml_lines: str = ""
    variables: dict = field(default_factory=dict)
    module_defaults: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    task_loading: dict = field(default_factory=dict)


@dataclass
class Role(SageObject):
    type: str = "role"
    key: str = ""
    name: str = ""
    filepath: str = ""
    fqcn: str = ""
    metadata: dict = field(default_factory=dict)
    collection: str = ""
    playbooks: list = field(default_factory=list)
    taskfiles: list = field(default_factory=list)
    handlers: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    dependency: dict = field(default_factory=dict)
    requirements: dict = field(default_factory=dict)
    ari_source: str = ""  # collection/scm repo/galaxy

    default_variables: dict = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    # key: loop_var (default "item"), value: list/dict of item value
    loop: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)


@dataclass
class Playbook(SageObject):
    type: str = "playbook"
    key: str = ""
    name: str = ""
    filepath: str = ""
    yaml_lines: str = ""
    role: str = ""
    collection: str = ""
    plays: list = field(default_factory=list)
    variables: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)


@dataclass
class Play(SageObject):
    type: str = "play"
    key: str = ""
    name: str = ""
    filepath: str = ""
    index: int = -1
    role: str = ""
    collection: str = ""
    import_module: str = ""
    import_playbook: str = ""
    pre_tasks: list = field(default_factory=list)
    tasks: list = field(default_factory=list)
    post_tasks: list = field(default_factory=list)
    # not actual Role, but RoleInPlay defined in this playbook
    roles: list = field(default_factory=list)
    module_defaults: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    collections_in_play: list = field(default_factory=list)
    become: BecomeInfo = None
    variables: dict = field(default_factory=dict)
    vars_files: list = field(default_factory=list)

    task_loading: dict = field(default_factory=dict)


@dataclass
class Collection(SageObject):
    type: str = "collection"
    name: str = ""
    key: str = ""
    filepath: str = ""
    metadata: dict = field(default_factory=dict)
    meta_runtime: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)
    playbooks: list = field(default_factory=list)
    taskfiles: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    dependency: dict = field(default_factory=dict)
    requirements: dict = field(default_factory=dict)
    variables: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)


@dataclass
class File(SageObject):
    type: str = "file"
    key: str = ""
    name: str = ""
    role: str = ""
    collection: str = ""
    body: str = ""
    data: any = None
    error: str = ""
    label: str = ""
    filepath: str = ""


@dataclass
class Project(SageObject):
    type: str = "project"
    key: str = ""
    name: str = ""
    filepath: str = ""
    # if set, this repository is a collection repository
    my_collection_name: str = ""
    playbooks: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    # for playbook scan
    target_playbook_path: str = ""
    # for taskfile scan
    target_taskfile_path: str = ""
    requirements: dict = field(default_factory=dict)
    installed_collections_path: str = ""
    installed_collections: list = field(default_factory=list)
    installed_roles_path: str = ""
    installed_roles: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    taskfiles: list = field(default_factory=list)
    inventories: list = field(default_factory=list)
    files: list = field(default_factory=list)
    version: str = ""

    @classmethod
    def from_ari_obj(cls, ari_obj, source: dict={}):
        instance = super().from_ari_obj(ari_obj, source)
        instance.key = f"project {instance.source_id}"
        return instance


def convert_to_sage_obj(ari_obj, source: dict={}):
    if isinstance(ari_obj, ARIModule):
        return Module.from_ari_obj(ari_obj, source)
    elif isinstance(ari_obj, ARITask):
        return Task.from_ari_obj(ari_obj, source)
    elif isinstance(ari_obj, ARITaskFile):
        return TaskFile.from_ari_obj(ari_obj, source)
    elif isinstance(ari_obj, ARIRole):
        return Role.from_ari_obj(ari_obj, source)
    elif isinstance(ari_obj, ARIPlaybook):
        return Playbook.from_ari_obj(ari_obj, source)
    elif isinstance(ari_obj, ARIPlay):
        return Play.from_ari_obj(ari_obj, source)
    elif isinstance(ari_obj, ARICollection):
        return Collection.from_ari_obj(ari_obj, source)
    elif isinstance(ari_obj, ARIFile):
        return File.from_ari_obj(ari_obj, source)
    elif isinstance(ari_obj, ARIRepository):
        return Project.from_ari_obj(ari_obj, source)
    else:
        raise ValueError(f"{type(ari_obj)} is not a supported type for Sage objects")


def convert_to_ari_obj(sage_obj):
    if isinstance(sage_obj, Module):
        return Module.to_ari_obj(sage_obj)
    elif isinstance(sage_obj, Task):
        return Task.to_ari_obj(sage_obj)
    elif isinstance(sage_obj, TaskFile):
        return TaskFile.to_ari_obj(sage_obj)
    elif isinstance(sage_obj, Role):
        return Role.to_ari_obj(sage_obj)
    elif isinstance(sage_obj, Playbook):
        return Playbook.to_ari_obj(sage_obj)
    elif isinstance(sage_obj, Play):
        return Play.to_ari_obj(sage_obj)
    elif isinstance(sage_obj, Collection):
        return Collection.to_ari_obj(sage_obj)
    elif isinstance(sage_obj, File):
        return File.to_ari_obj(sage_obj)
    elif isinstance(sage_obj, Project):
        return Project.to_ari_obj(sage_obj)
    else:
        raise ValueError(f"{type(sage_obj)} is not a supported type for ARI objects")


attr_list = [
    "collections",
    "modules",
    "playbooks",
    "plays",
    "projects",
    "roles",
    "taskfiles",
    "tasks",
    "files",
]


@dataclass
class SageProject(object):
    source: dict = field(default_factory=dict)
    source_id: str = ""

    file_inventory: list = field(default_factory=list)

    collections: list = field(default_factory=list)
    modules: list = field(default_factory=list)
    playbooks: list = field(default_factory=list)
    plays: list = field(default_factory=list)
    projects: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    taskfiles: list = field(default_factory=list)
    tasks: list = field(default_factory=list)
    files: list = field(default_factory=list)

    path: str = ""
    scan_timestamp: str = ""
    scan_time_detail: list = field(default_factory=list)
    dir_size: int = 0
    pipeline_version: str = ""

    # only used for ARI RAM conversion
    ari_metadata: dict = field(default_factory=dict)
    dependencies: list = field(default_factory=list)

    @classmethod
    def from_source_objects(
        cls,
        source: dict,
        file_inventory: list,
        objects: list,
        metadata: dict,
        scan_time: list,
        dir_size: int,
        ari_metadata: dict={},
        dependencies: list=[],
        ):
        proj = cls()
        proj.source = source
        if source:
            proj.source_id = json.dumps(source, separators=(',', ':'))

        proj.file_inventory = file_inventory

        for obj in objects:
            proj.add_object(obj)

        proj.path = metadata.get("name", "")
        proj.scan_timestamp = metadata.get("scan_timestamp", "")
        proj.pipeline_version = metadata.get("pipeline_version", "")
        proj.scan_time_detail = scan_time
        proj.dir_size = dir_size

        proj.ari_metadata = ari_metadata
        proj.dependencies = dependencies
        return proj
    
    def add_object(self, obj: SageObject):
        obj_type = obj.type + "s"
        objects_per_type = getattr(self, obj_type, [])
        objects_per_type.append(obj)
        setattr(self, obj_type, objects_per_type)
        return

    def get_object(self, key: str=""):
        if key:
            obj_type = get_obj_type(key) + "s"
            objects_per_type = getattr(self, obj_type, [])
            for obj in objects_per_type:
                if obj.key == key:
                    return obj
        return None

    def get_all_call_sequences(self, follow_include: bool=True):
        found_taskfile_keys = set()
        all_call_sequences = []
        for p in self.playbooks:
            call_graph = self._get_call_graph(obj=p, follow_include=follow_include)
            call_seq = self.call_graph2sequence(call_graph)
            all_call_sequences.append(call_seq)
            tmp_taskfile_keys = set([obj.key for obj in call_seq if isinstance(obj, TaskFile)])
            found_taskfile_keys = found_taskfile_keys.union(tmp_taskfile_keys)
        for r in self.roles:
            call_graph = self._get_call_graph(obj=r, follow_include=follow_include)
            call_seq = self.call_graph2sequence(call_graph)
            all_call_sequences.append(call_seq)
            tmp_taskfile_keys = set([obj.key for obj in call_seq if isinstance(obj, TaskFile)])
            found_taskfile_keys = found_taskfile_keys.union(tmp_taskfile_keys)
        for tf in self.taskfiles:
            if tf.key in found_taskfile_keys:
                continue
            call_graph = self._get_call_graph(obj=tf, follow_include=follow_include)
            call_seq = self.call_graph2sequence(call_graph)
            all_call_sequences.append(call_seq)
        return all_call_sequences
    
    # NOTE: currently this returns only 1 sequence found first
    def get_call_sequence_for_task(self, task: Task, follow_include: bool=True):
        target_key = task.key
        all_call_seqs = self.get_all_call_sequences(follow_include=follow_include)
        found_seq = None
        for call_seq in all_call_seqs:
            keys_in_seq = [obj.key for obj in call_seq]
            if target_key in keys_in_seq:
                found_seq = call_seq
                break
        return found_seq
    
    def get_call_sequence_by_entrypoint(self, entrypoint: Playbook|Role|TaskFile, follow_include: bool=True):
        call_tree = self.get_call_tree_by_entrypoint(entrypoint=entrypoint, follow_include=follow_include)
        call_seq = self.call_graph2sequence(call_tree)
        return call_seq

    def get_call_tree_by_entrypoint(self, entrypoint: Playbook|Role|TaskFile, follow_include: bool=True):
        return self._get_call_graph(obj=entrypoint, follow_include=follow_include)
    
    def call_graph2sequence(self, call_graph: list=[]):
        if not call_graph:
            return []
        call_seq = [call_graph[0][0]]
        for (_, c_obj) in call_graph:
            call_seq.append(c_obj)
        return call_seq

    # get call graph which starts from the specified object (e.g. playbook -> play -> task)
    def _get_call_graph(self, obj: SageObject=None, key: str="", follow_include: bool=True):
        if not obj and not key:
            raise ValueError("either `obj` or `key` must be non-empty value")
        
        if not obj and key:
            obj = self.get_object(key)
            if not obj:
                raise ValueError(f"No object found for key `{key}`")
        
        history = []
        return self._recursive_get_call_graph(obj=obj, history=history, follow_include=follow_include)


    def _get_children_keys_for_graph(self, obj, follow_include: bool=True):
        if isinstance(obj, Playbook):
            return obj.plays
        elif isinstance(obj, Role):
            # TODO: support role invokation for non main.yml
            target_filenames = ["main.yml", "main.yaml"]
            def get_filename(tf_key):
                return tf_key.split(key_delimiter)[-1].split("/")[-1]
            taskfile_key = [
                tf_key
                for tf_key in obj.taskfiles if get_filename(tf_key) in target_filenames
            ]
            return taskfile_key
        elif isinstance(obj, Play):
            roles = []
            if follow_include:
                if obj.roles:
                    for rip in obj.roles:
                    
                        role_key = rip.role_info.get("key", None)
                        if role_key:
                            roles.append(role_key)
            return obj.pre_tasks + obj.tasks + roles + obj.post_tasks
        elif isinstance(obj, TaskFile):
            return obj.tasks
        elif isinstance(obj, Task):
            if follow_include:
                if obj.include_info:
                    c_key = obj.include_info.get("key", None)
                    if c_key:
                        return [c_key]
        
        return []
        
    def _recursive_get_call_graph(self, obj, history=None, follow_include: bool=True):
        if not history:
            history = []
        
        obj_key = obj.key
        if obj_key in history:
            return []
        
        _history = [h for h in history]
        _history.append(obj_key)

        call_graph = []
        children_keys = self._get_children_keys_for_graph(obj=obj, follow_include=follow_include)
        if children_keys:
            for c_key in children_keys:
                c_obj = self.get_object(c_key)
                if not c_obj:
                    logger.warn(f"No object found for key `{c_key}`; skip this node")
                    continue
                call_graph.append((obj, c_obj))
                sub_graph = self._recursive_get_call_graph(obj=c_obj, history=_history, follow_include=follow_include)
                if sub_graph:
                    call_graph.extend(sub_graph)
        return call_graph
    
    def object_to_key(self):
        
        new_proj = SageProject(
            source=self.source,
            source_id=self.source_id,
            file_inventory=self.file_inventory,
            path=self.path,
            scan_timestamp=self.scan_timestamp,
        )
        for attr in attr_list:
            objects = getattr(self, attr, [])
            keys = [obj.key for obj in objects]
            setattr(new_proj, attr, keys)
        return new_proj
    
    def metadata(self):
        objects = {}
        for attr in attr_list:
            objects_per_type = getattr(self, attr, [])
            if attr == "files":
                objects["files"] = len(self.file_inventory)
                objects["loaded_files"] = len(objects_per_type)
                objects["ignored_files"] = objects["files"] - objects["loaded_files"]
            else:
                objects[attr] = len(objects_per_type)
        return {
            "source": self.source,
            "source_id": self.source_id,
            "objects": objects,
            "path": self.path,
            "scan_timestamp": self.scan_timestamp,
            "scan_time_detail": self.scan_time_detail,
            "dir_size": self.dir_size,
            "pipeline_version": self.pipeline_version,
            "file_inventory": self.file_inventory,
            "ari_metadata": self.ari_metadata,
            "dependencies": self.dependencies,
        }
    
    def objects(self):
        _objects = []
        for attr in attr_list:
            objects_per_type = getattr(self, attr, [])
            _objects.extend(objects_per_type)
        return _objects


@dataclass
class SageObjects(object):
    _projects: List[SageProject] = field(default_factory=list)

    def projects(self):
        return self._projects
    
    def project(self, source_type: str="", repo_name: str=""):
        for proj in self.projects():
            p_source_type = proj.source.get("type", "")
            p_repo_name = proj.source.get("repo_name", "")
            if p_source_type == source_type and p_repo_name == repo_name:
                return proj
        return None


def load_objects(fpath: str) -> SageObjects:
    proj_dict = {}
    with open(fpath, "r") as file:
        for line in file:
            obj = jsonpickle.decode(line)
            if not isinstance(obj, SageObject):
                raise ValueError(f"expected type: SageObject, detected type: {type(obj)}")
            source = obj.source
            source_id = obj.source_id
            if source_id not in proj_dict:
                proj_dict[source_id] = SageProject(source=source, source_id=source_id)
            proj_dict[source_id].add_object(obj)
    
    proj_list = [c for c in proj_dict.values()]
    obj = SageObjects(_projects=proj_list)
    return obj


def save_objects(fpath: str, sage_objects: SageObjects):
    projects = sage_objects.projects()
    all_objects = []
    for project in projects:
        _objects = project.objects()
        all_objects.extend(_objects)
    lines = []
    for obj in all_objects:
        if not isinstance(obj, SageObject):
            raise ValueError(f"expected type: SageObject, detected type: {type(obj)}")
        line = jsonpickle.encode(obj, make_refs=False, separators=(',', ':')) + "\n"
        lines.append(line)
    with open(fpath, "w") as file:
        file.write("".join(lines))
    return


# inherit this class to define custom metrics
@dataclass
class DataMetrics(object):
    # sample metrics
    num_of_tasks: int = None
    num_of_plays: int = None


@dataclass
class PlaybookData(object):
    object: Playbook = None
    project: SageProject = None

    # attributes below are automatically set by __post_init__() 

    # parent if any
    collection: Collection = None
    role: Role = None

    # children / include targets
    playbooks: list = field(default_factory=list)
    plays: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    taskfiles: list = field(default_factory=list)
    tasks: list = field(default_factory=list)

    call_tree: list = field(default_factory=list)
    call_seq: list = field(default_factory=list)
    # initialize this with None to clarify whether it is already computed or not
    used_vars: dict = None
    follow_include_for_used_vars: bool = True

    metrics: DataMetrics = field(default_factory=DataMetrics)

    def __post_init__(self):
        if not self.object:
            return
        
        if not self.project:
            return
        
        if self.object.collection:
            for coll in self.project.collections:
                if coll.fqcn == self.object.collection:
                    self.collection = coll
                    break

        if self.object.role:
            for role in self.project.roles:
                if role.fqcn == self.object.role:
                    self.role = role
                    break

        call_tree = self.project.get_call_tree_by_entrypoint(self.object)
        self.call_tree = call_tree

        call_seq = self.project.call_graph2sequence(call_tree)
        self.call_seq = call_seq

        for obj in call_seq:
            if isinstance(obj, Playbook):
                self.playbooks.append(obj)
            elif isinstance(obj, Play):
                self.plays.append(obj)
            elif isinstance(obj, Role):
                self.roles.append(obj)
            elif isinstance(obj, TaskFile):
                self.taskfiles.append(obj)
            elif isinstance(obj, Task):
                self.tasks.append(obj)


    def metrics_to_json(self):
        data = {}
        data["source"] = self.project.source
        data["filepath"] = self.object.filepath
        for k, v in self.metrics.__dict__.items():
            data[k] = v
        return json.dumps(data, separators=(',', ':'))

    def compute_metrics(self, metrics_funcs: list=None):
        # if no func is passed, run sample funcs
        if metrics_funcs is None:
            metrics_funcs = [
                ("num_of_tasks", self.get_num_of_tasks),
                ("num_of_plays", self.get_num_of_plays),
            ]
        # run each funcs
        for _item in metrics_funcs:
            if len(_item) < 2:
                raise ValueError("`metrics_funcs` must be a list of (metrics_key, metrics_func, args)")
            elif len(_item) == 2:
                key = _item[0]
                func = _item[1]
                value = func()
                setattr(self.metrics, key, value)
            elif len(_item) > 2:
                key = _item[0]
                func = _item[1]
                args = _item[2]
                value = func(**args)
                setattr(self.metrics, key, value)
        return
    
    def get_num_of_tasks(self):
        return len(self.get_tasks_in_this_playbook())

    def get_tasks_in_this_playbook(self):
        return [t for t in self.tasks if t.filepath == self.object.filepath]

    def get_num_of_plays(self):
        return len(self.get_plays_in_this_playbook())

    def get_plays_in_this_playbook(self):
        return [p for p in self.plays if p.filepath == self.object.filepath]

@dataclass
class TaskFileData(object):
    object: TaskFile = None
    project: SageProject = None

    # attributes below are automatically set by __post_init__() 

    # parent if any
    collection: Collection = None
    role: Role = None

    # children / include targets
    roles: list = field(default_factory=list)
    taskfiles: list = field(default_factory=list)
    tasks: list = field(default_factory=list)

    call_tree: list = field(default_factory=list)
    call_seq: list = field(default_factory=list)
    # initialize this with None to clarify whether it is already computed or not
    used_vars: dict = None
    follow_include_for_used_vars: bool = True

    metrics: DataMetrics = field(default_factory=DataMetrics)

    def __post_init__(self):
        if not self.object:
            return
        
        if not self.project:
            return
        
        if self.object.collection:
            for coll in self.project.collections:
                if coll.fqcn == self.object.collection:
                    self.collection = coll
                    break

        if self.object.role:
            for role in self.project.roles:
                if role.fqcn == self.object.role:
                    self.role = role
                    break

        call_tree = self.project.get_call_tree_by_entrypoint(self.object)
        self.call_tree = call_tree

        call_seq = self.project.call_graph2sequence(call_tree)
        self.call_seq = call_seq

        for obj in call_seq:
            if isinstance(obj, Role):
                self.roles.append(obj)
            elif isinstance(obj, TaskFile):
                self.taskfiles.append(obj)
            elif isinstance(obj, Task):
                self.tasks.append(obj)


    def metrics_to_json(self):
        data = {}
        data["source"] = self.project.source
        data["filepath"] = self.object.filepath
        for k, v in self.metrics.__dict__.items():
            data[k] = v
        return json.dumps(data, separators=(',', ':'))

    def compute_metrics(self, metrics_funcs: list=None):
        # if no funcs are passed, run sample funcs below
        if metrics_funcs is None:
            metrics_funcs = [
                ("num_of_tasks", self.get_num_of_tasks),
                ("num_of_plays", self.get_num_of_plays),
            ]
        # run each funcs
        for _item in metrics_funcs:
            if len(_item) < 2:
                raise ValueError("`metrics_funcs` must be a list of (metrics_key, metrics_func, args)")
            elif len(_item) == 2:
                key = _item[0]
                func = _item[1]
                value = func()
                setattr(self.metrics, key, value)
            elif len(_item) > 2:
                key = _item[0]
                func = _item[1]
                args = _item[2]
                value = func(**args)
                setattr(self.metrics, key, value)
        return
    
    def get_num_of_tasks(self):
        return len(self.get_tasks_in_this_taskfile())

    def get_tasks_in_this_taskfile(self):
        return [t for t in self.tasks if t.filepath == self.object.filepath]
    
    def get_num_of_plays(self):
        return 0
