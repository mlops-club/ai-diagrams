#!/usr/bin/env python3
"""Convert Mermaid sequence diagrams (.mmd) to Excalidraw (.excalidraw) JSON."""

import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Constants ────────────────────────────────────────────────────────────────

CHAR_WIDTH = 9.6          # Approx monospace char width at font size ~16
ACTOR_BOX_PADDING = 40    # Horizontal padding inside actor box
ACTOR_BOX_HEIGHT = 60
ACTOR_BOX_Y = 30
ACTOR_GAP = 80            # Gap between actor box edges
LIFELINE_START_Y = ACTOR_BOX_Y + ACTOR_BOX_HEIGHT  # 90
FIRST_EVENT_Y = 140
MESSAGE_STEP = 55         # Vertical distance between messages
SELF_ARROW_WIDTH = 60     # Horizontal bump of self-ref loop
SELF_ARROW_HEIGHT = 35    # Vertical drop of self-ref loop
NOTE_HEIGHT = 40
TITLE_Y = -30
TITLE_FONT_SIZE = 24
ACTOR_FONT_SIZE = 18
LABEL_FONT_SIZE = 14
PHASE_FONT_SIZE = 16
PHASE_LABEL_X = 20
FONT_FAMILY = 3           # Code / monospace


# ── Data Structures ─────────────────────────────────────────────────────────

class ArrowStyle(Enum):
    SOLID_FILLED = "->>"
    DASHED_FILLED = "-->>"
    SOLID_OPEN = "->"
    DASHED_OPEN = "-->"


@dataclass
class Actor:
    key: str
    label: str
    index: int
    center_x: float = 0.0
    box_x: float = 0.0
    box_width: float = 0.0


@dataclass
class Message:
    source: str
    target: str
    text: str
    arrow_style: ArrowStyle
    y: float = 0.0

    @property
    def is_self(self) -> bool:
        return self.source == self.target


@dataclass
class Note:
    position: str       # "right", "left", "over"
    actors: list[str]
    text: str
    y: float = 0.0


@dataclass
class RectBlock:
    label: str
    color: str
    start_y: float = 0.0
    end_y: float = 0.0


@dataclass
class SequenceDiagram:
    title: Optional[str] = None
    actors: dict[str, Actor] = field(default_factory=dict)
    actor_order: list[str] = field(default_factory=list)
    events: list = field(default_factory=list)
    lifeline_end_y: float = 0.0


# ── Parser ───────────────────────────────────────────────────────────────────

PATTERNS = {
    "header": re.compile(r"^\s*sequenceDiagram\s*$"),
    "title": re.compile(r"^\s*title\s+(.+)$", re.IGNORECASE),
    "participant": re.compile(
        r"^\s*(?:participant|actor)\s+(\S+)\s+as\s+(.+)$"
    ),
    "participant_short": re.compile(
        r"^\s*(?:participant|actor)\s+(\S+)\s*$"
    ),
    "message": re.compile(
        r"^\s*(\w+)\s*(--?>>?)\s*(\w+)\s*:\s*(.+)$"
    ),
    "note": re.compile(
        r"^\s*Note\s+(right of|left of|over)\s+"
        r"(\S+?)(?:\s*,\s*(\S+?))?\s*:\s*(.+)$",
        re.IGNORECASE,
    ),
    "rect_start": re.compile(r"^\s*rect\s+(.+)$"),
    "rect_end": re.compile(r"^\s*end\s*$"),
    "comment": re.compile(r"^\s*%%"),
}

ARROW_MAP = {
    "->>": ArrowStyle.SOLID_FILLED,
    "-->>": ArrowStyle.DASHED_FILLED,
    "->": ArrowStyle.SOLID_OPEN,
    "-->": ArrowStyle.DASHED_OPEN,
}


