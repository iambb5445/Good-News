#!/usr/bin/env python3
"""
Growing-graph WFC: graph starts empty and gains one phantom node at all times.

Materializing (spawning) the phantom makes it concrete and adds a fresh
phantom, enabling potentially infinite graphs.

Re-exports all public symbols from wfc.py for callers.
"""

import random
from typing import Callable, Optional

from wfc import (
    Domain, EdgeState, ContradictionError, PropagationContext,
    Constraint, NodeConstraint, EdgeConstraint, CardinalityConstraint,
    SoftConstraint, NoSelfEdgeConstraint,
)

__all__ = [
    # Re-exported from wfc.py
    "Domain", "EdgeState", "ContradictionError", "PropagationContext",
    "Constraint", "NodeConstraint", "EdgeConstraint", "CardinalityConstraint",
    "SoftConstraint", "NoSelfEdgeConstraint",
    # New
    "GrowingWFCGraph", "GrowingWFCSolver",
]


# ---------------------------------------------------------------------------
# GrowingWFCGraph
# ---------------------------------------------------------------------------

class GrowingWFCGraph:
    """WFC graph that starts empty and grows via add_node().

    Identical interface to WFCGraph so existing constraints work unchanged.
    EdgeConstraint.initial_propagate accesses _edges, _adj_in, _adj_out
    directly — these are exposed with the same structure as WFCGraph.
    """

    def __init__(self, property_specs: dict, edge_labels: list):
        self.property_specs = property_specs   # name -> frozenset of values
        self.edge_labels = list(edge_labels)
        self._num_nodes = 0
        self._domains = []        # list[dict[str, Domain]]
        self._edges = {}          # (src, tgt, label) -> EdgeState
        self._adj_out = []        # list[dict[label, set[tgt]]]
        self._adj_in = []         # list[dict[label, set[src]]]
        self._soft_weights = {}   # (node, prop, value) -> float

    @property
    def num_nodes(self) -> int:
        return self._num_nodes

    def add_node(self) -> int:
        """Add a new node with full-domain properties and POTENTIAL edges to
        all existing nodes (both directions, all labels). Returns the new ID."""
        new_id = self._num_nodes

        # Initialize domains for new node
        self._domains.append(
            {prop: Domain(values)
             for prop, values in self.property_specs.items()}
        )

        # Initialize adjacency structures for new node
        self._adj_out.append({label: set() for label in self.edge_labels})
        self._adj_in.append({label: set() for label in self.edge_labels})

        # Add POTENTIAL edges between new node and every existing node
        for existing in range(self._num_nodes):
            for label in self.edge_labels:
                # new_id -> existing
                key = (new_id, existing, label)
                self._edges[key] = EdgeState.POTENTIAL
                self._adj_out[new_id][label].add(existing)
                self._adj_in[existing][label].add(new_id)
                # existing -> new_id
                key = (existing, new_id, label)
                self._edges[key] = EdgeState.POTENTIAL
                self._adj_out[existing][label].add(new_id)
                self._adj_in[new_id][label].add(existing)

        self._num_nodes += 1
        return new_id

    # -----------------------------------------------------------------------
    # Core state access (same interface as WFCGraph)
    # -----------------------------------------------------------------------

    def domain(self, node: int, prop: str) -> Domain:
        return self._domains[node][prop]

    def edge_state(self, src: int, tgt: int, label: str) -> EdgeState:
        return self._edges.get((src, tgt, label), EdgeState.ELIMINATED)

    def restrict_domain(self, node: int, prop: str, allowed) -> bool:
        """Intersect domain with allowed values. Returns True if changed."""
        old = self._domains[node][prop]
        if not isinstance(allowed, frozenset):
            allowed = frozenset(allowed)
        new_dom = old.restrict(allowed)
        if new_dom == old:
            return False
        if len(new_dom) == 0:
            raise ContradictionError(
                f"Domain of node {node} property '{prop}' became empty"
            )
        self._domains[node][prop] = new_dom
        return True

    def set_edge_state(self, src: int, tgt: int, label: str, state: EdgeState):
        """Update edge state. Raises on invalid transitions."""
        key = (src, tgt, label)
        if key not in self._edges:
            if state == EdgeState.ELIMINATED:
                return  # Non-existent edge is already effectively eliminated
            raise ContradictionError(
                f"Edge ({src},{tgt},{label}) does not exist in graph"
            )
        current = self._edges[key]
        if current == state:
            return
        if current != EdgeState.POTENTIAL:
            raise ContradictionError(
                f"Cannot transition edge ({src},{tgt},{label}) from "
                f"{current.value} to {state.value}"
            )
        self._edges[key] = state

    def get_established_edges(self, label: str) -> list:
        """Return list of (src, tgt) for established edges with given label."""
        return [
            (s, t) for (s, t, l), st in self._edges.items()
            if l == label and st == EdgeState.ESTABLISHED
        ]

    def incoming_edges(self, node: int, label: str,
                       states: Optional[set] = None) -> list:
        """Return (src, tgt) pairs for incoming edges to node."""
        if states is None:
            states = {EdgeState.POTENTIAL, EdgeState.ESTABLISHED}
        result = []
        for src in self._adj_in[node][label]:
            key = (src, node, label)
            if key in self._edges and self._edges[key] in states:
                result.append((src, node))
        return result

    def outgoing_edges(self, node: int, label: str,
                       states: Optional[set] = None) -> list:
        """Return (src, tgt) pairs for outgoing edges from node."""
        if states is None:
            states = {EdgeState.POTENTIAL, EdgeState.ESTABLISHED}
        result = []
        for tgt in self._adj_out[node][label]:
            key = (node, tgt, label)
            if key in self._edges and self._edges[key] in states:
                result.append((node, tgt))
        return result

    def is_collapsed(self, node: int) -> bool:
        """Check if all properties of a node are collapsed."""
        return all(d.is_collapsed() for d in self._domains[node].values())

    def is_fully_collapsed(self) -> bool:
        """Check if all nodes are collapsed."""
        return all(self.is_collapsed(n) for n in range(self._num_nodes))

    def get_value(self, node: int, prop: str):
        """Get collapsed value. Raises if not collapsed."""
        return self._domains[node][prop].get_value()

    def set_soft_weight(self, node: int, prop: str, value, weight: float):
        """Set soft weight for a specific (node, prop, value)."""
        self._soft_weights[(node, prop, value)] = weight

    def get_soft_weight(self, node: int, prop: str, value) -> float:
        """Get soft weight, default 1.0."""
        return self._soft_weights.get((node, prop, value), 1.0)

    def snapshot(self):
        """Create a snapshot of domains, edges, and soft weights."""
        domains_copy = [
            {p: Domain(d.values) for p, d in nd.items()}
            for nd in self._domains
        ]
        return (domains_copy, dict(self._edges), dict(self._soft_weights))

    def restore(self, snap):
        """Restore domains, edges, and soft weights from a snapshot.
        Topology (adjacency) is not restored — nodes are never removed.
        """
        domains_data, edges_data, weights_data = snap
        self._domains = [
            {p: Domain(d.values) for p, d in nd.items()}
            for nd in domains_data
        ]
        self._edges = dict(edges_data)
        self._soft_weights = dict(weights_data)


