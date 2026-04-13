"""Entity / ORM model extraction for all supported frameworks.

Public API:
    extract_entities(file_path, framework) -> list[EntityInfo]

Supported ORMs:
  JPA (@Entity), Django ORM (models.Model), SQLAlchemy/Pydantic,
  Eloquent, EF Core (DbSet<>), GORM (struct tags), Active Record,
  Diesel/SeaORM (#[derive]), Fluent (Vapor), Exposed (Ktor), TypeORM/Mongoose (NestJS).
"""
from __future__ import annotations

import re
from pathlib import Path

from codebeacon.common.types import EntityInfo
from codebeacon.extract.base import (
    extract_sfc_sections,
    load_query_file,
    node_text,
    parse_file,
    parse_sfc_script,
    run_query,
)


# ── Framework → query file stem ───────────────────────────────────────────────

_FW_TO_QUERY: dict[str, str] = {
    "spring-boot": "spring_boot",
    "express":     "express",
    "koa":         "express",
    "fastify":     "express",
    "nestjs":      "nestjs",
    "nextjs":      "react",
    "react":       "react",
    "fastapi":     "fastapi",
    "django":      "django",
    "flask":       "flask",
    "gin":         "gin",
    "echo":        "gin",
    "fiber":       "gin",
    "go":          "gin",
    "rails":       "rails",
    "laravel":     "laravel",
    "aspnet":      "aspnet",
    "actix":       "actix",
    "axum":        "actix",
    "rust":        "actix",
    "vapor":       "vapor",
    "ktor":        "ktor",
}

# GORM struct tag parser: `gorm:"column:name;primaryKey"`
_GORM_TAG_RE = re.compile(r'gorm:"([^"]*)"')
_GORM_KEY_RE = re.compile(r'(\w+)(?::(\w+))?')


# ── Public function ───────────────────────────────────────────────────────────

def extract_entities(file_path: str, framework: str) -> list[EntityInfo]:
    """Extract entity / ORM model definitions from *file_path*."""
    fw = framework.lower()
    query_name = _FW_TO_QUERY.get(fw)
    if not query_name:
        return []

    query_src = load_query_file(query_name)
    if not query_src:
        return []

    parsed = parse_file(file_path)
    if parsed is None:
        return []
    root, lang = parsed

    try:
        matches = run_query(lang, query_src, root)
    except Exception:
        return []

    _interpreters = {
        "spring_boot": _interpret_spring_boot,
        "express":     _interpret_noop,
        "nestjs":      _interpret_nestjs,
        "fastapi":     _interpret_python_orm,
        "django":      _interpret_django,
        "flask":       _interpret_python_orm,
        "gin":         _interpret_gorm,
        "rails":       _interpret_rails,
        "laravel":     _interpret_laravel,
        "aspnet":      _interpret_aspnet,
        "actix":       _interpret_rust,
        "vapor":       _interpret_vapor,
        "ktor":        _interpret_ktor,
        "react":       _interpret_noop,
    }

    interpreter = _interpreters.get(query_name, _interpret_noop)
    try:
        return interpreter(file_path, matches, fw)
    except Exception:
        return []


def _interpret_noop(file_path: str, matches: list, framework: str) -> list[EntityInfo]:
    return []


# ── Per-framework interpreters ────────────────────────────────────────────────

