"""Tests for common/symbols.py — SymbolTable and DI resolution."""
from __future__ import annotations

import pytest

from codebeacon.common.types import Edge, Node, UnresolvedRef
from codebeacon.common.symbols import SymbolTable


def _make_node(label: str, file_path: str = "src/Foo.java", implements=None, extends=None) -> Node:
    meta = {}
    if implements:
        meta["implements"] = implements
    if extends:
        meta["extends"] = extends
    return Node(
        id=f"{file_path}::{label}",
        label=label,
        type="class",
        source_file=file_path,
        line=1,
        metadata=meta,
    )


def _make_ref(source_class: str, ref_name: str, file_path: str = "src/Foo.java") -> UnresolvedRef:
    return UnresolvedRef(
        source_node_id=f"{file_path}::{source_class}",
        ref_type="autowired",
        ref_name=ref_name,
        framework="spring-boot",
    )


class TestSymbolTable:
    def test_build_registers_classes(self):
        st = SymbolTable()
        nodes = [_make_node("UserService"), _make_node("OrderService")]
        st.build(nodes)
        assert "UserService" in st.known_classes()
        assert "OrderService" in st.known_classes()

    def test_build_registers_node_ids(self):
        st = SymbolTable()
        nodes = [_make_node("Foo")]
        st.build(nodes)
        assert "src/Foo.java::Foo" in st.known_node_ids()

    def test_direct_class_resolution(self):
        """Ref to a known class name resolves to an EXTRACTED edge."""
        st = SymbolTable()
        st.build([_make_node("UserService"), _make_node("Caller")])
        ref = _make_ref("Caller", "UserService")
        edge = st.resolve_ref(ref)
        assert edge is not None
        assert edge.relation == "injects"
        assert edge.confidence == "EXTRACTED"
        assert edge.target == "UserService"

    def test_interface_impl_resolution(self):
        """Ref to an interface resolves to its impl with INFERRED confidence."""
        st = SymbolTable()
        # UserServiceImpl implements UserService
        impl_node = _make_node("UserServiceImpl", implements=["UserService"])
        st.build([impl_node, _make_node("Caller")])
        ref = _make_ref("Caller", "UserService")
        edge = st.resolve_ref(ref)
        assert edge is not None
        assert edge.target == "UserServiceImpl"
        assert edge.confidence == "INFERRED"
        assert edge.confidence_score < 1.0

    def test_prefers_impl_suffix(self):
        """When multiple impls exist, prefer the one ending in 'Impl'."""
        st = SymbolTable()
        nodes = [
            _make_node("AlertServiceImpl", implements=["AlertService"]),
            _make_node("DefaultAlertService", implements=["AlertService"]),
        ]
        st.build(nodes)
        ref = _make_ref("Caller", "AlertService")
        edge = st.resolve_ref(ref)
        assert edge is not None
        assert edge.target == "AlertServiceImpl"

    def test_unresolved_returns_none(self):
        """Ref to unknown class returns None."""
        st = SymbolTable()
        st.build([_make_node("Foo")])
        ref = _make_ref("Foo", "NonExistentService")
        assert st.resolve_ref(ref) is None

    def test_resolve_all(self):
        """resolve_all separates resolved from still-unresolved."""
        st = SymbolTable()
        st.build([_make_node("RealService")])
        refs = [
            _make_ref("Caller", "RealService"),
            _make_ref("Caller", "GhostService"),
        ]
        resolved, unresolved = st.resolve_all(refs)
        assert len(resolved) == 1
        assert len(unresolved) == 1
        assert resolved[0].target == "RealService"
        assert unresolved[0].ref_name == "GhostService"

    def test_empty_build(self):
        """Empty node list → no crashes."""
        st = SymbolTable()
        st.build([])
        assert st.known_classes() == set()
        edge = st.resolve_ref(_make_ref("Foo", "Bar"))
        assert edge is None

    def test_extends_also_registers(self):
        """extends relationship is treated same as implements for resolution."""
        st = SymbolTable()
        child = _make_node("ChildService", extends=["BaseService"])
        st.build([child])
        ref = _make_ref("Caller", "BaseService")
        edge = st.resolve_ref(ref)
        assert edge is not None
        assert edge.target == "ChildService"
