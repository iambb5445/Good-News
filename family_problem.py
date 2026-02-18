"""
Property-based family tree generator using the generic WFC engine.

Models N people with gender, father, and mother as WFC node properties.
Ages are assigned post-solve via topological sort over the parent-child DAG.
"""

import argparse
import string
from collections import deque
from random import Random

from wfc import (
    WFCGraph, WFCSolver, Constraint, PropagationContext,
    ContradictionError, EdgeState,
)

NONE_PARENT = -1
MIN_PARENT_AGE = 18
MIN_AGE = 0
MAX_AGE = 100
MAX_CHAIN = MAX_AGE // MIN_PARENT_AGE  # Max parent-child edges (5 for 100/18)
NONE_PARENT_WEIGHT = 0.1  # Low = prefer actual parents over orphan (per plan).


class FamilyConstraint(Constraint):
    """Enforces all family-specific rules as a single constraint.

    Rules:
    - Fathers must be male, mothers must be female.
    - A person's father and mother must be different people.
    - No cycles in the ancestor graph.
    """

    def __init__(self, n: int):
        self.n = n

    def initial_propagate(self, ctx: PropagationContext):
        pass  # Self-exclusion handled at graph construction time.

    def propagate(self, ctx: PropagationContext, node: int, prop: str):
        g = ctx.graph

        if prop == "gender":
            domain = g.domain(node, "gender")
            # If male is ruled out, this node can't be anyone's father.
            if "male" not in domain:
                for other in range(self.n):
                    if other == node:
                        continue
                    other_father = g.domain(other, "father")
                    if node in other_father:
                        ctx.restrict_domain(
                            other, "father",
                            other_father.values - frozenset({node})
                        )
            # If female is ruled out, this node can't be anyone's mother.
            if "female" not in domain:
                for other in range(self.n):
                    if other == node:
                        continue
                    other_mother = g.domain(other, "mother")
                    if node in other_mother:
                        ctx.restrict_domain(
                            other, "mother",
                            other_mother.values - frozenset({node})
                        )

        elif prop == "father":
            father_dom = g.domain(node, "father")
            if father_dom.is_collapsed():
                b = father_dom.get_value()
                if b != NONE_PARENT:
                    # Father must be male.
                    ctx.restrict_domain(b, "gender", frozenset({"male"}))
                    # Father != mother.
                    mother_dom = g.domain(node, "mother")
                    if b in mother_dom:
                        ctx.restrict_domain(
                            node, "mother",
                            mother_dom.values - frozenset({b})
                        )
                    # Cycle check: node must not be an ancestor of b.
                    if node in self._get_ancestors(g, b):
                        raise ContradictionError(
                            f"Cycle: node {node} is ancestor of its father {b}"
                        )
                    # Prevent reverse parentage (b can't have node as parent).
                    b_father = g.domain(b, "father")
                    if node in b_father:
                        ctx.restrict_domain(
                            b, "father",
                            b_father.values - frozenset({node})
                        )
                    b_mother = g.domain(b, "mother")
                    if node in b_mother:
                        ctx.restrict_domain(
                            b, "mother",
                            b_mother.values - frozenset({node})
                        )

        elif prop == "mother":
            mother_dom = g.domain(node, "mother")
            if mother_dom.is_collapsed():
                b = mother_dom.get_value()
                if b != NONE_PARENT:
                    # Mother must be female.
                    ctx.restrict_domain(b, "gender", frozenset({"female"}))
                    # Father != mother.
                    father_dom = g.domain(node, "father")
                    if b in father_dom:
                        ctx.restrict_domain(
                            node, "father",
                            father_dom.values - frozenset({b})
                        )
                    # Cycle check: node must not be an ancestor of b.
                    if node in self._get_ancestors(g, b):
                        raise ContradictionError(
                            f"Cycle: node {node} is ancestor of its mother {b}"
                        )
                    # Prevent reverse parentage.
                    b_father = g.domain(b, "father")
                    if node in b_father:
                        ctx.restrict_domain(
                            b, "father",
                            b_father.values - frozenset({node})
                        )
                    b_mother = g.domain(b, "mother")
                    if node in b_mother:
                        ctx.restrict_domain(
                            b, "mother",
                            b_mother.values - frozenset({node})
                        )

    def propagate_edge(self, ctx: PropagationContext, src: int, tgt: int,
                       label: str, new_state: EdgeState):
        pass  # No edges used.

    @staticmethod
    def _get_ancestors(graph, node):
        """BFS upward through collapsed father/mother links.

        Returns set including node itself (used for cycle detection).
        """
        visited = {node}
        queue = deque([node])
        while queue:
            current = queue.popleft()
            for prop in ("father", "mother"):
                dom = graph.domain(current, prop)
                if dom.is_collapsed():
                    parent = dom.get_value()
                    if parent != NONE_PARENT and parent not in visited:
                        visited.add(parent)
                        queue.append(parent)
        return visited