def parse(lines: list[str]) -> SequenceDiagram:
    diagram = SequenceDiagram()
    actor_idx = 0
    rect_stack: list[RectBlock] = []

    def ensure_actor(key: str) -> None:
        nonlocal actor_idx
        if key not in diagram.actors:
            diagram.actors[key] = Actor(key=key, label=key, index=actor_idx)
            diagram.actor_order.append(key)
            actor_idx += 1

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line or PATTERNS["comment"].match(line):
            continue
        if PATTERNS["header"].match(line):
            continue

        m = PATTERNS["title"].match(line)
        if m:
            diagram.title = m.group(1).strip()
            continue

        m = PATTERNS["participant"].match(line)
        if m:
            key, label = m.group(1), m.group(2).strip()
            diagram.actors[key] = Actor(key=key, label=label, index=actor_idx)
            diagram.actor_order.append(key)
            actor_idx += 1
            continue

        m = PATTERNS["participant_short"].match(line)
        if m:
            key = m.group(1)
            diagram.actors[key] = Actor(key=key, label=key, index=actor_idx)
            diagram.actor_order.append(key)
            actor_idx += 1
            continue

        m = PATTERNS["message"].match(line)
        if m:
            src, arrow_str, tgt, text = (
                m.group(1), m.group(2), m.group(3), m.group(4).strip(),
            )
            ensure_actor(src)
            ensure_actor(tgt)
            msg = Message(
                source=src, target=tgt, text=text,
                arrow_style=ARROW_MAP[arrow_str],
            )
            diagram.events.append(("message", msg))
            continue

        m = PATTERNS["note"].match(line)
        if m:
            pos_raw = m.group(1).lower()
            if "right" in pos_raw:
                pos = "right"
            elif "left" in pos_raw:
                pos = "left"
            else:
                pos = "over"
            actors = [m.group(2)]
            if m.group(3):
                actors.append(m.group(3))
            for a in actors:
                ensure_actor(a)
            note = Note(position=pos, actors=actors, text=m.group(4).strip())
            diagram.events.append(("note", note))
            continue

        m = PATTERNS["rect_start"].match(line)
        if m:
            color = m.group(1).strip()
            block = RectBlock(label="", color=color)
            rect_stack.append(block)
            diagram.events.append(("rect_start", block))
            continue

        if PATTERNS["rect_end"].match(line):
            if rect_stack:
                block = rect_stack.pop()
                diagram.events.append(("rect_end", block))
            continue

    return diagram


# ── Layout ───────────────────────────────────────────────────────────────────

def _label_lines(label: str) -> list[str]:
    """Split a label on literal \\n sequences for multi-line display."""
    return (label
            .replace("\\n", "\n")
            .replace("<br/>", "\n")
            .replace("<br>", "\n")
            .split("\n"))


def _max_line_width(label: str) -> float:
    return max(len(l) for l in _label_lines(label)) * CHAR_WIDTH


def _phase_label_text(block: RectBlock) -> str:
    """Extract the label text from a rect block's color string."""
    parts = block.color.split(None, 1)
    if len(parts) == 2 and (parts[0].startswith("#") or parts[0].startswith("rgb")):
        return parts[1]
    return ""


def layout(diagram: SequenceDiagram) -> None:
    # Pre-compute max phase label width to reserve left margin
    max_phase_w = 0.0
    for event_type, event in diagram.events:
        if event_type == "rect_start":
            label = _phase_label_text(event)
            if label:
                w = len(label) * PHASE_FONT_SIZE * 0.6 + 20
                max_phase_w = max(max_phase_w, w)

    # Horizontal: place actor boxes with left margin for phase labels
    left_margin = max(120.0, max_phase_w + 30)
    x_cursor = left_margin
    for key in diagram.actor_order:
        actor = diagram.actors[key]
        label_w = _max_line_width(actor.label)
        box_w = max(label_w + ACTOR_BOX_PADDING, 120.0)
        box_w = round(box_w / 2) * 2  # even number

        actor.box_x = x_cursor
        actor.box_width = box_w
        actor.center_x = x_cursor + box_w / 2
        x_cursor += box_w + ACTOR_GAP

    # Vertical: assign y to each event
    y = FIRST_EVENT_Y
    for event_type, event in diagram.events:
        if event_type == "message":
            event.y = y
            y += MESSAGE_STEP
            if event.is_self:
                y += SELF_ARROW_HEIGHT
        elif event_type == "note":
            event.y = y
            y += NOTE_HEIGHT + 20
        elif event_type == "rect_start":
            event.start_y = y
            y += 35  # space for the phase label before first message
        elif event_type == "rect_end":
            event.end_y = y - 10

    diagram.lifeline_end_y = y + 40


