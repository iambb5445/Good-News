#!/usr/bin/env python3
"""
Family tree generator using the graph-based WFC engine.

Generates genetically-consistent families whose members map to AverageFace
characters. Genetic traits (hair color, skin tint, eye color) are inherited
with realistic variation through soft constraints.
"""

import argparse
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from averageface import CharacterState, get_assets
from wfc import (
    WFCGraph, WFCSolver, ContradictionError, EdgeState,
    NodeConstraint, EdgeConstraint, CardinalityConstraint,
    SoftConstraint, NoSelfEdgeConstraint,
)

# Hair color groups for inheritance
HAIR_DARK = frozenset({"Black", "Brown 1", "Brown 2"})
HAIR_LIGHT = frozenset({"Blonde", "Tan", "White"})
HAIR_MEDIUM = frozenset({"Red", "Grey"})

HAIR_GROUPS = {
    "Black": HAIR_DARK, "Brown 1": HAIR_DARK, "Brown 2": HAIR_DARK,
    "Blonde": HAIR_LIGHT, "Tan": HAIR_LIGHT, "White": HAIR_LIGHT,
    "Red": HAIR_MEDIUM, "Grey": HAIR_MEDIUM,
}

# All hair colors from AverageFace assets
HAIR_COLORS = frozenset({"Black", "Blonde", "Brown 1", "Brown 2",
                          "Grey", "Red", "Tan", "White"})

EYE_COLORS = frozenset({"Black", "Blue", "Brown", "Green", "Red"})

SKIN_TINTS = frozenset(range(1, 9))

GENDERS = frozenset({"male", "female"})

AGES = frozenset(range(0, 101))

EYE_SIZES = frozenset({"large", "small"})
EYEBROW_STYLES = frozenset({1, 2, 3})
NOSE_STYLES = frozenset({1, 2, 3})


@dataclass
class Person:
    """A family member with genetic and demographic traits."""
    id: int
    age: int
    gender: str
    hair_color: str
    skin_tint: int
    eye_color: str
    eye_size: str
    eyebrow_style: int
    nose_style: int

    def to_character_state(self) -> CharacterState:
        """Create a CharacterState with genetic properties fixed."""
        state = CharacterState()
        state.fix("skin_tint", self.skin_tint)
        state.fix("hair_color", self.hair_color)
        state.fix("eye_color", self.eye_color)
        state.fix("eye_size", self.eye_size)
        state.fix("eyebrow_style", self.eyebrow_style)
        state.fix("nose_style", self.nose_style)
        # Map gender to hair gender
        if self.gender == "male":
            state.fix("hair_gender", "Man")
        else:
            state.fix("hair_gender", "Woman")
        return state


