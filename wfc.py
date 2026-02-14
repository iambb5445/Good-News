"""
Generic graph-based Wave Function Collapse (WFC) engine.

Operates on a graph where nodes have properties with finite domains,
and directed/labeled edges between nodes can be established or eliminated.
Constraints (hard and soft) govern both property values and edge existence.
"""

import math
import random
from abc import ABC, abstractmethod
from collections import deque
from copy import deepcopy
from enum import Enum
from typing import Callable, Optional


class ContradictionError(Exception):
    """Raised when a domain becomes empty or constraints conflict."""
    pass


class EdgeState(Enum):
    POTENTIAL = "potential"
    ESTABLISHED = "established"
    ELIMINATED = "eliminated"


class Domain:
    """Wraps a frozenset of possible values for a node property."""

    __slots__ = ("_values",)

    def __init__(self, values):
        if isinstance(values, frozenset):
            self._values = values
        else:
            self._values = frozenset(values)

    @property
    def values(self) -> frozenset:
        return self._values

    def restrict(self, allowed) -> "Domain":
        """Return a new Domain intersected with allowed values."""
        if isinstance(allowed, frozenset):
            new_vals = self._values & allowed
        else:
            new_vals = self._values & frozenset(allowed)
        return Domain(new_vals)

    def exclude(self, disallowed) -> "Domain":
        """Return a new Domain with disallowed values removed."""
        if isinstance(disallowed, frozenset):
            new_vals = self._values - disallowed
        else:
            new_vals = self._values - frozenset(disallowed)
        return Domain(new_vals)

    def is_collapsed(self) -> bool:
        return len(self._values) == 1

    def entropy(self) -> float:
        n = len(self._values)
        if n <= 1:
            return 0.0
        return math.log2(n)

    def get_value(self):
        """Get the single collapsed value. Raises if not collapsed."""
        if not self.is_collapsed():
            raise ValueError("Domain is not collapsed")
        return next(iter(self._values))

    def __len__(self):
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __contains__(self, item):
        return item in self._values

    def __repr__(self):
        if len(self._values) <= 5:
            return f"Domain({set(self._values)})"
        return f"Domain(|{len(self._values)}|)"

    def __eq__(self, other):
        if isinstance(other, Domain):
            return self._values == other._values
        return NotImplemented

    def __hash__(self):
        return hash(self._values)


class WFCGraphSnapshot:
    """Snapshot of WFCGraph state for backtracking."""

    __slots__ = ("domains", "edges", "soft_weights")

    def __init__(self, domains, edges, soft_weights):
        self.domains = domains
        self.edges = edges
        self.soft_weights = soft_weights