# ── Renderer ─────────────────────────────────────────────────────────────────

class IdGen:
    def __init__(self):
        self._n = 0
        self._seed = 100

    def id(self, prefix: str = "el") -> str:
        self._n += 1
        return f"{prefix}_{self._n}"

    def seed(self) -> int:
        self._seed += 2
        return self._seed


def _base(ids: IdGen, etype: str, x, y, w, h, **overrides) -> dict:
    s = ids.seed()
    el = {
        "id": ids.id(etype[:3]),
        "type": etype,
        "x": x, "y": y,
        "width": w, "height": h,
        "angle": 0,
        "strokeColor": "#1e1e1e",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": s,
        "version": 1,
        "versionNonce": s + 1,
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
    }
    el.update(overrides)
    return el


def _rect(ids: IdGen, x, y, w, h, bg="#a5d8ff", **kw) -> dict:
    return _base(ids, "rectangle", x, y, w, h,
                 backgroundColor=bg, fillStyle="solid",
                 roundness={"type": 3}, **kw)


def _text(ids: IdGen, x, y, txt, font_size=LABEL_FONT_SIZE,
          align="center", w=None, h=None, **kw) -> dict:
    lines = txt.split("\n")
    if w is None:
        w = max(len(l) for l in lines) * font_size * 0.6
    if h is None:
        h = len(lines) * font_size * 1.5
    return _base(ids, "text", x, y, w, h,
                 text=txt, fontSize=font_size, fontFamily=FONT_FAMILY,
                 textAlign=align, verticalAlign="middle",
                 containerId=None, originalText=txt,
                 lineHeight=1.25, strokeWidth=1, **kw)


def _arrow(ids: IdGen, x, y, points, dashed=False, arrowhead=True, **kw) -> dict:
    dx = max(abs(p[0]) for p in points)
    dy = max(abs(p[1]) for p in points)
    return _base(ids, "arrow", x, y, dx, dy,
                 points=points,
                 lastCommittedPoint=None,
                 startBinding=None, endBinding=None,
                 startArrowhead=None,
                 endArrowhead="arrow" if arrowhead else None,
                 roundness={"type": 2},
                 strokeStyle="dashed" if dashed else "solid",
                 **kw)


def _line(ids: IdGen, x, y, points, **kw) -> dict:
    dx = max(abs(p[0]) for p in points)
    dy = max(abs(p[1]) for p in points)
    return _base(ids, "line", x, y, dx, dy,
                 points=points,
                 lastCommittedPoint=None,
                 startBinding=None, endBinding=None,
                 startArrowhead=None, endArrowhead=None,
                 **kw)


def _resolve_escapes(text: str) -> str:
    """Convert literal \\n sequences to real newlines."""
    return (text
            .replace("\\n", "\n")
            .replace("<br/>", "\n")
            .replace("<br>", "\n"))


def _contained_text(ids: IdGen, rect_id: str, text_id: str,
                    rx, ry, rw, rh, txt, font_size) -> dict:
    """Create a text element centered inside a container rectangle.
    Excalidraw expects top-left x/y positioned to center the text."""
    lines = txt.split("\n")
    tw = max(len(l) for l in lines) * font_size * 0.6
    th = len(lines) * font_size * 1.25
    # Center the text within the container
    tx = rx + (rw - tw) / 2
    ty = ry + (rh - th) / 2
    text_el = _text(ids, tx, ty, txt, font_size=font_size, w=tw, h=th)
    text_el["id"] = text_id
    text_el["containerId"] = rect_id
    text_el["textAlign"] = "center"
    text_el["verticalAlign"] = "middle"
    return text_el


