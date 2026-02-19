#!/usr/bin/env python3
"""
Growing WFC Family Tree Animation

Generates frames of a family growing node-by-node via GrowingWFCSolver.
One phantom node is always visible; spawning materializes it as a concrete
person and adds a fresh phantom. Each frame captures one WFC step.

Usage:
    python family_wfc_animation_growing.py -n 4 --seed 42 --output-dir wfc_frames_grow
    ffmpeg -framerate 2 -i wfc_frames_grow/frame_%04d.png \
           -c:v libx264 -r 2 -pix_fmt yuv420p family_wfc_grow.mp4
"""

import argparse
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from averageface import CharacterState, get_assets, render_superposition
from family_tree import (
    HAIR_COLORS, EYE_COLORS, SKIN_TINTS, GENDERS,
    EYE_SIZES, EYEBROW_STYLES, NOSE_STYLES,
    _age_predicate, _hair_weight, _skin_weight, _eye_weight,
    _categorical_inherit_weight, _collapse_priority,
)
from family_wfc_animation import (
    HERITABLE_PROPS, CHAR_ASPECT,
    FATHER_POTENTIAL, FATHER_ESTABLISHED,
    MOTHER_POTENTIAL, MOTHER_ESTABLISHED,
    render_thumb, compute_layout, compute_positions, _draw_arrow,
    build_person_state,
)
from wfc import (
    EdgeState, NoSelfEdgeConstraint,
    EdgeConstraint, CardinalityConstraint, SoftConstraint,
)
from wfc_growing import GrowingWFCGraph, GrowingWFCSolver


# ---------------------------------------------------------------------------
# Constraint setup (mirrors build_family_wfc from family_tree.py)
# ---------------------------------------------------------------------------

def build_growing_family_constraints() -> tuple:
    """Build property_specs, edge_labels, and constraints for family WFC."""
    property_specs = {
        "age":           frozenset(range(0, 101)),
        "gender":        GENDERS,
        "hair_color":    HAIR_COLORS,
        "skin_tint":     SKIN_TINTS,
        "eye_color":     EYE_COLORS,
        "eye_size":      EYE_SIZES,
        "eyebrow_style": EYEBROW_STYLES,
        "nose_style":    NOSE_STYLES,
    }
    edge_labels = ["father_of", "mother_of"]

    constraints = [
        NoSelfEdgeConstraint(),
        # Father must be male
        EdgeConstraint("father_of", "gender", "gender",
                       lambda sv, tv: sv == "male"),
        # Mother must be female
        EdgeConstraint("mother_of", "gender", "gender",
                       lambda sv, tv: sv == "female"),
        # Age constraints
        EdgeConstraint("father_of", "age", "age", _age_predicate),
        EdgeConstraint("mother_of", "age", "age", _age_predicate),
        # At most 1 incoming father / mother per person
        CardinalityConstraint("father_of", "incoming", 0, 1),
        CardinalityConstraint("mother_of", "incoming", 0, 1),
    ]

    # Soft constraints for genetic inheritance (both edge directions)
    for label in ["father_of", "mother_of"]:
        constraints.append(
            SoftConstraint(label, "hair_color", weight_fn=_hair_weight))
        constraints.append(
            SoftConstraint(label, "skin_tint", weight_fn=_skin_weight))
        constraints.append(
            SoftConstraint(label, "eye_color", weight_fn=_eye_weight))
        constraints.append(
            SoftConstraint(label, "eye_size",
                           weight_fn=_categorical_inherit_weight))
        constraints.append(
            SoftConstraint(label, "eyebrow_style",
                           weight_fn=_categorical_inherit_weight))
        constraints.append(
            SoftConstraint(label, "nose_style",
                           weight_fn=_categorical_inherit_weight))

    return property_specs, edge_labels, constraints


# ---------------------------------------------------------------------------
# Edge drawing (growing variant)
# ---------------------------------------------------------------------------

def draw_edges_growing(canvas: Image.Image,
                       graph: GrowingWFCGraph,
                       concrete_ids: list,
                       phantom_id: int,
                       node_positions: dict) -> Image.Image:
    """Draw edges on an RGBA overlay composited onto canvas.

    Concrete↔concrete edges: full alpha.
    Concrete↔phantom edges: 25% of normal alpha.
    """
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    all_nodes = list(concrete_ids)
    if phantom_id is not None:
        all_nodes.append(phantom_id)

    for src in all_nodes:
        for tgt in all_nodes:
            if src == tgt:
                continue
            if src not in node_positions or tgt not in node_positions:
                continue

            involves_phantom = (src == phantom_id) or (tgt == phantom_id)
            x1, y1 = node_positions[src]
            x2, y2 = node_positions[tgt]

            for label, pot_rgba, est_rgba in [
                ("father_of", FATHER_POTENTIAL, FATHER_ESTABLISHED),
                ("mother_of", MOTHER_POTENTIAL, MOTHER_ESTABLISHED),
            ]:
                state = graph.edge_state(src, tgt, label)
                if state == EdgeState.ELIMINATED:
                    continue

                if involves_phantom:
                    # 25% of normal alpha
                    if state == EdgeState.POTENTIAL:
                        color = (*pot_rgba[:3], int(pot_rgba[3] * 0.25))
                    else:
                        color = (*est_rgba[:3], int(est_rgba[3] * 0.25))
                    draw.line([(x1, y1), (x2, y2)], fill=color, width=1)
                else:
                    if state == EdgeState.POTENTIAL:
                        draw.line([(x1, y1), (x2, y2)], fill=pot_rgba,
                                  width=1)
                    else:  # ESTABLISHED
                        _draw_arrow(draw, x1, y1, x2, y2, est_rgba, width=3)

    return Image.alpha_composite(canvas, overlay)


