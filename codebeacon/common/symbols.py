"""Global symbol table for two-pass DI resolution (Pass 2).

SymbolTable:
  - Pass 1: receives all extracted nodes, builds class_name → node ids and
    implements/extends maps
  - Pass 2: resolves UnresolvedRef objects → concrete Edge objects

Resolution priority:
  1. Interface → Impl mapping (Spring Boot @Service/@Component implements chain)
  2. Direct class name match
  3. Unresolved → return None

Every candidate must clear an **evidence** check before it can be bound. A DI
reference carries nothing but a type name, so matching on the name alone wired a
Java service to a React component in another project at full confidence
(GI-2207), and made ``extends Exception`` mean "every error class implements
Exception" (G-0949-15). A candidate qualifies when it shares the referrer's
language family and either lives in the same project, is imported by it, or
sits under a shared-library marker. Nothing else binds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from codebeacon.common.filters import (
    families_compatible,
    is_generic_supertype,
    is_shared_lib,
)
from codebeacon.common.types import Edge, Node, UnresolvedRef

# Naming conventions that mark the canonical implementation of an interface.
_IMPL_SUFFIXES = ("Impl", "Implementation")


def _bare(node_id: str) -> str:
    """Plain declaration name from a node id (``proj::hint/Name`` → ``Name``)."""
    return node_id.rsplit("::", 1)[-1].rsplit("/", 1)[-1]


class SymbolTable:
    """Manages global symbol mappings for cross-file dependency resolution."""

    def __init__(self) -> None:
        # class_name → [node_id, ...]  (multiple definitions possible in monorepo)
        self._class_map: dict[str, list[str]] = {}
        # interface_name → [impl node_id, ...]
        self._implements_map: dict[str, list[str]] = {}
        # All known node IDs
        self._node_ids: set[str] = set()
        # node_id → source_file, so resolved edges carry a real file path
        self._node_files: dict[str, str] = {}
        # node_id → project name / source extension, for the evidence check
        self._node_projects: dict[str, str] = {}
        self._node_exts: dict[str, str] = {}
        # (source node id, target node id) pairs backed by a real import edge
        self._import_pairs: set[tuple[str, str]] = set()
        self._project_roots: dict[str, str] = {}

    def build(
        self,
        nodes: list[Node],
        import_edges: Optional[Iterable[Edge]] = None,
        project_roots: Optional[dict[str, str]] = None,
    ) -> None:
        """Build symbol maps from a flat list of all extracted nodes.

        Must be called after all Pass-1 extraction is complete.

        ``import_edges`` (already remapped onto node ids) and ``project_roots``
        are optional evidence inputs: they let a cross-project reference bind
        when the referrer genuinely imports the target or the target is a shared
        library. Without them the resolver simply stays inside each project.
        """
        self._project_roots = dict(project_roots or {})
        for edge in import_edges or ():
            if edge.relation in ("imports", "imports_from", "re_exports"):
                self._import_pairs.add((edge.source, edge.target))

        for node in nodes:
            self._node_ids.add(node.id)
            self._node_files[node.id] = node.source_file or ""
            self._node_exts[node.id] = (
                Path(node.source_file).suffix.lower() if node.source_file else ""
            )
            meta = node.metadata or {}
            self._node_projects[node.id] = (
                meta.get("project") or node.id.split("::")[0]
            )

            # Index the declaration under its label AND its plain name: a node
            # disambiguated by ``_disambiguate_decl`` wears a decorated label
            # ("User (admin)") that no dependency declaration will ever spell.
            for key in (node.label, _bare(node.id)):
                if not key:
                    continue
                bucket = self._class_map.setdefault(key, [])
                if node.id not in bucket:
                    bucket.append(node.id)

            # Register implements/extends relationships from metadata, minus the
            # generic bases every language shares — inverting those turns one
            # arbitrary subclass into the resolution target for a bare
            # ``Exception``/``Model``/``Controller`` reference.
            ext = self._node_exts[node.id]
            for parent in list(meta.get("implements", [])) + list(meta.get("extends", [])):
                if not parent or is_generic_supertype(parent, ext):
                    continue
                bucket = self._implements_map.setdefault(parent, [])
                if node.id not in bucket:
                    bucket.append(node.id)

        # Sort every candidate list: the input order tracks wave completion, so
        # an unsorted list makes the chosen target flip run to run.
        for mapping in (self._class_map, self._implements_map):
            for key, ids in mapping.items():
                mapping[key] = sorted(ids)

    # ── evidence ──────────────────────────────────────────────────────────────

    def _qualifies(self, source_id: str, candidate_id: str) -> bool:
        """True when ``candidate_id`` may be bound to a ref made from ``source_id``."""
        if not families_compatible(
            self._node_exts.get(source_id, ""), self._node_exts.get(candidate_id, "")
        ):
            return False
        src_project = self._node_projects.get(source_id, "")
        tgt_project = self._node_projects.get(candidate_id, "")
        if not src_project or not tgt_project or src_project == tgt_project:
            return True
        if (source_id, candidate_id) in self._import_pairs:
            return True
        return is_shared_lib(
            self._node_files.get(candidate_id, ""),
            self._project_roots.get(tgt_project),
        )

    def _same_project(self, source_id: str, candidate_id: str) -> bool:
        src = self._node_projects.get(source_id, "")
        return bool(src) and src == self._node_projects.get(candidate_id, "")

    def _eligible(self, source_id: str, candidate_ids: Iterable[str]) -> list[str]:
        return [
            cid for cid in candidate_ids
            if cid != source_id and self._qualifies(source_id, cid)
        ]

    # ── resolution ────────────────────────────────────────────────────────────

    def resolve_ref(self, ref: UnresolvedRef) -> Optional[Edge]:
        """Attempt to resolve a single UnresolvedRef into a concrete Edge.

        Returns None if resolution fails.
        """
        source_id = ref.source_node_id
        target_id: Optional[str] = None
        confidence = "EXTRACTED"
        score = 1.0

        # Step 1: interface → impl (Spring Boot / Laravel / Angular pattern).
        # Only a SINGLE surviving implementation may be bound automatically:
        # with several, picking one is a guess that flipped between runs purely
        # on node order (G-0949-15 / R7d).
        impls = self._eligible(source_id, self._implements_map.get(ref.ref_name, []))
        if len(impls) == 1:
            target_id = impls[0]
            confidence, score = "INFERRED", 0.8
        elif len(impls) > 1:
            conventional = [i for i in impls if _bare(i).endswith(_IMPL_SUFFIXES)]
            if len(conventional) == 1:
                # The language's own naming convention names the canonical
                # implementation; bind it, but say plainly that the runtime
                # target was ambiguous.
                target_id = conventional[0]
                confidence, score = "AMBIGUOUS", 0.5
            # Otherwise leave the interface unsubstituted and fall through: a
            # direct match on the interface itself is honest, a coin flip
            # between implementations is not.

        # Step 2: direct class match.
        if target_id is None:
            candidates = self._eligible(source_id, self._class_map.get(ref.ref_name, []))
            if not candidates:
                return None
            same_project = [c for c in candidates if self._same_project(source_id, c)]
            if same_project:
                target_id = same_project[0]
            else:
                # A cross-project bind cleared the evidence check, but it is
                # still weaker than one inside the service: tier it down.
                target_id = candidates[0]
                confidence, score = "INFERRED", 0.7

        if target_id == source_id:
            return None

        return Edge(
            source=source_id,
            target=target_id,
            relation="injects",
            confidence=confidence,
            confidence_score=score,
            # The source node's actual file — Edge.source_file is a file path
            # everywhere else; stamping the node ID here leaked "proj::Name"
            # strings into beacon.json's source_file fields.
            source_file=self._node_files.get(source_id, ""),
        )

    def resolve_all(
        self, unresolved: list[UnresolvedRef]
    ) -> tuple[list[Edge], list[UnresolvedRef]]:
        """Resolve all UnresolvedRefs.

        Returns:
            (resolved_edges, still_unresolved) tuple.
        """
        resolved: list[Edge] = []
        still_unresolved: list[UnresolvedRef] = []
        for ref in unresolved:
            edge = self.resolve_ref(ref)
            if edge is not None:
                resolved.append(edge)
            else:
                still_unresolved.append(ref)
        return resolved, still_unresolved

    def known_classes(self) -> set[str]:
        """Return the set of all known class/type names."""
        return set(self._class_map.keys())

    def known_node_ids(self) -> set[str]:
        """Return all registered node IDs."""
        return set(self._node_ids)
