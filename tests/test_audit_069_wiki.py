"""Audit 0.6.9 — wiki + safety regressions (group F-F).

Covers three confirmed bugs plus one cross-cutting robustness guard:

* BH-W2  node_to_wiki_path ignored dedup_stem collision-salting, so
         ``affected --as wiki`` could hand back the WRONG node's article.
* BH-W3  the controller route table matched handlers by substring, fabricating
         another controller's routes onto any name that was a superstring.
* BH-S3  wiki markdown was not escaped, so a regex-alternation route path with a
         literal ``|`` broke the routes.md table (dropped the File column).
* G06    None labels crashed / poisoned the sort in wiki generation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import networkx as nx
import networkx.readwrite.json_graph as nxjson
import pytest

from codebeacon.affected import affected_from_paths
from codebeacon.common.safety import safe_wiki_filename
from codebeacon.wiki import templates
from codebeacon.wiki.generator import generate_wiki, node_to_wiki_path


# ── shared helpers ────────────────────────────────────────────────────────────

def _unescaped_cells(row: str) -> list[str]:
    """Split a GFM table row into cells the way a renderer does: on pipes that
    are NOT backslash-escaped. ``\\|`` stays inside its cell."""
    parts = re.split(r"(?<!\\)\|", row)
    return parts[1:-1]  # drop the empty pieces before the first / after last `|`


# ── BH-W2: collision-salted article resolution ───────────────────────────────

def _collision_graph() -> nx.DiGraph:
    """Two DISTINCT class nodes sharing label 'PaymentService' in one project.

    Node A is inserted first → claims the unsalted stem; node B is salted.
    """
    G = nx.DiGraph()
    G.add_node(
        "api::PaymentServiceA", label="PaymentService", type="class",
        project="api", source_file="api/src/a/PaymentService.py",
        annotations=["@Service"], methods=["chargeA"],
    )
    G.add_node(
        "api::PaymentServiceB", label="PaymentService", type="class",
        project="api", source_file="api/src/b/PaymentService.py",
        annotations=["@Service"], methods=["chargeB"],
    )
    return G


class TestBHW2CollisionResolution:
    def test_node_to_wiki_path_points_at_the_salted_file_on_disk(self, tmp_path):
        G = _collision_graph()
        generate_wiki(G, {}, str(tmp_path))
        services = tmp_path / "wiki" / "api" / "services"

        pa = node_to_wiki_path(G, "api::PaymentServiceA")
        pb = node_to_wiki_path(G, "api::PaymentServiceB")

        # The two colliding nodes must resolve to two DIFFERENT files.
        assert pa != pb, "both nodes collapsed to one article — dedup ignored"
        # Both resolved paths exist on disk (writer/resolver agree).
        assert (tmp_path / "wiki" / pa).exists()
        assert (tmp_path / "wiki" / pb).exists()

        # And each path holds THAT node's content, not the other's.
        assert "chargeA" in (tmp_path / "wiki" / pa).read_text()
        body_b = (tmp_path / "wiki" / pb).read_text()
        assert "chargeB" in body_b and "chargeA" not in body_b
        # The salted node genuinely lands on a salted stem.
        assert "_h" in Path(pb).name
        # Sanity: it matches whatever the writer actually wrote.
        on_disk = {p.name for p in services.glob("*.md")}
        assert Path(pb).name in on_disk

    def test_affected_wiki_surfaces_the_right_article_for_the_salted_node(self, tmp_path):
        G = _collision_graph()
        bdir = tmp_path / ".codebeacon"
        bdir.mkdir()
        (bdir / "beacon.json").write_text(
            json.dumps(nxjson.node_link_data(G), ensure_ascii=False), encoding="utf-8"
        )
        generate_wiki(G, {}, str(bdir))

        # Change ONLY node B's source file.
        result = affected_from_paths(
            bdir, ["api/src/b/PaymentService.py"], include_wiki_paths=True,
        )
        assert result.seed_node_ids == ["api::PaymentServiceB"]
        # Must hand back node B's salted article, never node A's unsalted one.
        assert len(result.wiki_paths) == 1
        wp = result.wiki_paths[0]
        assert "_h" in wp, f"got node A's unsalted article for a node-B change: {wp}"
        assert "chargeB" in (bdir / "wiki" / wp).read_text()

    def test_single_node_still_uses_the_plain_unsalted_stem(self, tmp_path):
        """No collision → no salt; the happy path must be untouched."""
        G = nx.DiGraph()
        G.add_node("api::Solo", label="Solo", type="class", project="api",
                   source_file="api/src/Solo.py", annotations=["@Service"], methods=[])
        assert node_to_wiki_path(G, "api::Solo") == "api/services/Solo.md"


# ── BH-W3: controller route table exact-match ─────────────────────────────────

def _substring_controllers_graph() -> nx.DiGraph:
    """UserController ⊂ AdminUserController, each owning one route."""
    G = nx.DiGraph()
    G.add_node(
        "api::UserController.getUsers::route",
        label="UserController.getUsers [GET /users]", type="route", project="api",
        framework="fastapi", source_file="/p/api/src/UserController.py",
        method="GET", path="/users", tags=[],
    )
    G.add_node(
        "api::AdminUserController.listUsers::route",
        label="AdminUserController.listUsers [GET /admin/users]", type="route",
        project="api", framework="fastapi",
        source_file="/p/api/src/AdminUserController.py",
        method="GET", path="/admin/users", tags=[],
    )
    G.add_node("api::UserController", label="UserController", type="class",
               project="api", framework="fastapi",
               source_file="/p/api/src/UserController.py",
               annotations=[], methods=["getUsers"], dependencies=[])
    G.add_node("api::AdminUserController", label="AdminUserController", type="class",
               project="api", framework="fastapi",
               source_file="/p/api/src/AdminUserController.py",
               annotations=[], methods=["listUsers"], dependencies=[])
    return G


class TestBHW3ControllerRouteMatch:
    def test_superstring_controller_route_is_not_fabricated(self, tmp_path):
        G = _substring_controllers_graph()
        generate_wiki(G, {}, str(tmp_path), project_roots={"api": "/p/api"})
        ctrl = tmp_path / "wiki" / "api" / "controllers"

        user = (ctrl / "UserController.md").read_text()
        assert "handles **1 route(s)**" in user
        assert "/users" in user
        # The admin route must NOT leak onto the shorter-named controller.
        assert "/admin/users" not in user

        admin = (ctrl / "AdminUserController.md").read_text()
        assert "handles **1 route(s)**" in admin
        assert "/admin/users" in admin

    def test_exact_handler_class_still_matches_own_routes(self, tmp_path):
        """A controller with two of its OWN routes still lists both."""
        G = nx.DiGraph()
        for m, path in (("getUsers", "/users"), ("getUser", "/users/{id}")):
            G.add_node(
                f"api::UserController.{m}::route",
                label=f"UserController.{m} [GET {path}]", type="route",
                project="api", framework="fastapi",
                source_file="/p/api/src/UserController.py",
                method="GET", path=path, tags=[],
            )
        G.add_node("api::UserController", label="UserController", type="class",
                   project="api", framework="fastapi",
                   source_file="/p/api/src/UserController.py",
                   annotations=[], methods=["getUsers", "getUser"], dependencies=[])
        generate_wiki(G, {}, str(tmp_path), project_roots={"api": "/p/api"})
        user = (tmp_path / "wiki" / "api" / "controllers" / "UserController.md").read_text()
        assert "handles **2 route(s)**" in user

    def test_non_dot_handler_lists_own_routes(self, tmp_path):
        """Frameworks whose handler has no dot (Laravel array `[Ctrl::class, 'm']`
        → bare `UserController`; Laravel `Ctrl@method`) must still list a
        controller's OWN routes — stripping the ` [VERB path]` suffix only after
        splitting on `.` used to leave the whole label intact for non-dot handlers,
        so the route silently vanished from the article (BH-W3)."""
        G = nx.DiGraph()
        # Bare handler (Laravel array / invokable): route label = "UserController [GET /users]".
        G.add_node(
            "api::UserController::index::route",
            label="UserController [GET /users]", type="route", project="api",
            framework="laravel", source_file="/p/api/app/UserController.php",
            method="GET", path="/users", tags=[],
        )
        # Laravel `@`-form handler: "UserController@show [GET /users/{id}]".
        G.add_node(
            "api::UserController::show::route",
            label="UserController@show [GET /users/{id}]", type="route", project="api",
            framework="laravel", source_file="/p/api/app/UserController.php",
            method="GET", path="/users/{id}", tags=[],
        )
        # A superstring-named controller's route must NOT leak onto UserController.
        G.add_node(
            "api::AdminUserController::index::route",
            label="AdminUserController@index [GET /admin/users]", type="route",
            project="api", framework="laravel",
            source_file="/p/api/app/AdminUserController.php",
            method="GET", path="/admin/users", tags=[],
        )
        G.add_node("api::UserController", label="UserController", type="class",
                   project="api", framework="laravel",
                   source_file="/p/api/app/UserController.php",
                   annotations=[], methods=["index", "show"], dependencies=[])
        G.add_node("api::AdminUserController", label="AdminUserController",
                   type="class", project="api", framework="laravel",
                   source_file="/p/api/app/AdminUserController.php",
                   annotations=[], methods=["index"], dependencies=[])
        generate_wiki(G, {}, str(tmp_path), project_roots={"api": "/p/api"})
        ctrl = tmp_path / "wiki" / "api" / "controllers"

        user = (ctrl / "UserController.md").read_text()
        # Both bare-handler and @-handler routes of UserController are listed.
        assert "handles **2 route(s)**" in user
        assert "/users" in user and "/users/{id}" in user
        # The superstring controller's route must NOT be fabricated here.
        assert "/admin/users" not in user

        admin = (ctrl / "AdminUserController.md").read_text()
        assert "handles **1 route(s)**" in admin
        assert "/admin/users" in admin


# ── BH-S3: markdown escaping ──────────────────────────────────────────────────

_PIPE_PATH = "/user/{id:[0-9]+|new}"  # Spring regex path variable with alternation


class TestBHS3MarkdownEscaping:
    def test_md_cell_escapes_pipe_only(self):
        assert templates._md_cell(_PIPE_PATH) == "/user/{id:[0-9]+\\|new}"
        # It must NOT escape `]` (harmful inside a code span) nor touch a clean path.
        assert templates._md_cell("/a]b") == "/a]b"
        assert templates._md_cell("/health") == "/health"

    def test_md_link_text_escapes_brackets(self):
        assert templates._md_link_text("page [GET /signup]") == "page \\[GET /signup\\]"
        assert templates._md_link_text("NormalService") == "NormalService"

    def test_routes_summary_row_keeps_four_cells_with_pipe_path(self):
        routes = {
            "api": [
                {"method": "GET", "path": _PIPE_PATH,
                 "handler": f"getUser [GET {_PIPE_PATH}]",
                 "source_file": "src/UserController.java", "framework": "spring"},
            ]
        }
        md = templates.routes_summary(routes)
        data_rows = [ln for ln in md.splitlines() if ln.startswith("| `")]
        assert len(data_rows) == 1
        row = data_rows[0]
        # A literal (unescaped) pipe would open a phantom column and drop File.
        cells = _unescaped_cells(row)
        assert len(cells) == 4, f"row broke into {len(cells)} cells: {row!r}"
        # The File column (last cell) survives intact.
        assert "src/UserController.java" in cells[3]
        # The path is present, escaped.
        assert "\\|" in row and "getUser" in row

    def test_rel_link_with_bracket_label_stays_a_valid_link(self):
        link = templates._rel_link("Foo]Bar", "api")
        # Display text escaped; target still uses safe_wiki_filename.
        assert link == "[Foo\\]Bar](./Foo_Bar.md)"

    def test_generate_wiki_routes_md_pipe_row_is_well_formed(self, tmp_path):
        G = nx.DiGraph()
        G.add_node("api::getUser", type="route", project="api", framework="spring",
                   method="GET", path=_PIPE_PATH,
                   label=f"getUser [GET {_PIPE_PATH}]",
                   source_file="src/UserController.java", tags=[])
        generate_wiki(G, {}, str(tmp_path))
        content = (tmp_path / "wiki" / "routes.md").read_text()
        row = next(ln for ln in content.splitlines()
                   if ln.startswith("| `") and "getUser" in ln)
        assert len(_unescaped_cells(row)) == 4
        assert "src/UserController.java" in row

    def test_routes_md_renders_to_four_columns_with_reference_gfm(self, tmp_path):
        """Stronger assertion against the reference renderer, when available."""
        cmarkgfm = pytest.importorskip("cmarkgfm")
        routes = {
            "api": [
                {"method": "GET", "path": _PIPE_PATH,
                 "handler": f"getUser [GET {_PIPE_PATH}]",
                 "source_file": "src/UserController.java", "framework": "spring"},
            ]
        }
        md = templates.routes_summary(routes)
        html = cmarkgfm.markdown_to_html_with_extensions(md, extensions=["table"])
        # Exactly one data row, 4 <td> cells, File column preserved.
        body = html.split("<tbody>")[1]
        assert body.count("<td>") == 4
        assert "src/UserController.java" in body
        # The alternation pipe survived inside the code span (no split).
        assert "/user/{id:[0-9]+|new}" in body


# ── G06: None-label robustness ────────────────────────────────────────────────

class TestG06NoneLabelRobustness:
    def test_safe_wiki_filename_none_is_unnamed(self):
        assert safe_wiki_filename(None) == "unnamed"

    def test_generate_wiki_does_not_crash_on_none_caller_label(self, tmp_path):
        """A predecessor with label=None used to poison sorted(called_by).

        Uses a route caller (routes get no article of their own) so the test
        isolates the neighbor-label coercion, not article generation.
        """
        G = nx.DiGraph()
        G.add_node("api::Svc", label="Svc", type="class", project="api",
                   source_file="api/src/Svc.py", annotations=["@Service"], methods=["do"])
        # Two route handlers call the service; ONE has label=None. With a valid
        # caller alongside it, sorted(called_by) mixes str and None and raises
        # unless the None is coerced — isolating the neighbor-helper fix.
        G.add_node("api::route1", label=None, type="route", project="api",
                   method="GET", path="/x", source_file="api/src/Svc.py", tags=[])
        G.add_node("api::route2", label="listThings [GET /y]", type="route",
                   project="api", method="GET", path="/y",
                   source_file="api/src/Svc.py", tags=[])
        G.add_edge("api::route1", "api::Svc", relation="calls")
        G.add_edge("api::route2", "api::Svc", relation="calls")

        # Must not raise (previously: TypeError comparing str and NoneType when
        # sorting called_by, and AttributeError formatting the None route cell).
        generate_wiki(G, {}, str(tmp_path))
        svc = (tmp_path / "wiki" / "api" / "services" / "Svc.md").read_text()
        # The None label was coerced to the node id, not dropped as None.
        assert "## Called By" in svc
        assert "api::route1" in svc

    def test_none_label_on_article_owning_nodes_does_not_abort_export(self, tmp_path):
        """A class/entity/component node with label=None must yield an article
        named by its node id instead of crashing the whole export.

        Previously: a None class label hit ``_is_controller(None, …)`` (endswith
        AttributeError) and a None entity/component label poisoned ``sorted(names)``
        (str-vs-None TypeError) as soon as a real-labeled sibling was present. Only
        route nodes (which own no article) were hardened before this fix (G06)."""
        G = nx.DiGraph()
        # Real-labeled siblings so sorted() in project_index mixes str and None.
        G.add_node("api::RealSvc", label="RealSvc", type="class", project="api",
                   source_file="api/src/RealSvc.py", annotations=["@Service"], methods=["run"])
        G.add_node("api::RealEntity", label="RealEntity", type="entity", project="api",
                   source_file="api/src/RealEntity.py", table_name="t", fields=[], relations=[])
        G.add_node("api::RealComp", label="RealComp", type="component", project="api",
                   source_file="api/src/RealComp.tsx", props=[], hooks=[], imports=[])
        # One mis-shaped node of each article-owning type with label=None.
        G.add_node("api::NoneClass", label=None, type="class", project="api",
                   source_file="api/src/NoneClass.py", annotations=[], methods=["do"])
        G.add_node("api::NoneEntity", label=None, type="entity", project="api",
                   source_file="api/src/NoneEntity.py", table_name="", fields=[], relations=[])
        G.add_node("api::NoneComp", label=None, type="component", project="api",
                   source_file="api/src/NoneComp.tsx", props=[], hooks=[], imports=[])

        # Must complete — one mis-shaped node can't abort the whole export.
        generate_wiki(G, {}, str(tmp_path))

        # Each None-label node yields an article named by its coerced node id.
        assert (tmp_path / "wiki" / "api" / "services" / f"{safe_wiki_filename('api::NoneClass')}.md").exists()
        assert (tmp_path / "wiki" / "api" / "entities" / f"{safe_wiki_filename('api::NoneEntity')}.md").exists()
        assert (tmp_path / "wiki" / "api" / "components" / f"{safe_wiki_filename('api::NoneComp')}.md").exists()
        # And the healthy siblings survived (export not aborted partway).
        assert (tmp_path / "wiki" / "api" / "services" / "RealSvc.md").exists()
        assert (tmp_path / "wiki" / "api" / "entities" / "RealEntity.md").exists()
        assert (tmp_path / "wiki" / "api" / "components" / "RealComp.md").exists()