# ---------------------------------------------------------------------------
# Status counters
# ---------------------------------------------------------------------------

def _count_collapsed_concrete(graph: GrowingWFCGraph,
                               concrete_ids: list) -> int:
    count = 0
    for n in concrete_ids:
        for prop in HERITABLE_PROPS:
            if graph.domain(n, prop).is_collapsed():
                count += 1
    return count


def _count_potential_concrete_edges(graph: GrowingWFCGraph,
                                    concrete_ids: list) -> int:
    concrete_set = set(concrete_ids)
    return sum(
        1 for (src, tgt, _), st in graph._edges.items()
        if st == EdgeState.POTENTIAL
        and src in concrete_set
        and tgt in concrete_set
    )


# ---------------------------------------------------------------------------
# Frame rendering (growing variant)
# ---------------------------------------------------------------------------

def render_frame(graph: GrowingWFCGraph,
                 concrete_ids: list,
                 phantom_id: int,
                 node_positions: dict,
                 canvas_dim: int,
                 thumb_w: int,
                 thumb_h: int,
                 cache: dict,
                 fixed_clothes: dict,
                 per_person: dict,
                 frame_idx: int) -> Image.Image:
    """Render one animation frame of the growing family."""
    canvas = Image.new("RGBA", (canvas_dim, canvas_dim), (255, 255, 255, 255))

    # Edges behind thumbnails
    canvas = draw_edges_growing(
        canvas, graph, concrete_ids, phantom_id, node_positions)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        font_bold = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
        font_large = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except (OSError, IOError):
        font = font_bold = font_large = ImageFont.load_default()

    draw = ImageDraw.Draw(canvas)

    # Draw concrete nodes normally
    for node_id in concrete_ids:
        if node_id not in node_positions:
            continue
        cx_n, cy_n = node_positions[node_id]
        state = build_person_state(graph, node_id, fixed_clothes, per_person)
        thumb = render_thumb(state, thumb_w, thumb_h, cache)

        paste_x = cx_n - thumb_w // 2
        paste_y = cy_n - thumb_h // 2
        if paste_x < 0 or paste_y < 0:
            continue
        if paste_x + thumb_w > canvas_dim or paste_y + thumb_h > canvas_dim:
            continue

        canvas.paste(thumb, (paste_x, paste_y), thumb)
        gender_dom = graph.domain(node_id, "gender")
        g_suffix = ("M" if gender_dom.get_value() == "male" else "F") \
            if gender_dom.is_collapsed() else "?"
        draw.text((cx_n - 12, paste_y + thumb_h + 2), f"P{node_id} {g_suffix}",
                  fill=(0, 0, 0, 255), font=font_bold)

    # Draw phantom at 40% opacity with "?" label
    if phantom_id is not None and phantom_id in node_positions:
        cx_n, cy_n = node_positions[phantom_id]
        state = build_person_state(graph, phantom_id, fixed_clothes, per_person)
        thumb = render_thumb(state, thumb_w, thumb_h, cache)

        # Fade to 40% opacity
        r_ch, g_ch, b_ch, a_ch = thumb.split()
        a_ch = a_ch.point(lambda x: int(x * 0.4))
        thumb_faded = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))

        paste_x = cx_n - thumb_w // 2
        paste_y = cy_n - thumb_h // 2
        if (0 <= paste_x and 0 <= paste_y
                and paste_x + thumb_w <= canvas_dim
                and paste_y + thumb_h <= canvas_dim):
            canvas.paste(thumb_faded, (paste_x, paste_y), thumb_faded)
            # "?" centered over phantom
            draw.text((cx_n - 8, cy_n - 14), "?",
                      fill=(100, 100, 100, 200), font=font_large)
            draw.text((cx_n - 8, paste_y + thumb_h + 2), "?",
                      fill=(80, 80, 80, 255), font=font_bold)

    # Status line
    k = len(concrete_ids)
    collapsed = _count_collapsed_concrete(graph, concrete_ids)
    total_props = k * len(HERITABLE_PROPS)
    potential = _count_potential_concrete_edges(graph, concrete_ids)
    status = (
        f"Frame {frame_idx:03d}  |  "
        f"Concrete: {k}  |  "
        f"Collapsed: {collapsed}/{total_props}  |  "
        f"Potential edges: {potential}"
    )
    draw.text((10, canvas_dim - 20), status, fill=(60, 60, 60, 255), font=font)

    return canvas


