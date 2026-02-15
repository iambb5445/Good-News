#!/usr/bin/env python3
"""
Tile-based WFC image generator using the graph-based WFC engine.

Extracts overlapping NxN tiles from a source image, computes overlap
compatibility, and uses WFC to generate new images with the same local
patterns. Tile size is configurable (default 2x2).
"""

import argparse
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from wfc import (
    WFCGraph, WFCSolver, ContradictionError, EdgeState,
    EdgeConstraint,
)


def extract_tiles(pixels, tile_size=2):
    """Extract all unique NxN overlapping tiles from a pixel array.

    Args:
        pixels: numpy array of shape (H, W, C)
        tile_size: side length of each tile (default 2)

    Returns:
        (tile_list, tile_at) where:
        - tile_list[id] = flat tuple of N*N pixel tuples in row-major order
        - tile_at[y][x] = tile id at position (x, y)
    """
    h, w = pixels.shape[:2]
    tile_to_id = {}
    tile_list = []
    tile_at = []

    for y in range(h - tile_size + 1):
        row = []
        for x in range(w - tile_size + 1):
            tile = tuple(
                tuple(pixels[y + dy, x + dx])
                for dy in range(tile_size)
                for dx in range(tile_size)
            )
            if tile not in tile_to_id:
                tile_to_id[tile] = len(tile_list)
                tile_list.append(tile)
            row.append(tile_to_id[tile])
        tile_at.append(row)

    return tile_list, tile_at


def _tile_right_edge(tile, tile_size):
    """Rightmost (tile_size-1) columns as hashable tuple."""
    return tuple(tile[r * tile_size + c]
                 for r in range(tile_size)
                 for c in range(1, tile_size))


def _tile_left_edge(tile, tile_size):
    """Leftmost (tile_size-1) columns as hashable tuple."""
    return tuple(tile[r * tile_size + c]
                 for r in range(tile_size)
                 for c in range(tile_size - 1))


def _tile_bottom_edge(tile, tile_size):
    """Bottom (tile_size-1) rows as hashable tuple."""
    return tuple(tile[r * tile_size + c]
                 for r in range(1, tile_size)
                 for c in range(tile_size))


def _tile_top_edge(tile, tile_size):
    """Top (tile_size-1) rows as hashable tuple."""
    return tuple(tile[r * tile_size + c]
                 for r in range(tile_size - 1)
                 for c in range(tile_size))


def compute_compatibility(tile_list, tile_size=2):
    """Precompute overlap-compatible tile pairs for east and south directions.

    East: tile A can have tile B to its east iff A's rightmost (N-1) columns
        equal B's leftmost (N-1) columns.
    South: tile A can have tile B to its south iff A's bottom (N-1) rows
        equal B's top (N-1) rows.

    Returns:
        (east_compat, south_compat) where each maps tile_id -> frozenset of
        compatible neighbor tile_ids in that direction.
    """
    # Group tiles by left edge and top edge for fast matching
    by_left_edge = {}
    by_top_edge = {}

    for tid, tile in enumerate(tile_list):
        left = _tile_left_edge(tile, tile_size)
        top = _tile_top_edge(tile, tile_size)
        by_left_edge.setdefault(left, set()).add(tid)
        by_top_edge.setdefault(top, set()).add(tid)

    east_compat = {}
    south_compat = {}

    for tid, tile in enumerate(tile_list):
        right = _tile_right_edge(tile, tile_size)
        bottom = _tile_bottom_edge(tile, tile_size)
        east_compat[tid] = frozenset(by_left_edge.get(right, set()))
        south_compat[tid] = frozenset(by_top_edge.get(bottom, set()))

    return east_compat, south_compat


def render_tile(tile, tile_size=2, scale=10):
    """Render an NxN tile as a scaled RGBA PIL Image.

    Args:
        tile: flat tuple of N*N RGBA pixel tuples in row-major order
        tile_size: side length of the tile
        scale: each pixel becomes scale x scale in the output

    Returns:
        PIL Image of size (tile_size*scale, tile_size*scale)
    """
    arr = np.zeros((tile_size, tile_size, len(tile[0])), dtype=np.uint8)
    for dy in range(tile_size):
        for dx in range(tile_size):
            arr[dy, dx] = tile[dy * tile_size + dx]
    img = Image.fromarray(arr, "RGBA")
    return img.resize((tile_size * scale, tile_size * scale), Image.NEAREST)