class WFCGraph:
    """Central state container for the WFC solver.

    Initialized with num_nodes, property_specs (name -> frozenset of values),
    and edge_labels. All N*(N-1)*L directed edges start as POTENTIAL.
    """

    def __init__(self, num_nodes: int, property_specs: dict, edge_labels: list):
        self.num_nodes = num_nodes
        self.property_specs = property_specs  # name -> frozenset
        self.edge_labels = list(edge_labels)

        # domains[node][prop] = Domain
        self._domains = []
        for _ in range(num_nodes):
            node_domains = {}
            for prop, values in property_specs.items():
                node_domains[prop] = Domain(values)
            self._domains.append(node_domains)

        # edges[(src, tgt, label)] = EdgeState
        self._edges = {}
        for src in range(num_nodes):
            for tgt in range(num_nodes):
                if src != tgt:
                    for label in edge_labels:
                        self._edges[(src, tgt, label)] = EdgeState.POTENTIAL

        # Soft weights: (node, prop, value) -> float, default 1.0
        self._soft_weights = {}

    def domain(self, node: int, prop: str) -> Domain:
        return self._domains[node][prop]

    def edge_state(self, src: int, tgt: int, label: str) -> EdgeState:
        return self._edges[(src, tgt, label)]

    def restrict_domain(self, node: int, prop: str, allowed) -> bool:
        """Intersect domain with allowed values. Returns True if changed."""
        old = self._domains[node][prop]
        if isinstance(allowed, frozenset):
            new = old.restrict(allowed)
        else:
            new = old.restrict(frozenset(allowed))
        if new == old:
            return False
        if len(new) == 0:
            raise ContradictionError(
                f"Domain of node {node} property '{prop}' became empty"
            )
        self._domains[node][prop] = new
        return True

    def set_edge_state(self, src: int, tgt: int, label: str, state: EdgeState):
        """Update edge state. Raises on invalid transitions."""
        current = self._edges[(src, tgt, label)]
        if current == state:
            return
        # Valid transitions: POTENTIAL -> ESTABLISHED, POTENTIAL -> ELIMINATED
        if current != EdgeState.POTENTIAL:
            raise ContradictionError(
                f"Cannot transition edge ({src},{tgt},{label}) from "
                f"{current.value} to {state.value}"
            )
        self._edges[(src, tgt, label)] = state

    def get_established_edges(self, label: str) -> list:
        """Return list of (src, tgt) for established edges with given label."""
        result = []
        for (s, t, l), state in self._edges.items():
            if l == label and state == EdgeState.ESTABLISHED:
                result.append((s, t))
        return result

    def incoming_edges(self, node: int, label: str,
                       states: Optional[set] = None) -> list:
        """Return (src, tgt) pairs for incoming edges to node."""
        if states is None:
            states = {EdgeState.POTENTIAL, EdgeState.ESTABLISHED}
        result = []
        for src in range(self.num_nodes):
            if src != node:
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
        for tgt in range(self.num_nodes):
            if tgt != node:
                key = (node, tgt, label)
                if key in self._edges and self._edges[key] in states:
                    result.append((node, tgt))
        return result

    def is_collapsed(self, node: int) -> bool:
        """Check if all properties of a node are collapsed."""
        return all(d.is_collapsed() for d in self._domains[node].values())

    def is_fully_collapsed(self) -> bool:
        """Check if all nodes are collapsed."""
        return all(self.is_collapsed(n) for n in range(self.num_nodes))

    def get_value(self, node: int, prop: str):
        """Get collapsed value. Raises if not collapsed."""
        return self._domains[node][prop].get_value()

    def set_soft_weight(self, node: int, prop: str, value, weight: float):
        """Set soft weight for a specific (node, prop, value)."""
        self._soft_weights[(node, prop, value)] = weight

    def get_soft_weight(self, node: int, prop: str, value) -> float:
        """Get soft weight, default 1.0."""
        return self._soft_weights.get((node, prop, value), 1.0)

    def snapshot(self) -> WFCGraphSnapshot:
        """Create a snapshot for backtracking."""
        domains_copy = []
        for node_domains in self._domains:
            domains_copy.append({p: Domain(d.values) for p, d in node_domains.items()})
        edges_copy = dict(self._edges)
        weights_copy = dict(self._soft_weights)
        return WFCGraphSnapshot(domains_copy, edges_copy, weights_copy)

    def restore(self, snap: WFCGraphSnapshot):
        """Restore from a snapshot."""
        self._domains = []
        for node_domains in snap.domains:
            self._domains.append({p: Domain(d.values) for p, d in node_domains.items()})
        self._edges = dict(snap.edges)
        self._soft_weights = dict(snap.soft_weights)


class PropagationContext:
    """Wraps WFCGraph + propagation queues.

    Passed to constraints so they can enqueue domain/edge changes that
    feed back into the propagation loop.
    """

    def __init__(self, graph: WFCGraph):
        self.graph = graph
        self.prop_queue = deque()  # (node, prop)
        self.edge_queue = deque()  # (src, tgt, label, new_state)

    def restrict_domain(self, node: int, prop: str, allowed):
        """Restrict domain and enqueue if changed."""
        if self.graph.restrict_domain(node, prop, allowed):
            self.prop_queue.append((node, prop))

    def set_edge_state(self, src: int, tgt: int, label: str, state: EdgeState):
        """Update edge state and enqueue if changed."""
        old = self.graph.edge_state(src, tgt, label)
        if old == state:
            return
        self.graph.set_edge_state(src, tgt, label, state)
        self.edge_queue.append((src, tgt, label, state))