def build_family_problem(n, rng):
    """Build a WFCGraph for the family problem with N people."""
    property_specs = {
        "gender": frozenset({"male", "female"}),
        "father": frozenset({NONE_PARENT} | set(range(n))),
        "mother": frozenset({NONE_PARENT} | set(range(n))),
    }
    graph = WFCGraph(n, property_specs, edge_labels=[], edge_pairs=[])

    # Per-node: exclude self from father/mother, set NONE soft weight.
    for i in range(n):
        graph.restrict_domain(i, "father",
                              frozenset({NONE_PARENT} | (set(range(n)) - {i})))
        graph.restrict_domain(i, "mother",
                              frozenset({NONE_PARENT} | (set(range(n)) - {i})))
        graph.set_soft_weight(i, "father", NONE_PARENT, NONE_PARENT_WEIGHT)
        graph.set_soft_weight(i, "mother", NONE_PARENT, NONE_PARENT_WEIGHT)

    constraints = [FamilyConstraint(n)]
    return graph, constraints


def solve_family(n, rng):
    """Solve the family problem and return a list of person dicts."""
    graph, constraints = build_family_problem(n, rng)
    solver = WFCSolver(graph, constraints, max_restarts=100, rng=rng)
    if not solver.solve():
        raise RuntimeError("Failed to solve family problem after 100 restarts")

    people = []
    for i in range(n):
        father = graph.get_value(i, "father")
        mother = graph.get_value(i, "mother")
        people.append({
            "id": i,
            "gender": graph.get_value(i, "gender"),
            "father": father if father != NONE_PARENT else None,
            "mother": mother if mother != NONE_PARENT else None,
        })

    assign_ages(people, rng)
    for p in people:
        p["name"] = get_random_name(rng)

    return people


