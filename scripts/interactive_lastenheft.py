#!/usr/bin/env python3
"""
interactive_lastenheft.py — TUI Requirement Tree Browser

Keys:
  j/↓        next same-parent sibling (fallback: advance-by-1)
  k/↑        prev same-parent sibling (fallback: decrease-by-1)
  h/←        jump to parent; on root+expanded → collapse
  l/→        if collapsed: expand+move to first child; if expanded: move to first child
  space      toggle expand/collapse
  enter      show detail panel
  t          show DTC test cases for current node
  r          reload reqs.yaml
  e          edit current requirement in $EDITOR
  d          delete current requirement (with confirmation)
  D          delete all inactive requirements (with confirmation)
  q          quit
"""

import curses
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REQS_PATH = Path(__file__).parent.parent / "reqs.yaml"

# ── Colors (pair numbers) ──────────────────────────────────────────────────────
COLOR_TITLE     = 1
COLOR_URS       = 2
COLOR_SRS       = 3
COLOR_DDS       = 4
COLOR_DTC       = 5
COLOR_SCRIPT    = 6
COLOR_SELECTED  = 7
COLOR_STATUS_NR = 8   # needs_review
COLOR_STATUS_IN = 9   # inactive
COLOR_DETAIL_BG = 10
COLOR_WARN      = 11

TYPE_COLORS = {
    "URS":    COLOR_URS,
    "SRS":    COLOR_SRS,
    "DDS":    COLOR_DDS,
    "DTC":    COLOR_DTC,
    "script": COLOR_SCRIPT,
}


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class TreeNode:
    req_id:    str
    node_type: str          # URS | SRS | DDS | DTC | script
    title:     str
    status:    str          # active | inactive | needs_review | ""
    parent_id: Optional[str]
    script_id: Optional[str]
    data:      dict         # raw req dict
    children:  list         = field(default_factory=list)
    expanded:  bool         = False
    depth:     int          = 0


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def build_tree(data: dict) -> list[TreeNode]:
    """Return list of script-level root TreeNodes with children attached."""
    scripts_raw: dict = data.get("scripts", {}) or {}
    reqs_raw:    dict = data.get("requirements", {}) or {}

    # Build script nodes
    script_nodes: dict[str, TreeNode] = {}
    for sid, sdata in scripts_raw.items():
        script_nodes[sid] = TreeNode(
            req_id=sid,
            node_type="script",
            title=sdata.get("title", sid),
            status="",
            parent_id=None,
            script_id=None,
            data=sdata,
            depth=0,
        )

    # Build req nodes
    req_nodes: dict[str, TreeNode] = {}
    for rid, rdata in reqs_raw.items():
        req_nodes[rid] = TreeNode(
            req_id=rid,
            node_type=rdata.get("type", ""),
            title=rdata.get("title", rid),
            status=rdata.get("status", ""),
            parent_id=rdata.get("parent"),
            script_id=rdata.get("script"),
            data=rdata,
        )

    # Wire children
    for rid, node in req_nodes.items():
        pid = node.parent_id
        if pid and pid in req_nodes:
            req_nodes[pid].children.append(node)
        else:
            # Root req — attach to script node
            sid = node.script_id
            if sid and sid in script_nodes:
                script_nodes[sid].children.append(node)

    # Set depths recursively
    def set_depth(node: TreeNode, d: int):
        node.depth = d
        for child in node.children:
            set_depth(child, d + 1)

    roots = list(script_nodes.values())
    for r in roots:
        set_depth(r, 0)
        # Sort children by req_id for stable ordering
        _sort_children(r)

    return roots


def _sort_children(node: TreeNode):
    node.children.sort(key=lambda n: n.req_id)
    for child in node.children:
        _sort_children(child)


def walk_visible(nodes: list[TreeNode]) -> list[TreeNode]:
    """Flatten tree into visible order respecting expanded state."""
    result: list[TreeNode] = []
    for node in nodes:
        result.append(node)
        if node.expanded and node.children:
            result.extend(walk_visible(node.children))
    return result


# ── TUI State ──────────────────────────────────────────────────────────────────

class TUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.data: dict = {}
        self.roots: list[TreeNode] = []
        self.flat: list[TreeNode] = []
        self.cursor: int = 0
        self.scroll: int = 0
        self.mode: str = "BROWSE"   # BROWSE | DETAIL | CONFIRM | TEST
        self.confirm_action: str = ""
        self.detail_lines: list[str] = []
        self.test_lines: list[str] = []
        self.message: str = ""

        self._init_colors()
        self.reload()

    def _init_colors(self):
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(COLOR_TITLE,     curses.COLOR_WHITE,   curses.COLOR_BLUE)
        curses.init_pair(COLOR_URS,       curses.COLOR_CYAN,    -1)
        curses.init_pair(COLOR_SRS,       curses.COLOR_GREEN,   -1)
        curses.init_pair(COLOR_DDS,       curses.COLOR_YELLOW,  -1)
        curses.init_pair(COLOR_DTC,       curses.COLOR_MAGENTA, -1)
        curses.init_pair(COLOR_SCRIPT,    curses.COLOR_WHITE,   -1)
        curses.init_pair(COLOR_SELECTED,  curses.COLOR_BLACK,   curses.COLOR_CYAN)
        curses.init_pair(COLOR_STATUS_NR, curses.COLOR_BLACK,   curses.COLOR_YELLOW)
        curses.init_pair(COLOR_STATUS_IN, curses.COLOR_BLACK,   curses.COLOR_RED)
        curses.init_pair(COLOR_DETAIL_BG, curses.COLOR_WHITE,   curses.COLOR_BLUE)
        curses.init_pair(COLOR_WARN,      curses.COLOR_RED,     -1)

    def reload(self):
        old_id = self.flat[self.cursor].req_id if self.flat and self.cursor < len(self.flat) else None
        try:
            self.data = load_yaml(REQS_PATH)
            self.roots = build_tree(self.data)
            self.flat = walk_visible(self.roots)
            # Restore cursor by req_id
            if old_id:
                for i, n in enumerate(self.flat):
                    if n.req_id == old_id:
                        self.cursor = i
                        break
            self.cursor = max(0, min(self.cursor, len(self.flat) - 1))
            self.scroll = 0
            self.message = "Reloaded."
        except Exception as e:
            self.message = f"ERROR loading: {e}"

    def _refresh_flat(self):
        self.flat = walk_visible(self.roots)
        self.cursor = max(0, min(self.cursor, len(self.flat) - 1))

    # ── Navigation ─────────────────────────────────────────────────────────────

    def _current(self) -> Optional[TreeNode]:
        if not self.flat:
            return None
        return self.flat[self.cursor]

    def _siblings(self, node: TreeNode) -> list[TreeNode]:
        """Return list of siblings (same parent) as visible nodes."""
        parent_id = node.parent_id
        # Find parent node
        if parent_id:
            parent = next((n for n in self._all_nodes(self.roots) if n.req_id == parent_id), None)
            if parent:
                return parent.children
        else:
            # Root of script group
            for root in self.roots:
                if root.req_id == node.req_id:
                    return self.roots
                if node in root.children:
                    return root.children
            return self.roots

    def _all_nodes(self, nodes: list[TreeNode]) -> list[TreeNode]:
        result = []
        for n in nodes:
            result.append(n)
            result.extend(self._all_nodes(n.children))
        return result

    def nav_j(self):
        """DTC-045, DTC-049, DTC-052"""
        node = self._current()
        if not node:
            return
        siblings = self._siblings(node)
        try:
            idx = next(i for i, s in enumerate(siblings) if s.req_id == node.req_id)
        except StopIteration:
            idx = -1

        # Find next sibling that is visible in flat list
        for s in siblings[idx + 1:]:
            flat_idx = next((i for i, n in enumerate(self.flat) if n.req_id == s.req_id), None)
            if flat_idx is not None:
                self.cursor = flat_idx
                return

        # Fallback: advance by 1 (DTC-049), clamp at end (DTC-052)
        self.cursor = min(self.cursor + 1, len(self.flat) - 1)

    def nav_k(self):
        """DTC-046, DTC-050"""
        node = self._current()
        if not node:
            return
        siblings = self._siblings(node)
        try:
            idx = next(i for i, s in enumerate(siblings) if s.req_id == node.req_id)
        except StopIteration:
            idx = len(siblings)

        for s in reversed(siblings[:idx]):
            flat_idx = next((i for i, n in enumerate(self.flat) if n.req_id == s.req_id), None)
            if flat_idx is not None:
                self.cursor = flat_idx
                return

        # Fallback: decrease by 1 (DTC-050), clamp at 0
        self.cursor = max(self.cursor - 1, 0)

    def nav_h(self):
        """DTC-047, DTC-051"""
        node = self._current()
        if not node:
            return
        if node.parent_id is None and node.node_type != "script":
            # Root req — try script parent
            pass

        if node.depth == 0 and node.node_type == "script":
            # DTC-051: root node — collapse if expanded
            if node.expanded:
                node.expanded = False
                self._refresh_flat()
            return

        pid = node.parent_id
        if not pid:
            # Script child (URS root) — go to script node
            sid = node.script_id
            if sid:
                flat_idx = next((i for i, n in enumerate(self.flat) if n.req_id == sid), None)
                if flat_idx is not None:
                    self.cursor = flat_idx
            return

        flat_idx = next((i for i, n in enumerate(self.flat) if n.req_id == pid), None)
        if flat_idx is not None:
            self.cursor = flat_idx

    def nav_l(self):
        """DTC-048, DTC-053"""
        node = self._current()
        if not node or not node.children:
            return
        if not node.expanded:
            # DTC-048: expand then move to first child
            node.expanded = True
            self._refresh_flat()
        # DTC-053: move to first child (works for both cases)
        first_child = node.children[0]
        flat_idx = next((i for i, n in enumerate(self.flat) if n.req_id == first_child.req_id), None)
        if flat_idx is not None:
            self.cursor = flat_idx

    def nav_space(self):
        node = self._current()
        if not node:
            return
        node.expanded = not node.expanded
        self._refresh_flat()

    # ── Detail / Test views ─────────────────────────────────────────────────────

    def show_detail(self):
        node = self._current()
        if not node:
            return
        d = node.data
        lines = [
            f"ID:          {d.get('id', node.req_id)}",
            f"Type:        {d.get('type', node.node_type)}",
            f"Title:       {d.get('title', '')}",
            f"Status:      {d.get('status', '')}",
            f"Script:      {d.get('script', '')}",
            f"Parent:      {d.get('parent', 'null')}",
        ]
        desc = d.get("description", "")
        if desc:
            lines.append("")
            lines.append("Description:")
            for ln in str(desc).splitlines():
                lines.append("  " + ln)
        ts = d.get("test_scenario", "")
        if ts:
            lines.append("")
            lines.append("Test Scenario:")
            for ln in str(ts).splitlines():
                lines.append("  " + ln)
        self.detail_lines = lines
        self.mode = "DETAIL"

    def show_tests(self):
        node = self._current()
        if not node:
            return
        all_nodes = self._all_nodes(self.roots)
        dtcs = [n for n in all_nodes if n.node_type == "DTC" and n.parent_id == node.req_id]
        if not dtcs:
            # Search deeper — all DTC descendants
            def get_dtc_descendants(n: TreeNode) -> list[TreeNode]:
                result = []
                for child in n.children:
                    if child.node_type == "DTC":
                        result.append(child)
                    result.extend(get_dtc_descendants(child))
                return result
            dtcs = get_dtc_descendants(node)

        lines = [f"DTC test cases for: {node.req_id} — {node.title}", ""]
        if not dtcs:
            lines.append("  (no DTC children found)")
        for dtc in dtcs:
            lines.append(f"  {dtc.req_id}: {dtc.title}")
            ts = dtc.data.get("test_scenario", "")
            if ts:
                for ln in str(ts).strip().splitlines():
                    lines.append(f"    {ln}")
            lines.append("")
        self.test_lines = lines
        self.mode = "TEST"

    # ── Edit / Delete ───────────────────────────────────────────────────────────

    def edit_current(self):
        node = self._current()
        if not node or node.node_type == "script":
            self.message = "Cannot edit script nodes."
            return

        rid = node.req_id
        req_data = dict(node.data)

        # Write to temp yaml file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", prefix=f"{rid}_", delete=False
        ) as tf:
            yaml.dump({rid: req_data}, tf, default_flow_style=False, allow_unicode=True)
            tmppath = tf.name

        editor = os.environ.get("EDITOR", "vi")
        curses.endwin()
        os.system(f"{editor} {tmppath}")

        # Parse back
        try:
            with open(tmppath) as f:
                edited = yaml.safe_load(f)
            if edited and rid in edited:
                new_data = edited[rid]
                # Update reqs.yaml
                full = load_yaml(REQS_PATH)
                full["requirements"][rid].update(new_data)
                with open(REQS_PATH, "w") as f:
                    yaml.dump(full, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                self.message = f"Saved {rid}."
        except Exception as e:
            self.message = f"Edit error: {e}"
        finally:
            os.unlink(tmppath)

        self.reload()
        self.stdscr.refresh()

    def delete_current(self):
        node = self._current()
        if not node or node.node_type == "script":
            self.message = "Cannot delete script nodes."
            return
        self.confirm_action = f"delete:{node.req_id}"
        self.mode = "CONFIRM"

    def delete_inactive(self):
        self.confirm_action = "delete_inactive"
        self.mode = "CONFIRM"

    def _do_delete(self, req_id: str):
        full = load_yaml(REQS_PATH)
        reqs = full.get("requirements", {})
        if req_id in reqs:
            del reqs[req_id]
            # Also remove from children of parent
            with open(REQS_PATH, "w") as f:
                yaml.dump(full, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            self.message = f"Deleted {req_id}."
        self.reload()

    def _do_delete_inactive(self):
        full = load_yaml(REQS_PATH)
        reqs = full.get("requirements", {})
        to_delete = [k for k, v in reqs.items() if v.get("status") == "inactive"]
        for k in to_delete:
            del reqs[k]
        with open(REQS_PATH, "w") as f:
            yaml.dump(full, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        self.message = f"Deleted {len(to_delete)} inactive requirement(s)."
        self.reload()

    # ── Rendering ───────────────────────────────────────────────────────────────

    def render(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()

        if self.mode in ("DETAIL", "TEST"):
            self._render_overlay(h, w)
            self.stdscr.refresh()
            return

        # Header (3 lines)
        self._render_header(w)

        if self.mode == "CONFIRM":
            self._render_confirm(h, w)
        else:
            self._render_tree(h, w)

        # Status bar
        msg = self.message
        if msg:
            attr = curses.color_pair(COLOR_WARN) if msg.startswith("ERROR") else 0
            self._safe_addstr(h - 1, 0, msg[:w - 1], attr)

        self.stdscr.refresh()

    def _render_header(self, w: int):
        title = "Requirement Project Hierarchy"
        self._safe_addstr(0, 0, title.ljust(w), curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        nav1 = "Nav: hjkl/arrows  space=expand  enter=view"
        nav2 = "Mgmt: t=tests r=reload e=edit d=del D=del-inactive q=quit"
        self._safe_addstr(1, 0, nav1[:w - 1])
        self._safe_addstr(2, 0, nav2[:w - 1])

    def _render_tree(self, h: int, w: int):
        viewport_top    = 3
        viewport_bottom = h - 2
        viewport_height = viewport_bottom - viewport_top

        # Scroll tracking
        if self.cursor < self.scroll:
            self.scroll = self.cursor
        elif self.cursor >= self.scroll + viewport_height:
            self.scroll = self.cursor - viewport_height + 1

        for row_idx in range(viewport_height):
            flat_idx = self.scroll + row_idx
            if flat_idx >= len(self.flat):
                break
            node = self.flat[flat_idx]
            y = viewport_top + row_idx
            self._render_node(node, y, w, selected=(flat_idx == self.cursor))

    def _render_node(self, node: TreeNode, y: int, w: int, selected: bool):
        indent = "  " * node.depth
        if not node.children:
            marker = " > "
        elif node.expanded:
            marker = "[-]"
        else:
            marker = "[+]"

        status_badge = ""
        if node.status == "needs_review":
            status_badge = " [NR]"
        elif node.status == "inactive":
            status_badge = " [--]"

        text = f"{indent}{marker} {node.req_id}: {node.title}{status_badge}"
        text = text[:w - 1]

        if selected:
            attr = curses.color_pair(COLOR_SELECTED) | curses.A_BOLD
        else:
            type_color = TYPE_COLORS.get(node.node_type, 0)
            attr = curses.color_pair(type_color)
            if node.status == "needs_review":
                attr |= curses.A_BOLD
            elif node.status == "inactive":
                attr |= curses.A_DIM

        self._safe_addstr(y, 0, text.ljust(w - 1), attr)

    def _render_overlay(self, h: int, w: int):
        lines = self.detail_lines if self.mode == "DETAIL" else self.test_lines
        title = "Detail View — any key to return" if self.mode == "DETAIL" else "Test Cases — any key to return"

        # Box
        box_h = min(len(lines) + 4, h - 2)
        box_w = min(max((max((len(l) for l in lines), default=40) + 4), 60), w - 4)
        start_y = max(0, (h - box_h) // 2)
        start_x = max(0, (w - box_w) // 2)

        attr = curses.color_pair(COLOR_DETAIL_BG)
        for row in range(box_h):
            self._safe_addstr(start_y + row, start_x, " " * box_w, attr)

        self._safe_addstr(start_y, start_x + 2, title[:box_w - 4], attr | curses.A_BOLD)
        for i, line in enumerate(lines):
            if i + 2 >= box_h - 1:
                break
            self._safe_addstr(start_y + i + 2, start_x + 2, line[:box_w - 4], attr)

    def _render_confirm(self, h: int, w: int):
        self._render_tree(h, w)
        if "delete_inactive" in self.confirm_action:
            msg = "Delete ALL inactive requirements? (y=yes, n/Esc=cancel)"
        else:
            rid = self.confirm_action.split(":", 1)[-1]
            msg = f"Delete '{rid}'? (y=yes, n/Esc=cancel)"
        self._safe_addstr(h - 2, 0, msg[:w - 1], curses.color_pair(COLOR_WARN) | curses.A_BOLD)

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0):
        h, w = self.stdscr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        max_len = w - x - 1
        if max_len <= 0:
            return
        try:
            self.stdscr.addstr(y, x, text[:max_len], attr)
        except curses.error:
            pass

    # ── Event Loop ──────────────────────────────────────────────────────────────

    def handle_key(self, key: int):
        self.message = ""

        if self.mode == "DETAIL":
            self.mode = "BROWSE"
            return

        if self.mode == "TEST":
            self.mode = "BROWSE"
            return

        if self.mode == "CONFIRM":
            if key == ord('y'):
                if "delete_inactive" in self.confirm_action:
                    self._do_delete_inactive()
                else:
                    rid = self.confirm_action.split(":", 1)[-1]
                    self._do_delete(rid)
            self.confirm_action = ""
            self.mode = "BROWSE"
            return

        # BROWSE mode
        if key in (ord('j'), curses.KEY_DOWN):
            self.nav_j()
        elif key in (ord('k'), curses.KEY_UP):
            self.nav_k()
        elif key in (ord('h'), curses.KEY_LEFT):
            self.nav_h()
        elif key in (ord('l'), curses.KEY_RIGHT):
            self.nav_l()
        elif key == ord(' '):
            self.nav_space()
        elif key in (curses.KEY_ENTER, 10, 13):
            self.show_detail()
        elif key == ord('t'):
            self.show_tests()
        elif key == ord('r'):
            self.reload()
        elif key == ord('e'):
            self.edit_current()
        elif key == ord('d'):
            self.delete_current()
        elif key == ord('D'):
            self.delete_inactive()
        elif key == ord('q'):
            raise SystemExit(0)

    def run(self):
        curses.curs_set(0)
        self.stdscr.keypad(True)
        while True:
            self.render()
            key = self.stdscr.getch()
            self.handle_key(key)


# ── Entry point ────────────────────────────────────────────────────────────────

def main(stdscr):
    tui = TUI(stdscr)
    tui.run()


if __name__ == "__main__":
    if not REQS_PATH.exists():
        print(f"ERROR: {REQS_PATH} not found", file=sys.stderr)
        sys.exit(1)
    try:
        curses.wrapper(main)
    except SystemExit:
        pass
    except KeyboardInterrupt:
        pass