class Constraint(ABC):
    """Abstract base class for constraints."""

    @abstractmethod
    def initial_propagate(self, ctx: PropagationContext):
        """Called once before solving to establish initial constraints."""
        pass

    @abstractmethod
    def propagate(self, ctx: PropagationContext, node: int, prop: str):
        """Called when a node's property domain changes."""
        pass

    @abstractmethod
    def propagate_edge(self, ctx: PropagationContext, src: int, tgt: int,
                       label: str, new_state: EdgeState):
        """Called when an edge state changes."""
        pass


class NodeConstraint(Constraint):
    """Restrict one or all nodes' property to allowed values."""

    def __init__(self, prop: str, allowed, node: Optional[int] = None):
        self.prop = prop
        self.allowed = frozenset(allowed)
        self.node = node  # None = apply to all nodes

    def initial_propagate(self, ctx: PropagationContext):
        if self.node is not None:
            ctx.restrict_domain(self.node, self.prop, self.allowed)
        else:
            for n in range(ctx.graph.num_nodes):
                ctx.restrict_domain(n, self.prop, self.allowed)

    def propagate(self, ctx: PropagationContext, node: int, prop: str):
        pass

    def propagate_edge(self, ctx: PropagationContext, src: int, tgt: int,
                       label: str, new_state: EdgeState):
        pass


class NoSelfEdgeConstraint(Constraint):
    """Eliminates all self-edges at initialization."""

    def initial_propagate(self, ctx: PropagationContext):
        # Self-edges are already excluded from WFCGraph construction,
        # so this is a no-op but kept for completeness.
        pass

    def propagate(self, ctx: PropagationContext, node: int, prop: str):
        pass

    def propagate_edge(self, ctx: PropagationContext, src: int, tgt: int,
                       label: str, new_state: EdgeState):
        pass


class EdgeConstraint(Constraint):
    """Relate source/target properties on labeled edges.

    Takes label, source_prop, target_prop (optional), and a predicate.
    The predicate(src_val, tgt_val) -> bool determines valid value pairs.
    """

    def __init__(self, label: str, source_prop: str,
                 target_prop: Optional[str] = None,
                 predicate: Callable = None):
        self.label = label
        self.source_prop = source_prop
        self.target_prop = target_prop or source_prop
        self.predicate = predicate or (lambda s, t: True)

    def initial_propagate(self, ctx: PropagationContext):
        # Check all existing potential/established edges
        g = ctx.graph
        for src in range(g.num_nodes):
            for tgt in range(g.num_nodes):
                if src == tgt:
                    continue
                key = (src, tgt, self.label)
                if key not in g._edges:
                    continue
                state = g._edges[key]
                if state == EdgeState.ELIMINATED:
                    continue
                self._check_edge(ctx, src, tgt, state)

    def propagate(self, ctx: PropagationContext, node: int, prop: str):
        if prop != self.source_prop and prop != self.target_prop:
            return
        g = ctx.graph
        # Check outgoing edges where this node is source
        if prop == self.source_prop:
            for tgt in range(g.num_nodes):
                if tgt == node:
                    continue
                key = (node, tgt, self.label)
                if key not in g._edges:
                    continue
                state = g._edges[key]
                if state == EdgeState.ELIMINATED:
                    continue
                self._check_edge(ctx, node, tgt, state)
        # Check incoming edges where this node is target
        if prop == self.target_prop:
            for src in range(g.num_nodes):
                if src == node:
                    continue
                key = (src, node, self.label)
                if key not in g._edges:
                    continue
                state = g._edges[key]
                if state == EdgeState.ELIMINATED:
                    continue
                self._check_edge(ctx, src, node, state)

    def propagate_edge(self, ctx: PropagationContext, src: int, tgt: int,
                       label: str, new_state: EdgeState):
        if label != self.label:
            return
        if new_state == EdgeState.ESTABLISHED:
            # Enforce arc consistency on established edge
            self._enforce_arc_consistency(ctx, src, tgt)

    def _check_edge(self, ctx: PropagationContext, src: int, tgt: int,
                    state: EdgeState):
        """Check if any valid value pair exists for this edge."""
        g = ctx.graph
        src_domain = g.domain(src, self.source_prop)
        tgt_domain = g.domain(tgt, self.target_prop)

        has_valid = False
        for sv in src_domain:
            for tv in tgt_domain:
                if self.predicate(sv, tv):
                    has_valid = True
                    break
            if has_valid:
                break

        if not has_valid:
            if state == EdgeState.ESTABLISHED:
                raise ContradictionError(
                    f"Established edge ({src},{tgt},{self.label}) has no "
                    f"valid value pairs"
                )
            ctx.set_edge_state(src, tgt, self.label, EdgeState.ELIMINATED)
        elif state == EdgeState.ESTABLISHED:
            self._enforce_arc_consistency(ctx, src, tgt)

    def _enforce_arc_consistency(self, ctx: PropagationContext,
                                 src: int, tgt: int):
        """For established edges, remove unsupported values."""
        g = ctx.graph
        src_domain = g.domain(src, self.source_prop)
        tgt_domain = g.domain(tgt, self.target_prop)

        # Find supported source values
        supported_src = set()
        for sv in src_domain:
            for tv in tgt_domain:
                if self.predicate(sv, tv):
                    supported_src.add(sv)
                    break

        # Find supported target values
        supported_tgt = set()
        for tv in tgt_domain:
            for sv in src_domain:
                if self.predicate(sv, tv):
                    supported_tgt.add(tv)
                    break

        if supported_src:
            ctx.restrict_domain(src, self.source_prop, frozenset(supported_src))
        if supported_tgt:
            ctx.restrict_domain(tgt, self.target_prop, frozenset(supported_tgt))