def render_analysis(tile_list, east_compat, south_compat, source_name,
                    tile_size=2):
    """Render a visual analysis PNG with tile atlas and adjacency matrices.

    Args:
        tile_list: list of tiles
        east_compat: tile_id -> frozenset of east-compatible tile_ids
        south_compat: tile_id -> frozenset of south-compatible tile_ids
        source_name: name of the source image (for title)
        tile_size: side length of each tile

    Returns:
        PIL Image
    """
    n = len(tile_list)
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = math.ceil(n / cols)

    # Atlas layout - scale tile preview size based on tile_size
    tile_preview = tile_size * 10  # rendered tile pixel size
    cell_w = tile_preview + 4
    cell_h = tile_preview + 18
    atlas_w = cols * cell_w
    atlas_h = rows * cell_h + 20  # 20px top for title

    # Matrix layout
    mat_cell = max(4, min(8, 400 // max(n, 1)))
    margin = 30
    mat_size = margin + n * mat_cell
    mat_total_w = mat_size * 2 + 20  # two matrices side by side with gap

    # Overall canvas
    canvas_w = max(atlas_w, mat_total_w)
    canvas_h = atlas_h + 20 + mat_size + 20  # atlas + gap + matrices + padding
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 9)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 7)
    except (IOError, OSError):
        font = ImageFont.load_default()
        font_small = font

    # -- Tile atlas --
    draw.text((4, 2), f"Tile Atlas: {source_name} ({n} tiles)", fill=(0, 0, 0), font=font)
    atlas_y_off = 20
    for tid in range(n):
        col = tid % cols
        row = tid // cols
        x0 = col * cell_w + 2
        y0 = atlas_y_off + row * cell_h
        # Gray border
        draw.rectangle([x0 - 1, y0 - 1, x0 + tile_preview, y0 + tile_preview],
                       outline=(180, 180, 180))
        tile_img = render_tile(tile_list[tid], tile_size=tile_size)
        canvas.paste(tile_img, (x0, y0))
        # ID label
        draw.text((x0, y0 + tile_preview + 2), str(tid), fill=(80, 80, 80),
                  font=font_small)

    # -- Adjacency matrices --
    mat_y_start = atlas_h + 20

    for mat_idx, (compat, title) in enumerate([
        (east_compat, "East adjacency"),
        (south_compat, "South adjacency"),
    ]):
        mx0 = mat_idx * (mat_size + 20)
        my0 = mat_y_start

        draw.text((mx0 + margin, my0), title, fill=(0, 0, 0), font=font)
        grid_y = my0 + 14

        # Axis labels (every 5th)
        for i in range(0, n, 5):
            # Top labels (column)
            lx = mx0 + margin + i * mat_cell
            draw.text((lx, grid_y), str(i), fill=(80, 80, 80), font=font_small)
            # Left labels (row)
            ly = grid_y + margin + i * mat_cell
            draw.text((mx0, ly), str(i), fill=(80, 80, 80), font=font_small)

        grid_x0 = mx0 + margin
        grid_y0 = grid_y + margin

        for src in range(n):
            for tgt in range(n):
                cx = grid_x0 + tgt * mat_cell
                cy = grid_y0 + src * mat_cell
                if tgt in compat[src]:
                    color = (34, 170, 68)  # green
                else:
                    color = (238, 238, 238)  # light gray
                draw.rectangle([cx, cy, cx + mat_cell - 1, cy + mat_cell - 1], fill=color)

    return canvas