def assign_ages(people, rng):
    """Assign ages via topological sort (parents before children).

    Uses a dynamic age gap so all ages fit in [MIN_AGE, MAX_AGE] regardless
    of tree depth. For chains of depth ≤ MAX_CHAIN the gap equals
    MIN_PARENT_AGE (18 years); deeper chains use a proportionally smaller gap.
    """
    n = len(people)
    children_of = {i: [] for i in range(n)}
    in_degree = {i: 0 for i in range(n)}
    for p in people:
        for parent_id in (p["father"], p["mother"]):
            if parent_id is not None:
                children_of[parent_id].append(p["id"])
                in_degree[p["id"]] += 1

    # Kahn's algorithm for topological sort (parents first).
    queue = deque([i for i in range(n) if in_degree[i] == 0])
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for child in children_of[node]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Compute max descendant depth bottom-up.
    depth_below = {i: 0 for i in range(n)}
    for node in reversed(order):
        for child in children_of[node]:
            depth_below[node] = max(depth_below[node], 1 + depth_below[child])

    max_depth = max(depth_below.values()) if n else 0
    # Choose largest age gap that fits all generations in [0, MAX_AGE].
    age_gap = min(MIN_PARENT_AGE, MAX_AGE // (max_depth + 1)) if max_depth else MIN_PARENT_AGE
    age_gap = max(age_gap, 1)

    # Assign ages top-down.
    ages = {}
    for node in order:
        p = people[node]
        min_age = depth_below[node] * age_gap
        max_age = MAX_AGE
        for parent_id in (p["father"], p["mother"]):
            if parent_id is not None and parent_id in ages:
                max_age = min(max_age, ages[parent_id] - age_gap)
        max_age = max(max_age, min_age)
        ages[node] = rng.randint(min_age, max_age)

    for p in people:
        p["age"] = ages[p["id"]]


def get_random_name(rnd):
    """Generate a random name (from family.py)."""
    vowels = list("aeiou")
    consonants = [s for s in string.ascii_lowercase if s not in vowels]
    vclusters = vowels + ["ae", "ou", "ea", "ai", "io", "ui"]
    cclusters = consonants + ["br", "cr", "dr", "gr", "pr", "fr", "st", "tr"]
    pattern = rnd.choice([
        [vowels, consonants, vowels],
        [vowels, consonants, vclusters, consonants],
        [cclusters, vclusters, consonants],
        [cclusters, vclusters, consonants, vowels],
        [cclusters, vclusters, consonants, vowels, consonants],
    ])
    return ''.join([rnd.choice(p) for p in pattern])


def get_tree(people, rnd):
    """Render an ASCII family tree (adapted from family.py)."""
    n = len(people)
    by_id = {p["id"]: p for p in people}

    # Build trios: (father, mother, child).
    trios = []
    for p in people:
        if p["father"] is not None and p["mother"] is not None:
            trios.append((p["father"], p["mother"], p["id"]))

    # Horizontal ordering via iterative relaxation.
    horizontal_score = [float(i) for i in range(n)]
    for _ in range(1000 * n):
        for father, mother, child in trios:
            f_score = horizontal_score[father]
            m_score = horizontal_score[mother]
            c_score = horizontal_score[child]
            lo, hi = min(f_score, m_score), max(f_score, m_score)
            if c_score > hi or c_score < lo:
                horizontal_score[child] = (
                    rnd.random() * abs(f_score - m_score)
                    + min(f_score, m_score)
                )

    horizontal_order = sorted(range(n), key=lambda i: horizontal_score[i])

    # Vertical ordering: oldest first.
    sorted_ids = sorted(range(n), key=lambda i: by_id[i]["age"], reverse=True)
    vertical_order = {}
    for pid in sorted_ids:
        p = by_id[pid]
        father_vo = vertical_order.get(p["father"], -1) if p["father"] is not None else -1
        mother_vo = vertical_order.get(p["mother"], -1) if p["mother"] is not None else -1
        vertical_order[pid] = max(father_vo, mother_vo) + 1

    char_per_person = len(str(n - 1)) + 2
    lines = [[" " for _ in range(char_per_person * n)] for _ in range(n)]

    # Place IDs on the grid.
    positions = []
    vpos = {}
    hpos = {}
    for index, pid in enumerate(horizontal_order):
        positions.append((vertical_order[pid], index, pid))
    positions.sort()
    for line_id, (_, hindex, pid) in enumerate(positions):
        hoffset = hindex * char_per_person + 1
        id_str = str(pid)
        for i in range(len(id_str)):
            lines[line_id][hoffset + i] = id_str[i]
        vpos[pid] = line_id
        hpos[pid] = hoffset

    # Draw connections.
    def add_char(x, y, char):
        old = lines[x][y]
        values = list(set([old, char]))
        new = "?"
        if len(values) == 1:
            new = values[0]
        if " " in values:
            new = char
        if "┼" in values:
            new = "┼"
        if "─" in values:
            if "┘" in values or "└" in values or "┴" in values:
                new = "┴"
            if "┬" in values:
                new = "┬"
            if "│" in values or "┤" in values or "├" in values:
                new = "┼"
        if "│" in values:
            if "└" in values or "├" in values:
                new = "├"
            if "┘" in values or "┤" in values:
                new = "┤"
            if "┴" in values or "┬" in values:
                new = "┼"
        if "┴" in values:
            if "┘" in values or "└" in values:
                new = "┴"
            if "┤" in values or "├" in values or "┬" in values:
                new = "┼"
        if "┘" in values:
            if "└" in values:
                new = "┴"
            if "┤" in values:
                new = "┤"
            if "├" in values or "┬" in values:
                new = "┼"
        if "└" in values:
            if "┤" in values or "┬" in values:
                new = "┼"
            if "├" in values:
                new = "├"
        if "┤" in values:
            if "├" in values or "┬" in values:
                new = "┼"
        if "├" in values and "┬" in values:
            new = "┼"
        lines[x][y] = new

    for father, mother, child in trios:
        higher = mother if vpos[mother] < vpos[father] else father
        lower = mother if higher == father else father
        hmin = (
            (hpos[father] + len(str(father)))
            if hpos[father] < hpos[mother]
            else (hpos[mother] + len(str(mother)))
        )
        hmax = hpos[father] if hpos[father] > hpos[mother] else hpos[mother]
        for i in range(hmin, hmax):
            add_char(vpos[lower], i, "─")
        if hpos[higher] < hpos[lower]:
            descend_hpos = hpos[higher] + len(str(higher)) - 1
            add_char(vpos[lower], descend_hpos, "└")
        else:
            descend_hpos = hpos[higher]
            add_char(vpos[lower], descend_hpos, "┘")
        for i in range(vpos[higher] + 1, vpos[lower]):
            add_char(i, descend_hpos, "│")
        add_char(vpos[lower], hpos[child], "┬")
        for i in range(vpos[lower] + 1, vpos[child]):
            add_char(i, hpos[child], "│")

    return "\n".join(["".join(char for char in line) for line in lines])


def print_results(people):
    """Print per-person details matching family.py's format."""
    for p in people:
        print(f"{p['id']}: {p['name']}")
        print(f"father: {p['father']}")
        print(f"mother: {p['mother']}")
        print(f"gender: {p['gender']}")
        print(f"age: {p['age']}")


def main():
    parser = argparse.ArgumentParser(
        description="Property-based family tree generator using WFC"
    )
    parser.add_argument("-n", type=int, default=20, help="Number of people")
    parser.add_argument("-s", "--seed", type=int, default=None,
                        help="Random seed")
    args = parser.parse_args()

    rng = Random(args.seed)
    people = solve_family(args.n, rng)
    print_results(people)
    print()
    print(get_tree(people, rng))


if __name__ == "__main__":
    main()