# ---------------------------------------------------------------------------
# GrowingWFCSolver
# ---------------------------------------------------------------------------

class GrowingWFCSolver:
    """Step-by-step WFC solver on a growing graph.

    One 'phantom' node exists at all times. spawn() materializes the current
    phantom as a concrete node and adds a fresh phantom, enabling potentially
    infinite graphs. Solving is step-by-step via step_auto(), not run-to-
    completion, so callers can capture frames between steps.
    """

    def __init__(self, property_specs: dict, edge_labels: list,
                 constraints: list,
                 rng: random.Random = None,
                 priority_fn: Callable = None):
        self._graph = GrowingWFCGraph(property_specs, edge_labels)
        self._constraints = constraints
        self._rng = rng or random.Random()
        self._priority_fn = priority_fn or (lambda n, p, d: d.entropy())
        self._ctx = PropagationContext(self._graph)
        self._concrete_ids: list[int] = []
        self._phantom_id: Optional[int] = None
        self._add_phantom()   # graph starts with one phantom

    @property
    def phantom_id(self) -> int:
        """Current phantom node ID."""
        return self._phantom_id

    @property
    def concrete_ids(self) -> list:
        """Concrete node IDs in spawn order (copy)."""
        return list(self._concrete_ids)

    @property
    def graph(self) -> GrowingWFCGraph:
        return self._graph

    def spawn(self) -> int:
        """Materialize the current phantom as a concrete node, add fresh phantom.

        Returns the newly-concrete node's ID.
        """
        concrete_id = self._phantom_id
        self._concrete_ids.append(concrete_id)
        self._add_phantom()
        return concrete_id

    def observe(self, node_id: int, prop: str, value):
        """Fix a node property to a specific value and propagate."""
        self._ctx.restrict_domain(node_id, prop, frozenset({value}))
        self._propagate()

    def observe_edge(self, src: int, tgt: int, label: str, state: EdgeState):
        """Set an edge state and propagate."""
        self._ctx.set_edge_state(src, tgt, label, state)
        self._propagate()

    def step_auto(self, include_phantom: bool = False):
        """Collapse one property on the best-priority uncollapsed node.

        Candidates: concrete nodes (+ phantom if include_phantom=True).
        Selects (node, prop) with lowest priority_fn value; ties broken by
        lowest entropy, then random shuffle.

        Returns (node_id, prop, value) or None if all candidates are collapsed.
        """
        candidates = list(self._concrete_ids)
        if include_phantom and self._phantom_id is not None:
            candidates.append(self._phantom_id)

        # Pass 1: find minimum priority across all uncollapsed (node, prop)
        best_priority = float("inf")
        for node_id in candidates:
            for prop in self._graph.property_specs:
                dom = self._graph.domain(node_id, prop)
                if dom.is_collapsed():
                    continue
                p = self._priority_fn(node_id, prop, dom)
                if p < best_priority:
                    best_priority = p

        if best_priority == float("inf"):
            return None  # all collapsed

        # Pass 2: collect (node, prop, entropy) at best_priority
        tied = []
        for node_id in candidates:
            for prop in self._graph.property_specs:
                dom = self._graph.domain(node_id, prop)
                if dom.is_collapsed():
                    continue
                if self._priority_fn(node_id, prop, dom) == best_priority:
                    tied.append((node_id, prop, dom.entropy()))

        # Sort by entropy (lowest = most constrained first)
        tied.sort(key=lambda x: x[2])
        min_entropy = tied[0][2]
        candidates_final = [(n, p) for n, p, e in tied if e == min_entropy]
        self._rng.shuffle(candidates_final)
        node_id, prop = candidates_final[0]

        # Weighted random value selection
        dom = self._graph.domain(node_id, prop)
        values = list(dom)
        weights = [self._graph.get_soft_weight(node_id, prop, v)
                   for v in values]

        combined = list(zip(values, weights))
        self._rng.shuffle(combined)

        total = sum(w for _, w in combined)
        if total > 0:
            r = self._rng.random() * total
            cumulative = 0.0
            chosen = combined[0][0]
            for v, w in combined:
                cumulative += w
                if r <= cumulative:
                    chosen = v
                    break
        else:
            chosen = combined[0][0]

        self._ctx.restrict_domain(node_id, prop, frozenset({chosen}))
        self._propagate()
        return (node_id, prop, chosen)

    def is_concrete_collapsed(self) -> bool:
        """True if all concrete node properties are collapsed.
        Vacuously True when there are no concrete nodes.
        """
        return all(
            all(self._graph.domain(n, prop).is_collapsed()
                for prop in self._graph.property_specs)
            for n in self._concrete_ids
        )

    def resolve_concrete_edges(self):
        """Resolve remaining POTENTIAL edges between concrete nodes.

        Checks EdgeConstraint predicates against collapsed values; invalid
        edges are eliminated. Then eliminates all remaining POTENTIAL edges
        between concrete nodes (matching WFCSolver._resolve_edges logic,
        restricted to concrete-only pairs).
        """
        g = self._graph
        concrete_set = set(self._concrete_ids)

        # Collect POTENTIAL edges between concrete nodes
        potential = [
            (src, tgt, label)
            for (src, tgt, label), state in list(g._edges.items())
            if state == EdgeState.POTENTIAL
            and src in concrete_set
            and tgt in concrete_set
        ]

        for src, tgt, label in potential:
            if g._edges.get((src, tgt, label)) != EdgeState.POTENTIAL:
                continue  # resolved by propagation

            # Check EdgeConstraint predicates against collapsed values
            valid = True
            for c in self._constraints:
                if isinstance(c, EdgeConstraint) and c.label == label:
                    try:
                        sv = g.get_value(src, c.source_prop)
                        tv = g.get_value(tgt, c.target_prop)
                        if not c.predicate(sv, tv):
                            valid = False
                            break
                    except ValueError:
                        pass  # not fully collapsed; leave for propagation

            if not valid:
                self._ctx.set_edge_state(src, tgt, label, EdgeState.ELIMINATED)
            else:
                # Check cardinality before establishing
                can_establish = True
                for c in self._constraints:
                    if isinstance(c, CardinalityConstraint) and c.label == label:
                        if c.direction == "incoming":
                            est = g.incoming_edges(
                                tgt, label, {EdgeState.ESTABLISHED})
                            if (c.max_count is not None
                                    and len(est) >= c.max_count):
                                can_establish = False
                        else:
                            est = g.outgoing_edges(
                                src, label, {EdgeState.ESTABLISHED})
                            if (c.max_count is not None
                                    and len(est) >= c.max_count):
                                can_establish = False
                if not can_establish:
                    self._ctx.set_edge_state(
                        src, tgt, label, EdgeState.ELIMINATED)
                else:
                    self._ctx.set_edge_state(
                        src, tgt, label, EdgeState.ESTABLISHED)

        # Eliminate all remaining POTENTIAL edges between concrete nodes
        for src, tgt, label in potential:
            if g._edges.get((src, tgt, label)) == EdgeState.POTENTIAL:
                self._ctx.set_edge_state(src, tgt, label, EdgeState.ELIMINATED)

        self._propagate()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _add_phantom(self):
        """Add a new node as the phantom; re-run all initial constraints."""
        new_id = self._graph.add_node()
        # Re-run initial_propagate for all constraints (idempotent:
        # existing nodes/edges unchanged; new node/edges get constrained)
        for c in self._constraints:
            c.initial_propagate(self._ctx)
        self._propagate()
        self._phantom_id = new_id

    def _propagate(self):
        """Drain propagation queues to fixpoint."""
        ctx = self._ctx
        while ctx.prop_queue or ctx.edge_queue:
            while ctx.prop_queue:
                node, prop = ctx.prop_queue.popleft()
                for c in self._constraints:
                    c.propagate(ctx, node, prop)
            while ctx.edge_queue:
                src, tgt, label, state = ctx.edge_queue.popleft()
                for c in self._constraints:
                    c.propagate_edge(ctx, src, tgt, label, state)