class FamilyTree:
    """A collection of people with parent-child relationships."""

    def __init__(self, people: list, father_edges: list, mother_edges: list):
        self.people = {p.id: p for p in people}
        self.father_edges = list(father_edges)  # (parent_id, child_id)
        self.mother_edges = list(mother_edges)

    def father_of(self, child_id: int) -> Optional[int]:
        """Return the father's id, or None."""
        for parent, child in self.father_edges:
            if child == child_id:
                return parent
        return None

    def mother_of(self, child_id: int) -> Optional[int]:
        """Return the mother's id, or None."""
        for parent, child in self.mother_edges:
            if child == child_id:
                return parent
        return None

    def children_of(self, parent_id: int) -> list:
        """Return list of children ids."""
        children = set()
        for parent, child in self.father_edges:
            if parent == parent_id:
                children.add(child)
        for parent, child in self.mother_edges:
            if parent == parent_id:
                children.add(child)
        return sorted(children)

    def siblings_of(self, person_id: int) -> list:
        """Return list of sibling ids (sharing at least one parent)."""
        siblings = set()
        father = self.father_of(person_id)
        mother = self.mother_of(person_id)
        if father is not None:
            siblings.update(self.children_of(father))
        if mother is not None:
            siblings.update(self.children_of(mother))
        siblings.discard(person_id)
        return sorted(siblings)

    def to_character_states(self) -> dict:
        """Return {person_id: CharacterState} for all people."""
        return {pid: p.to_character_state() for pid, p in self.people.items()}

    def print_tree(self):
        """Print a text representation showing generations and relationships."""
        # Group by generation (based on age)
        people_sorted = sorted(self.people.values(), key=lambda p: -p.age)

        # Find root parents (no incoming parent edges)
        all_children = set()
        for _, child in self.father_edges:
            all_children.add(child)
        for _, child in self.mother_edges:
            all_children.add(child)
        roots = [p for p in people_sorted if p.id not in all_children]

        # Build generations via BFS
        generations = []
        visited = set()
        current_gen = [p.id for p in roots]

        while current_gen:
            gen_people = []
            next_gen = []
            for pid in current_gen:
                if pid in visited:
                    continue
                visited.add(pid)
                gen_people.append(pid)
                next_gen.extend(self.children_of(pid))
            if gen_people:
                generations.append(gen_people)
            current_gen = list(dict.fromkeys(next_gen))  # dedupe, preserve order

        # Add any unvisited people
        unvisited = [p.id for p in people_sorted if p.id not in visited]
        if unvisited:
            generations.append(unvisited)

        print("\n=== Family Tree ===\n")
        for gen_idx, gen in enumerate(generations):
            print(f"Generation {gen_idx + 1}:")
            for pid in gen:
                p = self.people[pid]
                father = self.father_of(pid)
                mother = self.mother_of(pid)
                parents_str = ""
                if father is not None or mother is not None:
                    parts = []
                    if father is not None:
                        parts.append(f"father=P{father}")
                    if mother is not None:
                        parts.append(f"mother=P{mother}")
                    parents_str = f" [{', '.join(parts)}]"

                children = self.children_of(pid)
                children_str = ""
                if children:
                    children_str = f" -> children: {', '.join(f'P{c}' for c in children)}"

                print(f"  P{pid}: {p.gender}, age {p.age}, "
                      f"hair={p.hair_color}, skin={p.skin_tint}, "
                      f"eyes={p.eye_color}{parents_str}{children_str}")
            print()


def _hair_weight(src_val, tgt_val):
    """Weight function for hair color inheritance."""
    if src_val == tgt_val:
        return 5.0
    if HAIR_GROUPS.get(src_val) == HAIR_GROUPS.get(tgt_val):
        return 3.0
    return 1.0


def _skin_weight(src_val, tgt_val):
    """Weight function for skin tint inheritance."""
    diff = abs(src_val - tgt_val)
    return {0: 5, 1: 3, 2: 2, 3: 1.5}.get(diff, 1.0)


def _eye_weight(src_val, tgt_val):
    """Weight function for eye color inheritance."""
    if src_val == tgt_val:
        return 4.0
    return 1.0


def _categorical_inherit_weight(src_val, tgt_val):
    """Weight function for simple categorical trait inheritance."""
    if src_val == tgt_val:
        return 3.0
    return 1.0


def _age_predicate(parent_age, child_age):
    """Parent must be 18-50 years older than child."""
    diff = parent_age - child_age
    return 18 <= diff <= 50


