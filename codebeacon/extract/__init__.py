"""Extraction layer: AST-based analysis of source files.

Public API:
    extract_routes(file_path, framework, project_path="") -> list[RouteInfo]
    extract_services(file_path, framework) -> tuple[list[ServiceInfo], list[UnresolvedRef]]
    extract_entities(file_path, framework) -> list[EntityInfo]
    extract_components(file_path, framework, project_path="") -> list[ComponentInfo]
    extract_dependencies(file_path, framework) -> list[Edge]
"""
from codebeacon.extract.routes import extract_routes
from codebeacon.extract.services import extract_services
from codebeacon.extract.entities import extract_entities
from codebeacon.extract.components import extract_components
from codebeacon.extract.dependencies import extract_dependencies

__all__ = [
    "extract_routes",
    "extract_services",
    "extract_entities",
    "extract_components",
    "extract_dependencies",
]