def render_actor(ids: IdGen, actor: Actor) -> list[dict]:
    """Render actor box with grouped label text."""
    elements = []
    resolved = _resolve_escapes(actor.label)
    label_lines = resolved.split("\n")
    text_h = len(label_lines) * ACTOR_FONT_SIZE * 1.25
    box_h = max(ACTOR_BOX_HEIGHT, text_h + 20)

    rect_id = ids.id("rec")
    text_id = ids.id("tex")

    rect_el = _rect(ids, actor.box_x, ACTOR_BOX_Y,
                     actor.box_width, box_h)
    rect_el["id"] = rect_id
    rect_el["boundElements"] = [{"id": text_id, "type": "text"}]

    text_el = _contained_text(ids, rect_id, text_id,
                              actor.box_x, ACTOR_BOX_Y,
                              actor.box_width, box_h,
                              resolved, ACTOR_FONT_SIZE)

    elements.append(rect_el)
    elements.append(text_el)
    return elements


def render_lifeline(ids: IdGen, actor: Actor, end_y: float) -> list[dict]:
    """Render dashed vertical lifeline."""
    h = end_y - LIFELINE_START_Y
    return [_line(ids, actor.center_x, LIFELINE_START_Y,
                  [[0, 0], [0, h]],
                  strokeStyle="dashed", strokeWidth=1,
                  strokeColor="#868e96")]


def render_message(ids: IdGen, msg: Message, diagram: SequenceDiagram) -> list[dict]:
    """Render message arrow and label."""
    elements = []
    is_dashed = msg.arrow_style in (ArrowStyle.DASHED_FILLED, ArrowStyle.DASHED_OPEN)
    has_head = msg.arrow_style in (ArrowStyle.SOLID_FILLED, ArrowStyle.DASHED_FILLED)

    src_x = diagram.actors[msg.source].center_x
    tgt_x = diagram.actors[msg.target].center_x

    resolved = _resolve_escapes(msg.text)

    if msg.is_self:
        # Self-referencing: rectangular loop
        points = [
            [0, 0],
            [SELF_ARROW_WIDTH, 0],
            [SELF_ARROW_WIDTH, SELF_ARROW_HEIGHT],
            [0, SELF_ARROW_HEIGHT],
        ]
        elements.append(_arrow(ids, src_x, msg.y, points,
                               dashed=is_dashed, arrowhead=has_head))
        # Label to the right of the loop
        elements.append(_text(ids, src_x + SELF_ARROW_WIDTH + 5, msg.y + 5,
                              resolved, align="left"))
    else:
        dx = tgt_x - src_x
        points = [[0, 0], [dx, 0]]
        elements.append(_arrow(ids, src_x, msg.y, points,
                               dashed=is_dashed, arrowhead=has_head))
        # Label centered above the arrow
        mid_x = min(src_x, tgt_x) + abs(dx) / 2
        label_lines = resolved.split("\n")
        tw = max(len(l) for l in label_lines) * LABEL_FONT_SIZE * 0.6
        th = len(label_lines) * LABEL_FONT_SIZE * 1.5
        elements.append(_text(ids, mid_x - tw / 2, msg.y - th - 2,
                              resolved, w=tw, h=th))
    return elements


