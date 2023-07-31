from dataclasses import dataclass, field
from typing import List
import logging
import json
from ansible_risk_insight.models import (
    Module as ARIModule,
    Task as ARITask,
    TaskFile as ARITaskFile,
    Role as ARIRole,
    Playbook as ARIPlaybook,
    Play as ARIPlay,
    Collection as ARICollection,
    Repository as ARIRepository,
    Annotation,
    BecomeInfo,
)
from ansible_risk_insight.findings import Findings as ARIFindings
from ansible_risk_insight.keyutil import get_obj_type


logger = logging.getLogger(__name__)


@dataclass
class SageObject(object):
    type: str = ""
    key: str = ""
    name: str = ""
    source: dict = field(default_factory=dict)
    source_id: str = ""
    annotations: List[Annotation] = field(default_factory=list)

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
    
    def set_source(self, source: dict={}):
        self.source = source
        if source:
            self.source_id = json.dumps(source)
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

    # embed this data when role is resolved
    roles_info: list = field(default_factory=list)


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
    version: str = ""


def convert_to_sage_obj(ari_obj):
    if isinstance(ari_obj, ARIModule):
        return Module.from_ari_obj(ari_obj)
    elif isinstance(ari_obj, ARITask):
        return Task.from_ari_obj(ari_obj)
    elif isinstance(ari_obj, ARITaskFile):
        return TaskFile.from_ari_obj(ari_obj)
    elif isinstance(ari_obj, ARIRole):
        return Role.from_ari_obj(ari_obj)
    elif isinstance(ari_obj, ARIPlaybook):
        return Playbook.from_ari_obj(ari_obj)
    elif isinstance(ari_obj, ARIPlay):
        return Play.from_ari_obj(ari_obj)
    elif isinstance(ari_obj, ARICollection):
        return Collection.from_ari_obj(ari_obj)
    elif isinstance(ari_obj, ARIRepository):
        return Project.from_ari_obj(ari_obj)
    else:
        raise ValueError(f"{type(ari_obj)} is not a supported type for Sage objects")