def analyze(input_path, tile_size=2, save_path=None):
    """Analyze tiles and compatibility from a source image.

    Prints a text summary to stdout and saves a visual analysis PNG.

    Args:
        input_path: path to source PNG
        tile_size: side length of each tile (default 2)
        save_path: output PNG path (default: <input_stem>_analysis.png)
    """
    input_path = Path(input_path)
    img = Image.open(input_path).convert("RGBA")
    pixels = np.array(img)
    src_h, src_w = pixels.shape[:2]

    tile_list, tile_at = extract_tiles(pixels, tile_size)
    east_compat, south_compat = compute_compatibility(tile_list, tile_size)

    n = len(tile_list)
    grid_h = len(tile_at)
    grid_w = len(tile_at[0]) if tile_at else 0

    # Text summary
    print(f"=== Tile Analysis: {input_path.name} ===")
    print(f"Source: {src_w}x{src_h} pixels (RGBA)")
    print(f"Unique tiles: {n} ({tile_size}x{tile_size} overlapping)")
    print(f"Tile grid: {grid_w}x{grid_h} positions")
    print()

    print("--- Per-tile compatibility ---")
    for tid in range(n):
        e_neighbors = sorted(east_compat[tid])
        s_neighbors = sorted(south_compat[tid])

        def fmt_list(lst):
            if len(lst) <= 15:
                return " ".join(f"{x:2d}" for x in lst)
            shown = " ".join(f"{x:2d}" for x in lst[:15])
            return f"{shown} ...+{len(lst) - 15} more"

        print(f"Tile {tid:3d}: east={len(e_neighbors):3d} [{fmt_list(e_neighbors)}]  "
              f"south={len(s_neighbors):3d} [{fmt_list(s_neighbors)}]")
    print()

    total_cells = n * n
    east_count = sum(len(v) for v in east_compat.values())
    south_count = sum(len(v) for v in south_compat.values())
    print("--- Summary ---")
    print(f"East  adjacency: {east_count} / {total_cells} cells "
          f"({100 * east_count / total_cells:.1f}%)")
    print(f"South adjacency: {south_count} / {total_cells} cells "
          f"({100 * south_count / total_cells:.1f}%)")

    # Visual analysis
    analysis_img = render_analysis(tile_list, east_compat, south_compat,
                                   input_path.name, tile_size=tile_size)

    if save_path is None:
        save_path = input_path.with_name(f"{input_path.stem}_analysis.png")
    analysis_img.save(str(save_path))
    print(f"\nAnalysis image saved to {save_path}")


def build_tile_wfc(tile_list, east_compat, south_compat, w_out, h_out):
    """Build a WFC graph for tile-based image generation.

    Args:
        tile_list: list of tiles (for domain)
        east_compat: tile_id -> frozenset of east-compatible tile_ids
        south_compat: tile_id -> frozenset of south-compatible tile_ids
        w_out: output grid width (number of tile columns)
        h_out: output grid height (number of tile rows)

    Returns:
        (graph, constraints)
    """
    num_nodes = w_out * h_out
    all_tile_ids = frozenset(range(len(tile_list)))
    property_specs = {"tile": all_tile_ids}
    edge_labels = ["east", "south"]

    # Build sparse edge pairs: only grid-adjacent cells
    edge_pairs = []
    for y in range(h_out):
        for x in range(w_out):
            node = y * w_out + x
            if x + 1 < w_out:
                east_node = y * w_out + (x + 1)
                edge_pairs.append((node, east_node, "east"))
            if y + 1 < h_out:
                south_node = (y + 1) * w_out + x
                edge_pairs.append((node, south_node, "south"))

    graph = WFCGraph(num_nodes, property_specs, edge_labels,
                     edge_pairs=edge_pairs)

    # Pre-establish all grid edges (topology is fixed)
    for src, tgt, label in edge_pairs:
        graph.set_edge_state(src, tgt, label, EdgeState.ESTABLISHED)

    constraints = [
        EdgeConstraint(
            label="east",
            source_prop="tile",
            predicate=lambda s, t, ec=east_compat: t in ec[s],
        ),
        EdgeConstraint(
            label="south",
            source_prop="tile",
            predicate=lambda s, t, sc=south_compat: t in sc[s],
        ),
    ]

    return graph, constraints