def build_family_wfc(num_people: int) -> tuple:
    """Build a WFC graph configured for family tree generation.

    Returns (graph, constraints, property_specs).
    """
    property_specs = {
        "age": frozenset(range(0, 101)),
        "gender": GENDERS,
        "hair_color": HAIR_COLORS,
        "skin_tint": SKIN_TINTS,
        "eye_color": EYE_COLORS,
        "eye_size": EYE_SIZES,
        "eyebrow_style": EYEBROW_STYLES,
        "nose_style": NOSE_STYLES,
    }

    edge_labels = ["father_of", "mother_of"]

    graph = WFCGraph(num_people, property_specs, edge_labels)

    constraints = []

    # No self-edges
    constraints.append(NoSelfEdgeConstraint())

    # Father must be male
    constraints.append(EdgeConstraint(
        label="father_of",
        source_prop="gender",
        target_prop="gender",
        predicate=lambda sv, tv: sv == "male",
    ))

    # Mother must be female
    constraints.append(EdgeConstraint(
        label="mother_of",
        source_prop="gender",
        target_prop="gender",
        predicate=lambda sv, tv: sv == "female",
    ))

    # Parent-child age constraint for father
    constraints.append(EdgeConstraint(
        label="father_of",
        source_prop="age",
        target_prop="age",
        predicate=_age_predicate,
    ))

    # Parent-child age constraint for mother
    constraints.append(EdgeConstraint(
        label="mother_of",
        source_prop="age",
        target_prop="age",
        predicate=_age_predicate,
    ))

    # At most 1 incoming father_of per person
    constraints.append(CardinalityConstraint(
        label="father_of",
        direction="incoming",
        min_count=0,
        max_count=1,
    ))

    # At most 1 incoming mother_of per person
    constraints.append(CardinalityConstraint(
        label="mother_of",
        direction="incoming",
        min_count=0,
        max_count=1,
    ))

    # Soft constraints for genetic inheritance
    for label in ["father_of", "mother_of"]:
        constraints.append(SoftConstraint(
            label=label,
            source_prop="hair_color",
            weight_fn=_hair_weight,
        ))
        constraints.append(SoftConstraint(
            label=label,
            source_prop="skin_tint",
            weight_fn=_skin_weight,
        ))
        constraints.append(SoftConstraint(
            label=label,
            source_prop="eye_color",
            weight_fn=_eye_weight,
        ))
        constraints.append(SoftConstraint(
            label=label,
            source_prop="eye_size",
            weight_fn=_categorical_inherit_weight,
        ))
        constraints.append(SoftConstraint(
            label=label,
            source_prop="eyebrow_style",
            weight_fn=_categorical_inherit_weight,
        ))
        constraints.append(SoftConstraint(
            label=label,
            source_prop="nose_style",
            weight_fn=_categorical_inherit_weight,
        ))

    return graph, constraints


