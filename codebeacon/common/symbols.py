"""Global symbol table for two-pass DI resolution (Pass 2).

SymbolTable:
  - Pass 1: receives all extracted nodes, builds class_name → file_path + implements/extends maps
  - Pass 2: resolves UnresolvedRef objects → concrete Edge objects

Resolution priority:
  1. Interface → Impl mapping (Spring Boot @Service/@Component implements chain)
  2. Direct class name match
  3. Unresolved → return None
"""

from __future__ import annotations

from typing import Optional

from codebeacon.common.types import Edge, Node, UnresolvedRef


class SymbolTable:
    """Manages global symbol mappings for cross-file dependency resolution."""

    def __init__(self) -> None:
        # class_name → [file_path, ...]  (multiple definitions possible in monorepo)
        self._class_map: dict[str, list[str]] = {}
        # interface_name → [impl_class_name, ...]
        self._implements_map: dict[str, list[str]] = {}
        # All known node IDs
        self._node_ids: set[str] = set()

    def build(self, nodes: list[Node]) -> None:
        """Build symbol maps from a flat list of all extracted nodes.

        Must be called after all Pass-1 extraction is complete.
        """
        for node in nodes:
            self._node_ids.add(node.id)

            label = node.label
            if label not in self._class_map:
                self._class_map[label] = []
            if node.source_file not in self._class_map[label]:
                self._class_map[label].append(node.source_file)

            # Register implements/extends relationships from metadata
            meta = node.metadata or {}
            for iface in meta.get("implements", []):
                self._implements_map.setdefault(iface, [])
                if label not in self._implements_map[iface]:
                    self._implements_map[iface].append(label)
            for parent in meta.get("extends", []):
                self._implements_map.setdefault(parent, [])
                if label not in self._implements_map[parent]:
                    self._implements_map[parent].append(label)

    def resolve_ref(self, ref: UnresolvedRef) -> Optional[Edge]:
        """Attempt to resolve a single UnresolvedRef into a concrete Edge.

        Returns None if resolution fails.
        """
        target_name = ref.ref_name

        # Step 1: Try interface → impl mapping (Spring Boot / Laravel / Angular pattern)
        impls = self._implements_map.get(target_name)
        if impls:
            chosen = impls[0]
            if len(impls) > 1:
                for impl in impls:
                    if impl.endswith("Impl") or impl.endswith("Implementation"):
                        chosen = impl
                        break
            target_name = chosen

        # Step 2: Direct class match
        if target_name not in self._class_map:
            return None

        source_file = (
            ref.source_node_id.split("::")[1]
            if "::" in ref.source_node_id
            else ref.source_node_id
        )

        is_interface_resolved = target_name != ref.ref_name
        return Edge(
            source=ref.source_node_id,
            target=target_name,
            relation="injects",
            confidence="INFERRED" if is_interface_resolved else "EXTRACTED",
            confidence_score=0.8 if is_interface_resolved else 1.0,
            source_file=source_file,
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
