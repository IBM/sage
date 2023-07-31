from dataclasses import dataclass, field
from typing import List
import logging
import jsonpickle
from sage.models import (
    SageObject,
    Module,
    Task,
    TaskFile,
    Role,
    Collection,
    Playbook,
    Play,
    Project,
)
from ansible_risk_insight.findings import Findings as ARIFindings
from ansible_risk_insight.keyutil import get_obj_type


logger = logging.getLogger(__name__)


def _init_objects_dict():
    return {
        "collections": [],
        "modules": [],
        "playbooks": [],
        "plays": [],
        "projects": [],
        "roles": [],
        "taskfiles": [],
        "tasks": [],
    }


@dataclass
class SageProject(object):
    source: dict = field(default_factory=dict)
    source_id: str = ""

    objects: dict = field(default_factory=_init_objects_dict)
    
    def add_object(self, obj: SageObject):
        obj_type = obj.type + "s"
        self.objects[obj_type].append(obj)
        return

    def get_object(self, key: str=""):
        if key:
            type_s = get_obj_type(key) + "s"
            objects_per_type = self.objects.get(type_s, [])
            for obj in objects_per_type:
                if obj.key == key:
                    return obj
        return None
    
    def playbook(self, **kwargs):
        for p in self.objects["playbooks"]:
            match_count = 0
            all_matched = False
            for key, val in kwargs.items():
                if hasattr(p, key):
                    actual = getattr(p, key, None)
                    expected = val
                    if type(actual) == type(expected) and actual == expected:
                        match_count += 1
            if match_count == len(kwargs):
                all_matched = True
            if all_matched:
                return p
        return None
    
    @property
    def playbooks(self):
        return self.objects["playbooks"]
    
    def role(self, **kwargs):
        for r in self.objects["roles"]:
            match_count = 0
            all_matched = False
            for key, val in kwargs.items():
                if hasattr(r, key):
                    actual = getattr(r, key, None)
                    expected = val
                    if type(actual) == type(expected) and actual == expected:
                        match_count += 1
            if match_count == len(kwargs):
                all_matched = True
            if all_matched:
                return r
        return None
    
    @property
    def roles(self):
        return self.objects["roles"]
    
    def taskfile(self, **kwargs):
        for tf in self.objects["taskfiles"]:
            match_count = 0
            all_matched = False
            for key, val in kwargs.items():
                if hasattr(tf, key):
                    actual = getattr(tf, key, None)
                    expected = val
                    if type(actual) == type(expected) and actual == expected:
                        match_count += 1
            if match_count == len(kwargs):
                all_matched = True
            if all_matched:
                return tf
        return None
    
    @property
    def taskfiles(self):
        return self.objects["taskfiles"]
    
    # NOTE: currently this returns only 1 sequence found first
    def get_call_sequence(self, target: Task):
        target_key = target.key
        found = None
        for p in self.playbooks():
            call_graph = self._get_call_graph(obj=p)
            all_keys = [obj.key for obj in call_graph]
            if target_key in all_keys:
                found = call_graph
                break
        if found:
            return found
        return None

    def _get_call_graph(self, obj: SageObject=None, key: str=""):
        if not obj and not key:
            raise ValueError("either `obj` or `key` must be non-empty value")
        
        if not obj and key:
            obj = self.get_object(key)
            if not obj:
                raise ValueError(f"No object found for key `{key}`")
            
        return self._recursive_get_call_graph(obj)


    def _get_children_keys_for_graph(self, obj):
        if isinstance(obj, Playbook):
            return obj.plays
        elif isinstance(obj, Role):
            return obj.taskfiles
        elif isinstance(obj, Play):
            roles = []
            if obj.roles_info:
                for ri in obj.roles_info:
                    role_key = ri.get("key", None)
                    if role_key:
                        roles.append(role_key)
            return obj.pre_tasks + obj.tasks + roles + obj.post_tasks
        elif isinstance(obj, TaskFile):
            return obj.tasks
        elif isinstance(obj, Task):
            if obj.include_info:
                c_key = obj.include_info.get("key", None)
                if c_key:
                    return [c_key]
        
        return []
        

    def _recursive_get_call_graph(self, obj):
        call_graph = [obj]
        children_keys = self._get_children_keys_for_graph(obj)
        if children_keys:
            for c_key in children_keys:
                c_obj = self.get_object(c_key)
                if not c_obj:
                    logger.warn(f"No object found for key `{c_key}`; skip this node")
                    continue
                sub_graph = self._recursive_get_call_graph(c_obj)
                call_graph.extend(sub_graph)
        return call_graph

@dataclass
class SageProjectList(object):
    items: List[SageProject]

    def filter(self, source_type: str="", repo_name: str=""):
        for p in self.items:
            if p.source.get("type", "") != source_type:
                continue
            if p.source.get("repo_name", "") != repo_name:
                continue
            return p
        return None


@dataclass
class SageObjects(object):
    _projects: SageProjectList = field(default_factory=list)

    def projects(self):
        return self._projects
    
    def projct(self, source_type: str="", repo_name: str=""):
        return self._projects.filter(source_type=source_type, repo_name=repo_name)


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
    obj = SageObjects(_projects=SageProjectList(items=proj_list))
    return obj