def _seed_family_structure(solver: WFCSolver, num_people: int,
                           rng: random.Random):
    """Pre-seed family structure with some genders, ages, and edges.

    Spreads people across generations and attempts to establish
    parent-child edges. Catches contradictions gracefully.
    """
    if num_people < 2:
        return

    # Assign rough generational ages
    # Split people into ~3 generations
    gen_size = max(2, num_people // 3)
    generations = []
    idx = 0
    while idx < num_people:
        end = min(idx + gen_size, num_people)
        generations.append(list(range(idx, end)))
        idx = end

    # Assign ages per generation
    age_ranges = [(50, 80), (25, 45), (0, 20)]
    for gen_idx, gen in enumerate(generations):
        if gen_idx >= len(age_ranges):
            age_range = age_ranges[-1]
        else:
            age_range = age_ranges[gen_idx]
        for person_id in gen:
            age = rng.randint(age_range[0], age_range[1])
            try:
                solver.observe(person_id, "age", age)
            except ContradictionError:
                pass

    # Assign genders (roughly balanced)
    people_order = list(range(num_people))
    rng.shuffle(people_order)
    for i, person_id in enumerate(people_order):
        gender = "male" if i % 2 == 0 else "female"
        try:
            solver.observe(person_id, "gender", gender)
        except ContradictionError:
            pass

    # Try to establish parent-child edges between generations
    for gen_idx in range(len(generations) - 1):
        parents = generations[gen_idx]
        children = generations[gen_idx + 1] if gen_idx + 1 < len(generations) else []

        for child in children:
            # Try to find a father and mother from parent generation
            rng.shuffle(parents)
            for parent in parents:
                try:
                    parent_gender_dom = solver.graph.domain(parent, "gender")
                    if parent_gender_dom.is_collapsed():
                        g = parent_gender_dom.get_value()
                        if g == "male":
                            solver.establish_edge(parent, child, "father_of")
                            break
                except ContradictionError:
                    continue

            rng.shuffle(parents)
            for parent in parents:
                try:
                    parent_gender_dom = solver.graph.domain(parent, "gender")
                    if parent_gender_dom.is_collapsed():
                        g = parent_gender_dom.get_value()
                        if g == "female":
                            solver.establish_edge(parent, child, "mother_of")
                            break
                except ContradictionError:
                    continue


def _extract_family_tree(graph: WFCGraph, num_people: int) -> FamilyTree:
    """Extract a FamilyTree from a fully collapsed WFC graph."""
    people = []
    for i in range(num_people):
        people.append(Person(
            id=i,
            age=graph.get_value(i, "age"),
            gender=graph.get_value(i, "gender"),
            hair_color=graph.get_value(i, "hair_color"),
            skin_tint=graph.get_value(i, "skin_tint"),
            eye_color=graph.get_value(i, "eye_color"),
            eye_size=graph.get_value(i, "eye_size"),
            eyebrow_style=graph.get_value(i, "eyebrow_style"),
            nose_style=graph.get_value(i, "nose_style"),
        ))

    father_edges = graph.get_established_edges("father_of")
    mother_edges = graph.get_established_edges("mother_of")

    return FamilyTree(people, father_edges, mother_edges)


def generate_family_tree(num_people: int = 6,
                         seed: Optional[int] = None) -> FamilyTree:
    """Generate a genetically-consistent family tree.

    Args:
        num_people: Number of family members to generate.
        seed: Random seed for reproducibility.

    Returns:
        A FamilyTree with genetically-related members.
    """
    rng = random.Random(seed)

    graph, constraints = build_family_wfc(num_people)
    solver = WFCSolver(
        graph, constraints,
        priority_fn=_collapse_priority,
        max_restarts=100,
        rng=rng,
        epsilon=0.05,
    )

    # Pre-seed family structure
    _seed_family_structure(solver, num_people, rng)

    if not solver.solve():
        raise RuntimeError("Failed to generate family tree after max restarts")

    return _extract_family_tree(graph, num_people)


def _collapse_priority(node: int, prop: str, domain) -> float:
    """Priority function: lower = collapse first."""
    priorities = {
        "gender": 0,
        "age": 1,
        "hair_color": 2,
        "skin_tint": 2,
        "eye_color": 2,
        "eye_size": 2,
        "eyebrow_style": 2,
        "nose_style": 2,
    }
    return priorities.get(prop, 3)


def render_family(tree: FamilyTree, save_path: Optional[str] = None):
    """Render family tree with generational layout and parent-child edges."""
    from averageface import render_superposition
    from PIL import Image, ImageDraw, ImageFont

    THUMB_W, THUMB_H = 150, 193
    LABEL_H = 45
    H_PAD = 30
    V_PAD = 60
    MARGIN = 30

    # --- 1. Build generations via BFS (same logic as print_tree) ---
    people_sorted = sorted(tree.people.values(), key=lambda p: (-p.age, p.id))

    all_children = set()
    for _, child in tree.father_edges:
        all_children.add(child)
    for _, child in tree.mother_edges:
        all_children.add(child)
    roots = [p.id for p in people_sorted if p.id not in all_children]

    generations = []
    visited = set()
    current_gen = list(roots)

    while current_gen:
        gen_people = []
        next_gen = []
        for pid in current_gen:
            if pid in visited:
                continue
            visited.add(pid)
            gen_people.append(pid)
            next_gen.extend(tree.children_of(pid))
        if gen_people:
            generations.append(gen_people)
        current_gen = list(dict.fromkeys(next_gen))

    unvisited = [p.id for p in people_sorted if p.id not in visited]
    if unvisited:
        generations.append(unvisited)

    # --- 2. Render and resize each person's superposition ---
    states = tree.to_character_states()
    images = {}
    for pid in tree.people:
        img = render_superposition(states[pid], max_samples=50)
        images[pid] = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)

    # --- 3. Compute canvas size and positions ---
    row_height = THUMB_H + LABEL_H + V_PAD

    gen_widths = []
    for gen in generations:
        n = len(gen)
        gen_widths.append(n * THUMB_W + (n - 1) * H_PAD)

    canvas_w = max(gen_widths) + 2 * MARGIN
    canvas_h = len(generations) * row_height + MARGIN

    # Position each person: dict[pid] -> (x, y) top-left of thumbnail
    positions = {}
    for gen_idx, gen in enumerate(generations):
        n = len(gen)
        total_w = n * THUMB_W + (n - 1) * H_PAD
        start_x = (canvas_w - total_w) // 2
        y = MARGIN + gen_idx * row_height
        for i, pid in enumerate(gen):
            x = start_x + i * (THUMB_W + H_PAD)
            positions[pid] = (x, y)

    # --- 4. Create canvas, paste thumbnails, draw labels ---
    combined = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(combined)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except (OSError, IOError):
        font = ImageFont.load_default()

    for pid, (x, y) in positions.items():
        combined.paste(images[pid], (x, y), images[pid])
        p = tree.people[pid]
        label1 = f"P{pid}: {p.gender}, {p.age}y"
        label2 = f"{p.hair_color}, skin={p.skin_tint}, eyes={p.eye_color}"
        draw.text((x, y + THUMB_H + 2), label1,
                  fill=(0, 0, 0, 255), font=font)
        draw.text((x, y + THUMB_H + 16), label2,
                  fill=(80, 80, 80, 255), font=font)

    # --- 5. Draw edges from parents to children ---
    for parent_id, child_id in tree.father_edges:
        if parent_id in positions and child_id in positions:
            px, py = positions[parent_id]
            cx, cy = positions[child_id]
            start = (px + THUMB_W // 2, py + THUMB_H + LABEL_H)
            end = (cx + THUMB_W // 2, cy)
            draw.line([start, end], fill=(50, 80, 200, 255), width=2)

    for parent_id, child_id in tree.mother_edges:
        if parent_id in positions and child_id in positions:
            px, py = positions[parent_id]
            cx, cy = positions[child_id]
            start = (px + THUMB_W // 2, py + THUMB_H + LABEL_H)
            end = (cx + THUMB_W // 2, cy)
            draw.line([start, end], fill=(200, 50, 80, 255), width=2)

    if save_path:
        combined.save(save_path)
        print(f"Saved family visualization to: {save_path}")

    return combined


def main():
    parser = argparse.ArgumentParser(
        description="Family Tree Generator using WFC + AverageFace"
    )
    parser.add_argument("-n", type=int, default=6,
                        help="Number of family members (default: 6)")
    parser.add_argument("-s", "--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    parser.add_argument("--render", action="store_true",
                        help="Show matplotlib visualization")
    parser.add_argument("--save", type=str, default=None,
                        help="Save combined image to file")
    args = parser.parse_args()

    print(f"Generating family tree with {args.n} people...")
    if args.seed is not None:
        print(f"Using seed: {args.seed}")

    tree = generate_family_tree(num_people=args.n, seed=args.seed)
    tree.print_tree()

    if args.save:
        render_family(tree, save_path=args.save)

    if args.render:
        import matplotlib
        for backend in ['TkAgg', 'Qt5Agg', 'GTK3Agg', 'Agg']:
            try:
                matplotlib.use(backend)
                break
            except Exception:
                continue
        import matplotlib.pyplot as plt

        img = render_family(tree)
        fig, ax = plt.subplots(1, 1, figsize=(12, 8))
        ax.imshow(img)
        ax.set_title("Family Tree - AverageFace Characters")
        ax.axis("off")
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
