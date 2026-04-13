"""Core data types for codebeacon. All dataclasses use slots=True for memory efficiency."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class Node:
    id: str
    label: str
    type: str            # "class", "method", "entity", "route", "component"
    source_file: str
    line: int
    metadata: dict       # framework-specific extras


@dataclass(slots=True)
class Edge:
    source: str
    target: str
    relation: str        # "imports", "calls", "injects", "calls_api", "shares_db_entity"
    confidence: str      # "EXTRACTED", "INFERRED", "UNRESOLVED"
    confidence_score: float
    source_file: str


@dataclass(slots=True)
class UnresolvedRef:
    source_node_id: str
    ref_type: str        # "autowired", "depends", "inject", "import"
    ref_name: str        # "AlertService", "get_db"
    framework: str


@dataclass(slots=True)
class LocalExtractResult:
    file_path: str
    nodes: list          # list[Node]
    unresolved: list     # list[UnresolvedRef]
    imports: list        # list[str] - raw import statements


@dataclass(slots=True)
class RouteInfo:
    method: str          # "GET", "POST", "PUT", "DELETE", "PATCH", "ANY"
    path: str            # "/api/users/{id}"
    handler: str         # "UserController.getUser"
    source_file: str
    line: int
    framework: str
    prefix: str = ""     # accumulated prefix from router.use() / Blueprint / etc.
    tags: list = field(default_factory=list)  # ["auth", "db", "cache"]


@dataclass(slots=True)
class ServiceInfo:
    name: str            # "UserService"
    class_name: str
    source_file: str
    line: int
    framework: str
    methods: list = field(default_factory=list)    # list[str] - method names
    dependencies: list = field(default_factory=list)  # list[str] - injected type names (unresolved)
    annotations: list = field(default_factory=list)   # list[str] - @Service, @Injectable, etc.


@dataclass(slots=True)
class EntityInfo:
    name: str            # "User"
    table_name: str      # "users" or "" if not explicit
    source_file: str
    line: int
    framework: str       # "jpa", "django-orm", "sqlalchemy", "eloquent", "ef-core", "gorm", "active-record", "diesel", "sea-orm"
    fields: list = field(default_factory=list)    # list[dict]: {"name", "type", "annotations"}
    relations: list = field(default_factory=list) # list[dict]: {"type": "hasMany", "target": "Order"}


@dataclass(slots=True)
class ComponentInfo:
    name: str            # "UserCard"
    source_file: str
    line: int
    framework: str       # "react", "vue", "svelte", "angular"
    props: list = field(default_factory=list)     # list[str] - prop names
    hooks: list = field(default_factory=list)     # list[str] - used hooks/composables
    imports: list = field(default_factory=list)   # list[str] - imported component names
    is_page: bool = False                          # true if this is a route-level page component
    route_path: str = ""                           # Next.js/Nuxt/SvelteKit derived route path


@dataclass(slots=True)
class ProjectInfo:
    name: str
    path: str
    framework: str       # detected framework
    language: str        # primary language
    signature_file: str  # the file that triggered detection (pom.xml, package.json, etc.)
    is_multi: bool = False