def render_output(graph, tile_list, tile_size, w_out, h_out):
    """Render collapsed WFC graph to an RGBA image.

    Each grid node is offset by 1 pixel from its neighbor. Adjacent tiles
    overlap by (tile_size - 1) pixels; WFC constraints guarantee consistency
    in the overlapping region, so repeated writes are safe.
    """
    canvas_w = w_out + tile_size - 1
    canvas_h = h_out + tile_size - 1
    canvas = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)

    for gy in range(h_out):
        for gx in range(w_out):
            node = gy * w_out + gx
            tile_id = graph.get_value(node, "tile")
            tile = tile_list[tile_id]
            for dy in range(tile_size):
                for dx in range(tile_size):
                    canvas[gy + dy, gx + dx] = tile[dy * tile_size + dx]

    return Image.fromarray(canvas, "RGBA")


def generate(input_path, w_out=None, h_out=None, tile_size=2, seed=None,
             max_restarts=100):
    """Generate a new image using tile-based WFC.

    Args:
        input_path: path to source PNG
        w_out: output width in pixels (default: same as input)
        h_out: output height in pixels (default: same as input)
        tile_size: side length of each tile (default 2)
        seed: random seed
        max_restarts: max solver restarts

    Returns:
        PIL Image
    """
    img = Image.open(input_path).convert("RGBA")
    pixels = np.array(img)
    src_h, src_w = pixels.shape[:2]

    print(f"Source: {src_w}x{src_h} pixels")

    # Extract tiles
    tile_list, tile_at = extract_tiles(pixels, tile_size)
    print(f"Unique tiles: {len(tile_list)} ({tile_size}x{tile_size})")

    # Compute compatibility
    east_compat, south_compat = compute_compatibility(tile_list, tile_size)

    # Output grid dimensions (tiles, not pixels)
    # Output pixels = grid_w + (tile_size - 1)
    # So grid_w = w_out - (tile_size - 1)
    if w_out is None:
        w_out = src_w
    if h_out is None:
        h_out = src_h

    grid_w = w_out - (tile_size - 1)
    grid_h = h_out - (tile_size - 1)

    if grid_w < 1 or grid_h < 1:
        raise ValueError(
            f"Output dimensions must be at least {tile_size}x{tile_size} pixels"
        )

    print(f"Output: {w_out}x{h_out} pixels ({grid_w}x{grid_h} tile grid)")

    # Build WFC
    graph, constraints = build_tile_wfc(
        tile_list, east_compat, south_compat, grid_w, grid_h
    )

    rng = random.Random(seed)
    solver = WFCSolver(
        graph, constraints,
        max_restarts=max_restarts,
        rng=rng,
    )

    print(f"Solving (max {max_restarts} restarts)...")
    if not solver.solve():
        print("Failed to generate image after max restarts", file=sys.stderr)
        sys.exit(1)

    print("Solved! Rendering output...")
    return render_output(graph, tile_list, tile_size, grid_w, grid_h)


def main():
    parser = argparse.ArgumentParser(
        description="Tile-based WFC image generator"
    )
    parser.add_argument("input", help="Source PNG image path")
    parser.add_argument("-W", type=int, default=None,
                        help="Output width in pixels (default: same as input)")
    parser.add_argument("-H", type=int, default=None,
                        help="Output height in pixels (default: same as input)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    parser.add_argument("--save", type=str, default="output.png",
                        help="Output file path (default: output.png)")
    parser.add_argument("--restarts", type=int, default=100,
                        help="Max solver restarts (default: 100)")
    parser.add_argument("-T", "--tile-size", type=int, default=2,
                        help="Tile size NxN (default: 2)")
    parser.add_argument("--analyze", action="store_true",
                        help="Analyze tiles and constraints (skip generation)")
    parser.add_argument("--analyze-save", type=str, default=None,
                        help="Output path for analysis PNG")
    args = parser.parse_args()

    if args.analyze:
        analyze(args.input, tile_size=args.tile_size, save_path=args.analyze_save)
        return

    result = generate(
        args.input,
        w_out=args.W,
        h_out=args.H,
        tile_size=args.tile_size,
        seed=args.seed,
        max_restarts=args.restarts,
    )
    result.save(args.save)
    print(f"Saved to {args.save}")


if __name__ == "__main__":
    main()