def _interpret_spring_boot(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """JPA @Entity with @Table(name=...), @Id, @Column, @ManyToOne etc."""
    entities: dict[int, EntityInfo] = {}  # class start_byte → EntityInfo
    class_ranges: dict[int, tuple[int, int]] = {}
    table_names: dict[int, str] = {}  # entity class start_byte → table name

    for _idx, caps in matches:
        # @Entity class
        if "entity.class" in caps and "entity.class_name" in caps:
            cls = caps["entity.class"][0]
            name = node_text(caps["entity.class_name"][0])
            key = cls.start_byte
            entities[key] = EntityInfo(
                name=name,
                table_name="",
                source_file=file_path,
                line=cls.start_point[0] + 1,
                framework="jpa",
            )
            class_ranges[key] = (cls.start_byte, cls.end_byte)

        # @Table(name="...") annotation
        if "entity.table_annotation" in caps and "entity.table_name" in caps:
            tbl_node = caps["entity.table_annotation"][0]
            table = node_text(caps["entity.table_name"][0]).strip('"\'')
            for key, (start, end) in class_ranges.items():
                if start <= tbl_node.start_byte <= end:
                    entities[key].table_name = table
                    break

        # Entity fields with JPA annotations
        if "entity.field" in caps and "entity.field_name" in caps:
            field_node = caps["entity.field"][0]
            field_name = node_text(caps["entity.field_name"][0])
            field_type = node_text(caps["entity.field_type"][0]) if "entity.field_type" in caps else ""
            ann = node_text(caps["entity.field_annotation"][0]) if "entity.field_annotation" in caps else ""

            for key, (start, end) in class_ranges.items():
                if start <= field_node.start_byte <= end:
                    field_info = {"name": field_name, "type": field_type, "annotations": [ann] if ann else []}
                    # Relations
                    if ann in ("ManyToOne", "OneToMany", "ManyToMany", "OneToOne"):
                        entities[key].relations.append({"type": ann, "target": field_type})
                    else:
                        entities[key].fields.append(field_info)
                    break

    return list(entities.values())


def _interpret_nestjs(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """NestJS: TypeORM @Entity() / Mongoose @Schema()."""
    entities: list[EntityInfo] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if "entity.class" in caps and "entity.class_name" in caps:
            name = node_text(caps["entity.class_name"][0])
            if name in seen:
                continue
            seen.add(name)
            node = caps["entity.class"][0]
            entities.append(EntityInfo(
                name=name,
                table_name="",
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="typeorm",
            ))

    return entities


def _interpret_python_orm(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """FastAPI/Flask: SQLAlchemy Base / Pydantic BaseModel."""
    entities: dict[int, EntityInfo] = {}
    class_ranges: dict[int, tuple[int, int]] = {}

    for _idx, caps in matches:
        for cls_key in ("entity.class", "entity.class_attr"):
            if cls_key in caps and "entity.class_name" in caps:
                cls = caps[cls_key][0]
                name = node_text(caps["entity.class_name"][0])
                key = cls.start_byte
                if key not in entities:
                    entities[key] = EntityInfo(
                        name=name,
                        table_name="",
                        source_file=file_path,
                        line=cls.start_point[0] + 1,
                        framework="sqlalchemy",
                    )
                    class_ranges[key] = (cls.start_byte, cls.end_byte)
                break

        # Fields: type-annotated assignments
        if "entity.with_fields" in caps and "entity.field_name" in caps:
            cls = caps["entity.with_fields"][0]
            for fn, ft in zip(
                caps.get("entity.field_name", []),
                caps.get("entity.field_type", []),
            ):
                field_name = node_text(fn)
                field_type = node_text(ft)
                for key, (start, end) in class_ranges.items():
                    if start <= cls.start_byte <= end:
                        entities[key].fields.append({
                            "name": field_name, "type": field_type, "annotations": [],
                        })
                        break

    return list(entities.values())


def _interpret_django(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """Django: models.Model subclass with CharField, ForeignKey, etc."""
    entities: list[EntityInfo] = []

    for _idx, caps in matches:
        if "entity.model" in caps and "entity.class_name" in caps:
            name = node_text(caps["entity.class_name"][0])
            node = caps["entity.model"][0]
            fields = []
            relations = []
            for fn, ft in zip(
                caps.get("entity.field_name", []),
                caps.get("entity.field_type", []),
            ):
                fname = node_text(fn)
                ftype = node_text(ft)
                if ftype in ("ForeignKey", "OneToOneField", "ManyToManyField"):
                    relations.append({"type": ftype, "target": fname})
                else:
                    fields.append({"name": fname, "type": ftype, "annotations": []})

            entities.append(EntityInfo(
                name=name,
                table_name="",
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="django-orm",
                fields=fields,
                relations=relations,
            ))

    return entities


def _interpret_gorm(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """Go: GORM struct with struct tags parsed via regex."""
    entities: dict[int, EntityInfo] = {}

    for _idx, caps in matches:
        # Struct with tagged fields
        if "entity.struct" in caps and "entity.struct_name" in caps:
            cls = caps["entity.struct"][0]
            name = node_text(caps["entity.struct_name"][0])
            key = cls.start_byte
            if key not in entities:
                entities[key] = EntityInfo(
                    name=name,
                    table_name="",
                    source_file=file_path,
                    line=cls.start_point[0] + 1,
                    framework="gorm",
                )
            # Parse fields + tags
            for fn, ft, tag_node in zip(
                caps.get("entity.field_name", []),
                caps.get("entity.field_type", []),
                caps.get("entity.field_tag", []),
            ):
                field_name = node_text(fn)
                field_type = node_text(ft)
                tag_raw = node_text(tag_node)
                annotations = _parse_gorm_tag(tag_raw)
                entities[key].fields.append({
                    "name": field_name, "type": field_type, "annotations": annotations,
                })

        # Struct without tags (bare struct)
        elif "entity.struct_bare" in caps and "entity.struct_name" in caps:
            cls = caps["entity.struct_bare"][0]
            name = node_text(caps["entity.struct_name"][0])
            key = cls.start_byte
            if key not in entities:
                entities[key] = EntityInfo(
                    name=name,
                    table_name="",
                    source_file=file_path,
                    line=cls.start_point[0] + 1,
                    framework="gorm",
                )

    return list(entities.values())


def _parse_gorm_tag(raw: str) -> list[str]:
    """Parse GORM struct tag like `gorm:"column:name;primaryKey"` into annotations."""
    m = _GORM_TAG_RE.search(raw)
    if not m:
        return []
    parts = m.group(1).split(";")
    annotations = []
    for part in parts:
        part = part.strip()
        if part:
            annotations.append(f"gorm:{part}")
    return annotations


def _interpret_rails(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """Rails: ApplicationRecord subclass + has_many/belongs_to associations."""
    entities: dict[int, EntityInfo] = {}
    class_ranges: dict[int, tuple[int, int]] = {}

    for _idx, caps in matches:
        if "entity.model" in caps and "entity.class_name" in caps:
            cls = caps["entity.model"][0]
            name = node_text(caps["entity.class_name"][0])
            key = cls.start_byte
            entities[key] = EntityInfo(
                name=name,
                table_name="",
                source_file=file_path,
                line=cls.start_point[0] + 1,
                framework="active-record",
            )
            class_ranges[key] = (cls.start_byte, cls.end_byte)

    for _idx, caps in matches:
        if "entity.association" in caps and "entity.relation_type" in caps:
            rel_node = caps["entity.association"][0]
            rel_type = node_text(caps["entity.relation_type"][0])
            target = node_text(caps["entity.relation_target"][0]).strip(":") if "entity.relation_target" in caps else ""
            for key, (start, end) in class_ranges.items():
                if start <= rel_node.start_byte <= end:
                    entities[key].relations.append({"type": rel_type, "target": target})
                    break

    return list(entities.values())


def _interpret_laravel(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """Laravel: Eloquent Model subclass + relation methods."""
    entities: dict[int, EntityInfo] = {}
    class_ranges: dict[int, tuple[int, int]] = {}

    for _idx, caps in matches:
        if "entity.model" in caps and "entity.class_name" in caps:
            cls = caps["entity.model"][0]
            name = node_text(caps["entity.class_name"][0])
            key = cls.start_byte
            entities[key] = EntityInfo(
                name=name,
                table_name="",
                source_file=file_path,
                line=cls.start_point[0] + 1,
                framework="eloquent",
            )
            class_ranges[key] = (cls.start_byte, cls.end_byte)

    for _idx, caps in matches:
        if "entity.relation" in caps and "entity.relation_type" in caps:
            rel_node = caps["entity.relation"][0]
            rel_type = node_text(caps["entity.relation_type"][0])
            target = node_text(caps["entity.relation_model"][0]) if "entity.relation_model" in caps else ""
            for key, (start, end) in class_ranges.items():
                if start <= rel_node.start_byte <= end:
                    entities[key].relations.append({"type": rel_type, "target": target})
                    break

    return list(entities.values())


def _interpret_aspnet(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """ASP.NET: EF Core DbSet<T> properties on DbContext."""
    entities: list[EntityInfo] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if "entity.dbset" in caps and "entity.class_name" in caps:
            name = node_text(caps["entity.class_name"][0])
            if name in seen:
                continue
            seen.add(name)
            dbset_name = node_text(caps["entity.dbset_name"][0]) if "entity.dbset_name" in caps else ""
            node = caps["entity.dbset"][0]
            entities.append(EntityInfo(
                name=name,
                table_name=dbset_name,
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="ef-core",
            ))

    return entities


def _interpret_rust(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """Rust: #[derive(Queryable/DeriveEntityModel)] structs + fields."""
    entities: dict[int, EntityInfo] = {}
    class_ranges: dict[int, tuple[int, int]] = {}

    for _idx, caps in matches:
        # Struct with derive macros
        if "entity.struct" in caps and "entity.struct_name" in caps:
            cls = caps["entity.struct"][0]
            name = node_text(caps["entity.struct_name"][0])
            traits = [node_text(n) for n in caps.get("entity.derive_trait", [])]
            key = cls.start_byte

            orm_type = "diesel"
            if any(t in ("DeriveEntityModel", "DeriveRelation") for t in traits):
                orm_type = "sea-orm"
            elif any(t in ("FromRow",) for t in traits):
                orm_type = "sqlx"

            entities[key] = EntityInfo(
                name=name,
                table_name="",
                source_file=file_path,
                line=cls.start_point[0] + 1,
                framework=orm_type,
            )
            class_ranges[key] = (cls.start_byte, cls.end_byte)

    for _idx, caps in matches:
        if "entity.struct_with_fields" in caps and "entity.field_name" in caps:
            cls = caps["entity.struct_with_fields"][0]
            for fn, ft in zip(
                caps.get("entity.field_name", []),
                caps.get("entity.field_type", []),
            ):
                fname = node_text(fn)
                ftype = node_text(ft)
                for key, (start, end) in class_ranges.items():
                    if start <= cls.start_byte <= end:
                        entities[key].fields.append({
                            "name": fname, "type": ftype, "annotations": [],
                        })
                        break

    return list(entities.values())


def _interpret_vapor(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """Vapor Fluent: Model class + @Field/@ID property wrappers."""
    entities: dict[int, EntityInfo] = {}
    class_ranges: dict[int, tuple[int, int]] = {}

    for _idx, caps in matches:
        if "entity.model" in caps and "entity.class_name" in caps:
            cls = caps["entity.model"][0]
            name = node_text(caps["entity.class_name"][0])
            key = cls.start_byte
            entities[key] = EntityInfo(
                name=name,
                table_name="",
                source_file=file_path,
                line=cls.start_point[0] + 1,
                framework="fluent",
            )
            class_ranges[key] = (cls.start_byte, cls.end_byte)

    for _idx, caps in matches:
        # @Field(key: "column") var fieldName
        if "entity.field" in caps and "entity.field_name" in caps:
            field_node = caps["entity.field"][0]
            fname = node_text(caps["entity.field_name"][0])
            col_key = node_text(caps["entity.field_key"][0]) if "entity.field_key" in caps else ""
            for key, (start, end) in class_ranges.items():
                if start <= field_node.start_byte <= end:
                    entities[key].fields.append({
                        "name": fname, "type": "", "annotations": [f"key:{col_key}"] if col_key else [],
                    })
                    break

        # @ID var id
        if "entity.id_field" in caps and "entity.id_name" in caps:
            field_node = caps["entity.id_field"][0]
            fname = node_text(caps["entity.id_name"][0])
            for key, (start, end) in class_ranges.items():
                if start <= field_node.start_byte <= end:
                    entities[key].fields.append({
                        "name": fname, "type": "", "annotations": ["@ID"],
                    })
                    break

    return list(entities.values())


def _interpret_ktor(
    file_path: str, matches: list, framework: str,
) -> list[EntityInfo]:
    """Ktor: Exposed Table objects + columns, data classes."""
    entities: list[EntityInfo] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        # Exposed Table object
        if "entity.table" in caps and "entity.table_name" in caps:
            name = node_text(caps["entity.table_name"][0])
            if name in seen:
                continue
            seen.add(name)
            node = caps["entity.table"][0]
            fields = []
            for cn, ct in zip(
                caps.get("entity.column_name", []),
                caps.get("entity.column_type", []),
            ):
                fields.append({
                    "name": node_text(cn), "type": node_text(ct), "annotations": [],
                })
            entities.append(EntityInfo(
                name=name,
                table_name=name.lower(),
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="exposed",
                fields=fields,
            ))

        # Kotlin data class
        if "entity.data_class" in caps and "entity.class_name" in caps:
            name = node_text(caps["entity.class_name"][0])
            if name in seen:
                continue
            seen.add(name)
            node = caps["entity.data_class"][0]
            entities.append(EntityInfo(
                name=name,
                table_name="",
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="kotlin-data",
            ))

    return entities