def render_note(ids: IdGen, note: Note, diagram: SequenceDiagram) -> list[dict]:
    """Render a note box with text."""
    elements = []
    tw = len(note.text) * LABEL_FONT_SIZE * 0.6 + 20
    th = NOTE_HEIGHT

    if note.position == "over" and len(note.actors) == 2:
        ax1 = diagram.actors[note.actors[0]].center_x
        ax2 = diagram.actors[note.actors[1]].center_x
        nx = min(ax1, ax2) - 10
        tw = abs(ax2 - ax1) + 20
    elif note.position == "over":
        cx = diagram.actors[note.actors[0]].center_x
        nx = cx - tw / 2
    elif note.position == "right":
        cx = diagram.actors[note.actors[0]].center_x
        nx = cx + 20
    else:  # left
        cx = diagram.actors[note.actors[0]].center_x
        nx = cx - tw - 20

    elements.append(_rect(ids, nx, note.y, tw, th, bg="#fff3bf"))
    elements.append(_text(ids, nx + 10, note.y + 8, note.text,
                          w=tw - 20, h=th - 16))
    return elements


def render_rect_block(ids: IdGen, block: RectBlock,
                      diagram: SequenceDiagram) -> list[dict]:
    """Render a rect block as a phase-label badge, right-justified
    so its right edge sits just left of the first actor's lifeline."""
    label = _phase_label_text(block)
    parts = block.color.split(None, 1)
    color = parts[0] if parts else block.color

    if not label:
        return []

    elements = []
    text_h = PHASE_FONT_SIZE * 1.25
    bw = len(label) * PHASE_FONT_SIZE * 0.6 + 20
    bh = text_h + 10

    # Right edge just left of first actor's lifeline
    if diagram.actor_order:
        first = diagram.actors[diagram.actor_order[0]]
        bx = first.center_x - 20 - bw
    else:
        bx = PHASE_LABEL_X

    rect_id = ids.id("rec")
    text_id = ids.id("tex")

    rect_el = _rect(ids, bx, block.start_y, bw, bh, bg=color)
    rect_el["id"] = rect_id
    rect_el["boundElements"] = [{"id": text_id, "type": "text"}]

    text_el = _contained_text(ids, rect_id, text_id,
                              bx, block.start_y, bw, bh,
                              label, PHASE_FONT_SIZE)

    elements.append(rect_el)
    elements.append(text_el)
    return elements


def render(diagram: SequenceDiagram) -> dict:
    ids = IdGen()
    elements: list[dict] = []

    # Title
    if diagram.title:
        total_w = 0.0
        if diagram.actor_order:
            first = diagram.actors[diagram.actor_order[0]]
            last = diagram.actors[diagram.actor_order[-1]]
            total_w = (last.box_x + last.box_width) - first.box_x
        tw = len(diagram.title) * TITLE_FONT_SIZE * 0.6
        tx = (first.box_x + total_w / 2 - tw / 2) if diagram.actor_order else 200
        elements.append(_text(ids, tx, TITLE_Y, diagram.title,
                              font_size=TITLE_FONT_SIZE))

    # Actor boxes
    for key in diagram.actor_order:
        elements.extend(render_actor(ids, diagram.actors[key]))

    # Lifelines
    for key in diagram.actor_order:
        elements.extend(render_lifeline(ids, diagram.actors[key],
                                        diagram.lifeline_end_y))

    # Events
    for event_type, event in diagram.events:
        if event_type == "message":
            elements.extend(render_message(ids, event, diagram))
        elif event_type == "note":
            elements.extend(render_note(ids, event, diagram))
        elif event_type == "rect_start":
            elements.extend(render_rect_block(ids, event, diagram))

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "mermaid2excalidraw",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
        "files": {},
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) != 3:
        print(
            "Usage: uv run mermaid2excalidraw.py <input.mmd> <output.excalidraw>",
            file=sys.stderr,
        )
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    with open(input_path) as f:
        lines = f.readlines()

    diagram = parse(lines)
    layout(diagram)
    doc = render(diagram)

    with open(output_path, "w") as f:
        json.dump(doc, f, indent=2)

    print(f"Wrote {output_path} ({len(doc['elements'])} elements)")


if __name__ == "__main__":
    main()