class CardinalityConstraint(Constraint):
    """Min/max edge count per node per label and direction."""

    def __init__(self, label: str, direction: str = "incoming",
                 min_count: int = 0, max_count: int = None):
        """
        direction: "incoming" or "outgoing"
        """
        self.label = label
        self.direction = direction
        self.min_count = min_count
        self.max_count = max_count

    def initial_propagate(self, ctx: PropagationContext):
        for node in range(ctx.graph.num_nodes):
            self._check_node(ctx, node)

    def propagate(self, ctx: PropagationContext, node: int, prop: str):
        pass

    def propagate_edge(self, ctx: PropagationContext, src: int, tgt: int,
                       label: str, new_state: EdgeState):
        if label != self.label:
            return
        if self.direction == "incoming":
            self._check_node(ctx, tgt)
        else:
            self._check_node(ctx, src)

    def _check_node(self, ctx: PropagationContext, node: int):
        g = ctx.graph
        if self.direction == "incoming":
            edges = g.incoming_edges(node, self.label,
                                     {EdgeState.POTENTIAL, EdgeState.ESTABLISHED})
            established = g.incoming_edges(node, self.label,
                                           {EdgeState.ESTABLISHED})
            potential = g.incoming_edges(node, self.label,
                                         {EdgeState.POTENTIAL})
        else:
            edges = g.outgoing_edges(node, self.label,
                                     {EdgeState.POTENTIAL, EdgeState.ESTABLISHED})
            established = g.outgoing_edges(node, self.label,
                                           {EdgeState.ESTABLISHED})
            potential = g.outgoing_edges(node, self.label,
                                         {EdgeState.POTENTIAL})

        est_count = len(established)
        pot_count = len(potential)
        possible_count = est_count + pot_count

        # Check violation
        if self.max_count is not None and est_count > self.max_count:
            raise ContradictionError(
                f"Node {node} has {est_count} established {self.direction} "
                f"'{self.label}' edges, exceeding max {self.max_count}"
            )
        if possible_count < self.min_count:
            raise ContradictionError(
                f"Node {node} can have at most {possible_count} "
                f"{self.direction} '{self.label}' edges, below min "
                f"{self.min_count}"
            )

        # If established count equals max, eliminate remaining potential
        if self.max_count is not None and est_count == self.max_count:
            for s, t in potential:
                ctx.set_edge_state(s, t, self.label, EdgeState.ELIMINATED)

        # If possible count equals min, establish all remaining potential
        if possible_count == self.min_count and self.min_count > 0:
            for s, t in potential:
                ctx.set_edge_state(s, t, self.label, EdgeState.ESTABLISHED)