# ---------------------------------------------------------------------------
# Main animation generator
# ---------------------------------------------------------------------------

def generate_animation(n_target: int, seed: int, output_dir: str,
                       thumb_w: int):
    """Generate growing WFC family animation frames and save to output_dir."""
    rng = random.Random(seed)
    assets = get_assets()

    # Fixed clothing shared across all people and all frames
    fixed_clothes = {
        "shirt_color": rng.choice(assets["shirt_colors"]),
        "pants_color": rng.choice(assets["pants_colors"]),
        "shoe_color":  rng.choice(assets["shoe_colors"]),
    }

    # Per-person non-heritable traits, created lazily at spawn time
    per_person: dict = {}

    def make_person_traits(node_id: int):
        per_person[node_id] = {
            "shirt_style":      rng.choice(assets["shirt_styles"]),
            "sleeve_length":    rng.choice(assets["sleeve_lengths"]),
            "pants_style":      rng.choice(assets["pants_styles"]),
            "leg_length":       rng.choice(assets["leg_lengths"]),
            "shoe_style":       rng.choice(assets["shoe_styles"]),
            "mouth_expression": rng.choice(assets["mouth_expressions"]),
            # Pre-assign hair style for each gender
            "hair_style_Man":   rng.choice(assets["hair_styles_man"]),
            "hair_style_Woman": rng.choice(assets["hair_styles_woman"]),
        }

    # Build constraints and create solver
    property_specs, edge_labels, constraints = build_growing_family_constraints()
    solver = GrowingWFCSolver(
        property_specs, edge_labels, constraints,
        rng=rng,
        priority_fn=_collapse_priority,
    )

    # Create traits for the initial phantom
    make_person_traits(solver.phantom_id)

    # Layout: n_target + 1 circle slots (concrete 0..n-1, phantom at slot k)
    thumb_h = int(thumb_w * CHAR_ASPECT)
    canvas_dim, radius, center = compute_layout(n_target + 1, thumb_w)
    all_positions = compute_positions(n_target + 1, radius, center, center)

    cache: dict = {}
    frames: list = []

    def get_node_positions() -> dict:
        """Map current node IDs to circle positions."""
        pos = {}
        for k, cid in enumerate(solver.concrete_ids):
            pos[cid] = all_positions[k]
        if solver.phantom_id is not None:
            pos[solver.phantom_id] = all_positions[len(solver.concrete_ids)]
        return pos

    def capture():
        frame = render_frame(
            solver.graph, solver.concrete_ids, solver.phantom_id,
            get_node_positions(), canvas_dim, thumb_w, thumb_h,
            cache, fixed_clothes, per_person, len(frames),
        )
        frames.append(frame)

    # Frame 0: phantom only (completely empty looking)
    capture()

    print(f"Running growing WFC for {n_target} people (seed={seed})...")

    while True:
        if solver.is_concrete_collapsed():
            solver.resolve_concrete_edges()
            capture()                              # edge-resolved frame
            if len(solver.concrete_ids) >= n_target:
                break
            solver.spawn()
            make_person_traits(solver.phantom_id)  # traits for new phantom
            capture()                              # spawn frame
        else:
            result = solver.step_auto()
            if result is None:
                break
            capture()                              # one property collapsed

    # Save frames
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print(f"Saving {len(frames)} frames to {output_dir}/...")
    for i, frame in enumerate(frames):
        rgb_frame = Image.new("RGB", frame.size, (255, 255, 255))
        rgb_frame.paste(frame, mask=frame.split()[3])
        rgb_frame.save(out_path / f"frame_{i:04d}.png")

    print(f"\nDone. {len(frames)} frames saved.")
    print("\nTo create video, run:")
    print(f"  ffmpeg -framerate 2 -i {output_dir}/frame_%04d.png "
          f"-c:v libx264 -r 2 -pix_fmt yuv420p family_wfc_grow.mp4")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate growing WFC step-by-step family tree animation"
    )
    parser.add_argument("-n", type=int, default=4,
                        help="Number of concrete family members (default: 4)")
    parser.add_argument("-s", "--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("--output-dir", default="wfc_frames_grow",
                        help="Output directory for frames (default: wfc_frames_grow)")
    parser.add_argument("--thumb-size", type=int, default=100,
                        help="Thumbnail width in pixels (default: 100)")
    args = parser.parse_args()

    generate_animation(
        n_target=args.n,
        seed=args.seed,
        output_dir=args.output_dir,
        thumb_w=args.thumb_size,
    )


if __name__ == "__main__":
    main()