class SoftConstraint(Constraint):
    """Weight modifier - doesn't eliminate, biases collapse choices."""

    def __init__(self, label: str, source_prop: str,
                 target_prop: Optional[str] = None,
                 weight_fn: Callable = None):
        """
        weight_fn(src_val, tgt_val) -> float weight multiplier.
        Applied to target node's soft weights for each established edge.
        """
        self.label = label
        self.source_prop = source_prop
        self.target_prop = target_prop or source_prop
        self.weight_fn = weight_fn or (lambda s, t: 1.0)

    def initial_propagate(self, ctx: PropagationContext):
        # Apply weights for any already-established edges
        self._apply_all_weights(ctx)

    def propagate(self, ctx: PropagationContext, node: int, prop: str):
        if prop == self.source_prop or prop == self.target_prop:
            self._apply_all_weights(ctx)

    def propagate_edge(self, ctx: PropagationContext, src: int, tgt: int,
                       label: str, new_state: EdgeState):
        if label != self.label:
            return
        if new_state == EdgeState.ESTABLISHED:
            self._apply_edge_weights(ctx, src, tgt)

    def _apply_all_weights(self, ctx: PropagationContext):
        g = ctx.graph
        for src, tgt in g.get_established_edges(self.label):
            self._apply_edge_weights(ctx, src, tgt)

    def _apply_edge_weights(self, ctx: PropagationContext, src: int, tgt: int):
        g = ctx.graph
        src_domain = g.domain(src, self.source_prop)
        tgt_domain = g.domain(tgt, self.target_prop)

        if src_domain.is_collapsed():
            src_val = src_domain.get_value()
            for tv in tgt_domain:
                w = self.weight_fn(src_val, tv)
                if w != 1.0:
                    current = g.get_soft_weight(tgt, self.target_prop, tv)
                    g.set_soft_weight(tgt, self.target_prop, tv, current * w)


class WFCSolver:
    """Main solver that collapses all domains using constraints."""

    def __init__(self, graph: WFCGraph, constraints: list,
                 priority_fn: Callable = None,
                 max_restarts: int = 100,
                 rng: random.Random = None,
                 epsilon: float = 0.0):
        self.graph = graph
        self.constraints = constraints
        self.priority_fn = priority_fn or (lambda n, p, d: d.entropy())
        self.max_restarts = max_restarts
        self.rng = rng or random.Random()
        self.epsilon = epsilon
        self._ctx = PropagationContext(graph)

    def solve(self) -> bool:
        """Attempt to solve. Returns True if successful."""
        initial_snap = self.graph.snapshot()
        for attempt in range(self.max_restarts):
            if attempt > 0:
                self.graph.restore(initial_snap)
                self._ctx = PropagationContext(self.graph)
            try:
                if self._solve_inner():
                    return True
            except ContradictionError:
                continue
        return False

    def observe(self, node: int, prop: str, value):
        """Fix a node's property to a specific value and propagate."""
        self._ctx.restrict_domain(node, prop, frozenset({value}))
        self._propagate()

    def establish_edge(self, src: int, tgt: int, label: str):
        """Establish an edge and propagate."""
        self._ctx.set_edge_state(src, tgt, label, EdgeState.ESTABLISHED)
        self._propagate()

    def eliminate_edge(self, src: int, tgt: int, label: str):
        """Eliminate an edge and propagate."""
        self._ctx.set_edge_state(src, tgt, label, EdgeState.ELIMINATED)
        self._propagate()

    def _solve_inner(self) -> bool:
        """Single solve attempt. Returns True on success, raises on contradiction."""
        self._initialize()

        while not self.graph.is_fully_collapsed():
            if self.epsilon > 0 and self.rng.random() < self.epsilon:
                # Epsilon-random: pick a random uncollapsed (node, prop)
                uncollapsed = [
                    (n, prop)
                    for n in range(self.graph.num_nodes)
                    for prop in self.graph.property_specs
                    if not self.graph.domain(n, prop).is_collapsed()
                ]
                if not uncollapsed:
                    break
                node, prop = self.rng.choice(uncollapsed)
            else:
                # Priority-based selection
                best = None
                best_priority = float("inf")

                for n in range(self.graph.num_nodes):
                    for prop in self.graph.property_specs:
                        dom = self.graph.domain(n, prop)
                        if dom.is_collapsed():
                            continue
                        p = self.priority_fn(n, prop, dom)
                        if p < best_priority:
                            best_priority = p
                            best = (n, prop)

                if best is None:
                    break

                node, prop = best
            dom = self.graph.domain(node, prop)
            values = list(dom)

            # Weighted random by soft weights
            weights = [self.graph.get_soft_weight(node, prop, v) for v in values]

            # Shuffle to break ties randomly
            combined = list(zip(values, weights))
            self.rng.shuffle(combined)
            values, weights = zip(*combined) if combined else ([], [])
            values = list(values)
            weights = list(weights)

            # Sort by weight descending for try order (higher weight = more likely)
            order = sorted(range(len(values)), key=lambda i: -weights[i])

            collapsed = False
            snap = self.graph.snapshot()

            for idx in order:
                v = values[idx]
                # Weighted random: instead of strict order, sample weighted
                # but use backtracking order by weight
                try:
                    self.graph.restore(snap)
                    self._ctx = PropagationContext(self.graph)
                    self._ctx.restrict_domain(node, prop, frozenset({v}))
                    self._propagate()
                    collapsed = True
                    break
                except ContradictionError:
                    continue

            if not collapsed:
                raise ContradictionError(
                    f"All values exhausted for node {node} property '{prop}'"
                )

        # Resolve remaining potential edges
        self._resolve_edges()
        return True

    def _initialize(self):
        """Call initial_propagate on all constraints, then propagate."""
        for c in self.constraints:
            c.initial_propagate(self._ctx)
        self._propagate()

    def _propagate(self):
        """Propagate until fixpoint."""
        ctx = self._ctx
        while ctx.prop_queue or ctx.edge_queue:
            while ctx.prop_queue:
                node, prop = ctx.prop_queue.popleft()
                for c in self.constraints:
                    c.propagate(ctx, node, prop)
            while ctx.edge_queue:
                src, tgt, label, state = ctx.edge_queue.popleft()
                for c in self.constraints:
                    c.propagate_edge(ctx, src, tgt, label, state)

    def _resolve_edges(self):
        """Resolve remaining potential edges after all properties collapsed."""
        g = self.graph
        for label in g.edge_labels:
            for src in range(g.num_nodes):
                for tgt in range(g.num_nodes):
                    if src == tgt:
                        continue
                    key = (src, tgt, label)
                    if g._edges[key] == EdgeState.POTENTIAL:
                        # Check if the edge is valid given collapsed values
                        valid = True
                        for c in self.constraints:
                            if isinstance(c, EdgeConstraint) and c.label == label:
                                sv = g.get_value(src, c.source_prop)
                                tv = g.get_value(tgt, c.target_prop)
                                if not c.predicate(sv, tv):
                                    valid = False
                                    break
                        if not valid:
                            self._ctx.set_edge_state(src, tgt, label,
                                                     EdgeState.ELIMINATED)
                        else:
                            # Check cardinality before establishing
                            can_establish = True
                            for c in self.constraints:
                                if (isinstance(c, CardinalityConstraint)
                                        and c.label == label):
                                    if c.direction == "incoming":
                                        est = g.incoming_edges(
                                            tgt, label,
                                            {EdgeState.ESTABLISHED})
                                        if (c.max_count is not None
                                                and len(est) >= c.max_count):
                                            can_establish = False
                                    else:
                                        est = g.outgoing_edges(
                                            src, label,
                                            {EdgeState.ESTABLISHED})
                                        if (c.max_count is not None
                                                and len(est) >= c.max_count):
                                            can_establish = False
                            if not can_establish:
                                self._ctx.set_edge_state(
                                    src, tgt, label, EdgeState.ELIMINATED)
                            else:
                                # Leave as potential - will be eliminated below
                                pass

            # Eliminate all remaining potential edges for this label
            for src in range(g.num_nodes):
                for tgt in range(g.num_nodes):
                    if src == tgt:
                        continue
                    key = (src, tgt, label)
                    if g._edges[key] == EdgeState.POTENTIAL:
                        self._ctx.set_edge_state(src, tgt, label,
                                                 EdgeState.ELIMINATED)
        # Final propagation
        self._propagate()
