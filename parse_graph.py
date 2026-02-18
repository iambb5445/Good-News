"""
parse_graph.py — Parser for .gwfc files and WFC runner.

Usage:
    python parse_graph.py description.gwfc --count person=5 location=2 [--seed 42] [--restarts 100]
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

from wfc import (
    CardinalityConstraint,
    Constraint,
    EdgeConstraint,
    EdgeState,
    PropagationContext,
    WFCGraph,
    WFCSolver,
)

# ---------------------------------------------------------------------------
# Token kinds
# ---------------------------------------------------------------------------

TK_NUMBER = "NUMBER"
TK_IDENT = "IDENT"
TK_CONST = "CONST"          # .name
TK_STRING_TYPE = "STRING_TYPE"  # <str>
TK_LBRACE = "LBRACE"
TK_RBRACE = "RBRACE"
TK_LPAREN = "LPAREN"
TK_RPAREN = "RPAREN"
TK_LBRACK = "LBRACK"
TK_RBRACK = "RBRACK"
TK_COMMA = "COMMA"
TK_COLON = "COLON"
TK_DOT = "DOT"
TK_EQ = "EQ"       # ==
TK_NEQ = "NEQ"     # !=
TK_LE = "LE"       # <=
TK_GE = "GE"       # >=
TK_LT = "LT"       # <
TK_GT = "GT"       # >
TK_PLUS = "PLUS"
TK_MINUS = "MINUS"
TK_SLASH = "SLASH"
TK_ASSIGN = "ASSIGN"   # single =
TK_EOF = "EOF"

_TOKEN_PATTERNS = [
    (TK_NUMBER,      r'\d+(?:\.\d+)?'),
    (TK_STRING_TYPE, r'<str>'),
    (TK_EQ,          r'=='),
    (TK_NEQ,         r'!='),
    (TK_LE,          r'<='),
    (TK_GE,          r'>='),
    (TK_LT,          r'<'),
    (TK_GT,          r'>'),
    (TK_ASSIGN,      r'='),
    (TK_LBRACE,      r'\{'),
    (TK_RBRACE,      r'\}'),
    (TK_LPAREN,      r'\('),
    (TK_RPAREN,      r'\)'),
    (TK_LBRACK,      r'\['),
    (TK_RBRACK,      r'\]'),
    (TK_COMMA,       r','),
    (TK_COLON,       r':'),
    (TK_PLUS,        r'\+'),
    (TK_MINUS,       r'-'),
    (TK_SLASH,       r'/'),
    # CONST before DOT so `.name` is captured as one token
    (TK_CONST,       r'\.[A-Za-z_]\w*'),
    (TK_DOT,         r'\.'),
    (TK_IDENT,       r'[A-Za-z_]\w*'),
]

_MASTER_RE = re.compile(
    '|'.join(f'(?P<{kind}>{pat})' for kind, pat in _TOKEN_PATTERNS)
)


@dataclass
class Token:
    kind: str
    value: str
    line: int


def tokenize(text: str) -> list:
    tokens = []
    line = 1
    pos = 0
    while pos < len(text):
        # Skip whitespace
        if text[pos] in ' \t\r\n':
            if text[pos] == '\n':
                line += 1
            pos += 1
            continue
        # Skip line comments
        if text[pos] == '#':
            while pos < len(text) and text[pos] != '\n':
                pos += 1
            continue
        m = _MASTER_RE.match(text, pos)
        if not m:
            raise SyntaxError(f"Unexpected character {text[pos]!r} at line {line}")
        kind = m.lastgroup
        tokens.append(Token(kind, m.group(), line))
        pos = m.end()
    tokens.append(Token(TK_EOF, '', line))
    return tokens


# ---------------------------------------------------------------------------
# AST Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PropertyDef:
    name: str
    kind: str                      # "enum" | "range" | "string"
    values: frozenset = field(default_factory=frozenset)
    lo: float = 0.0
    hi: float = 0.0


@dataclass
class PropEqLiteral:
    var: str
    prop: str
    value: str


@dataclass
class PropCompare:
    left_var: str
    left_prop: str
    op: str
    right_var: str
    right_prop: str
    offset: float = 0.0


@dataclass
class ForEveryConstraint:
    raw_text: str


@dataclass
class EdgeTypeDef:
    source_type: str
    target_type: str
    src_var: str
    tgt_var: str
    bidirectional: bool
    simple_constraints: list
    complex_constraints: list


@dataclass
class DegreeConstraint:
    edge_label: str
    direction: str   # "incoming" | "outgoing"
    op: str
    count: int


@dataclass
class GlobalRule:
    node_type: str
    var_name: str
    degree_constraints: list


@dataclass
class Schema:
    constants: dict
    node_types: dict           # name -> list[PropertyDef]
    edge_types: dict           # name -> EdgeTypeDef
    global_rules: list
    probability_rules: list    # raw text lines


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list):
        self._tokens = tokens
        self._pos = 0

    # --- low-level helpers ---

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _peek2(self) -> Token:
        if self._pos + 1 < len(self._tokens):
            return self._tokens[self._pos + 1]
        return Token(TK_EOF, '', -1)

    def _advance(self) -> Token:
        t = self._tokens[self._pos]
        self._pos += 1
        return t

    def _expect(self, kind: str) -> Token:
        t = self._peek()
        if t.kind != kind:
            raise ParseError(
                f"Line {t.line}: expected {kind}, got {t.kind} ({t.value!r})"
            )
        return self._advance()

    def _accept(self, kind: str, value: str = None) -> Optional[Token]:
        t = self._peek()
        if t.kind == kind and (value is None or t.value == value):
            return self._advance()
        return None

    def _expect_ident(self, name: str = None) -> Token:
        t = self._peek()
        if t.kind != TK_IDENT:
            raise ParseError(
                f"Line {t.line}: expected identifier, got {t.kind} ({t.value!r})"
            )
        if name and t.value != name:
            raise ParseError(
                f"Line {t.line}: expected '{name}', got {t.value!r}"
            )
        return self._advance()

    # --- top-level ---

    def parse_file(self) -> Schema:
        constants = {}
        node_types = {}
        edge_types = {}
        global_rules = []
        probability_rules = []

        while self._peek().kind != TK_EOF:
            t = self._peek()
            if t.kind == TK_CONST:
                name, val = self.parse_constant()
                constants[name] = val
            elif t.kind == TK_IDENT:
                block = t.value
                if block == 'nodes':
                    self._advance()
                    node_types = self.parse_nodes_block()
                elif block == 'edges':
                    self._advance()
                    edge_types = self.parse_edges_block(constants)
                elif block == 'global':
                    self._advance()
                    global_rules = self.parse_global_block()
                elif block == 'probability':
                    self._advance()
                    probability_rules = self.parse_probability_block()
                else:
                    raise ParseError(f"Line {t.line}: unknown block {block!r}")
            else:
                raise ParseError(f"Line {t.line}: unexpected {t.kind} ({t.value!r})")

        return Schema(constants, node_types, edge_types, global_rules, probability_rules)

    def parse_constant(self):
        t = self._expect(TK_CONST)
        name = t.value[1:]  # strip leading dot
        num = self._expect(TK_NUMBER)
        return name, float(num.value)

    def parse_nodes_block(self) -> dict:
        self._expect(TK_LBRACE)
        node_types = {}
        while self._peek().kind != TK_RBRACE:
            name = self._expect_ident().value
            self._expect(TK_LBRACE)
            props = []
            while self._peek().kind != TK_RBRACE:
                props.append(self.parse_prop_def())
            self._expect(TK_RBRACE)
            node_types[name] = props
        self._expect(TK_RBRACE)
        return node_types

    def parse_prop_def(self) -> PropertyDef:
        name = self._expect_ident().value
        t = self._peek()
        if t.kind == TK_STRING_TYPE:
            self._advance()
            return PropertyDef(name=name, kind='string')
        elif t.kind == TK_LBRACK:
            self._advance()
            values = []
            values.append(self._expect_ident().value)
            while self._accept(TK_COMMA):
                values.append(self._expect_ident().value)
            self._expect(TK_RBRACK)
            return PropertyDef(name=name, kind='enum', values=frozenset(values))
        elif t.kind == TK_LPAREN:
            self._advance()
            lo = self._parse_const_or_number()
            self._expect(TK_COMMA)
            hi = self._parse_const_or_number()
            self._expect(TK_RPAREN)
            return PropertyDef(name=name, kind='range', lo=lo, hi=hi)
        else:
            raise ParseError(f"Line {t.line}: expected property type, got {t.kind}")

    def _parse_const_or_number(self, constants=None) -> float:
        t = self._peek()
        if t.kind == TK_NUMBER:
            self._advance()
            return float(t.value)
        elif t.kind == TK_CONST:
            self._advance()
            # We don't have constants here since range parsing happens before
            # they're resolved — return 0 as placeholder; real resolution in
            # build phase will use the schema constants dict passed separately.
            return t.value  # return as string ref for later resolution
        else:
            raise ParseError(f"Line {t.line}: expected number or constant")

    def parse_edges_block(self, constants: dict) -> dict:
        self._expect(TK_LBRACE)
        edge_types = {}
        while self._peek().kind != TK_RBRACE:
            name = self._expect_ident().value
            self._expect(TK_LBRACE)
            # header: src_type src_var to tgt_type tgt_var
            src_type = self._expect_ident().value
            src_var = self._expect_ident().value
            self._expect_ident('to')
            tgt_type = self._expect_ident().value
            tgt_var = self._expect_ident().value

            bidirectional = False
            simple = []
            complex_ = []

            while self._peek().kind != TK_RBRACE:
                c = self.parse_edge_constraint(src_var, tgt_var, constants)
                if c == 'bidirectional':
                    bidirectional = True
                elif isinstance(c, ForEveryConstraint):
                    complex_.append(c)
                else:
                    simple.append(c)

            self._expect(TK_RBRACE)
            edge_types[name] = EdgeTypeDef(
                source_type=src_type,
                target_type=tgt_type,
                src_var=src_var,
                tgt_var=tgt_var,
                bidirectional=bidirectional,
                simple_constraints=simple,
                complex_constraints=complex_,
            )
        self._expect(TK_RBRACE)
        return edge_types

    def parse_edge_constraint(self, src_var: str, tgt_var: str, constants: dict):
        t = self._peek()
        if t.kind == TK_IDENT and t.value == 'bidirectional':
            self._advance()
            return 'bidirectional'
        if t.kind == TK_IDENT and t.value == 'for':
            raw = self._collect_for_every_line()
            return ForEveryConstraint(raw_text=raw)

        # simple constraint: expr op expr
        lhs_var, lhs_prop, lhs_offset = self._parse_expr(src_var, tgt_var, constants)
        op_tok = self._parse_op()
        rhs_var, rhs_prop, rhs_offset = self._parse_expr(src_var, tgt_var, constants)

        # net offset: lhs + lhs_offset  op  rhs + rhs_offset
        # rewrite as: lhs op rhs + (rhs_offset - lhs_offset)
        net_offset = rhs_offset - lhs_offset

        if rhs_var is None:
            # rhs is a literal value (enum)
            return PropEqLiteral(var=lhs_var, prop=lhs_prop, value=rhs_prop)

        return PropCompare(
            left_var=lhs_var,
            left_prop=lhs_prop,
            op=op_tok,
            right_var=rhs_var,
            right_prop=rhs_prop,
            offset=net_offset,
        )

    def _parse_expr(self, src_var: str, tgt_var: str, constants: dict):
        """
        Parse an expression like:
          f.age, x.age, x.age + .constant, male (bare ident = literal)
        Returns (var_or_none, prop_or_literal, numeric_offset)
        If var_or_none is None, prop_or_literal is the literal value.

        NOTE: the tokenizer emits `f.age` as IDENT('f') + CONST('.age'),
        since the CONST pattern matches the dot+word as a single token.
        """
        t = self._peek()
        p2 = self._peek2()

        if t.kind == TK_IDENT:
            name = t.value
            if p2.kind == TK_CONST:
                # var.prop pattern: IDENT + CONST('.propname')
                self._advance()          # consume var
                const_tok = self._advance()  # consume .prop
                prop = const_tok.value[1:]   # strip leading dot
                offset = 0.0
                if self._peek().kind == TK_PLUS:
                    self._advance()
                    offset = self._resolve_const_or_number(constants)
                elif self._peek().kind == TK_MINUS:
                    self._advance()
                    offset = -self._resolve_const_or_number(constants)
                return (name, prop, offset)
            elif p2.kind == TK_DOT:
                # Fallback: separate DOT + IDENT
                self._advance()
                self._advance()
                prop = self._expect_ident().value
                offset = 0.0
                if self._peek().kind == TK_PLUS:
                    self._advance()
                    offset = self._resolve_const_or_number(constants)
                elif self._peek().kind == TK_MINUS:
                    self._advance()
                    offset = -self._resolve_const_or_number(constants)
                return (name, prop, offset)
            else:
                # bare identifier = literal value
                self._advance()
                return (None, name, 0.0)

        raise ParseError(f"Line {t.line}: expected expression, got {t.kind} ({t.value!r})")

    def _resolve_const_or_number(self, constants: dict) -> float:
        t = self._peek()
        if t.kind == TK_NUMBER:
            self._advance()
            return float(t.value)
        elif t.kind == TK_CONST:
            self._advance()
            cname = t.value[1:]
            if cname not in constants:
                raise ParseError(f"Line {t.line}: unknown constant {t.value!r}")
            return constants[cname]
        raise ParseError(f"Line {t.line}: expected number or constant")

    def _parse_op(self) -> str:
        t = self._advance()
        if t.kind in (TK_EQ, TK_NEQ, TK_LE, TK_GE, TK_LT, TK_GT):
            return t.kind
        raise ParseError(f"Line {t.line}: expected comparison operator, got {t.kind}")

    def _collect_for_every_line(self) -> str:
        """Consume tokens until end of logical line (heuristic: until next constraint or })."""
        start = self._pos
        # Collect until we hit RBRACE or another top-level constraint keyword
        # Strategy: scan to end of line by reading all tokens on the same logical line.
        # Since we don't have line tracking in tokens easily, collect until the pattern
        # changes — detect by looking for RBRACE or 'for'/'bidirectional' at token start.
        parts = []
        while True:
            t = self._peek()
            if t.kind == TK_RBRACE or t.kind == TK_EOF:
                break
            # Stop if next line starts a new constraint (for, bidirectional, or var.prop op)
            # We check if we've consumed at least a 'for every' prefix
            if parts and t.kind == TK_IDENT and t.value in ('for', 'bidirectional'):
                break
            if parts and t.kind == TK_IDENT and self._peek2().kind == TK_DOT:
                # Could be start of next simple constraint like f.gender == male
                break
            parts.append(t.value)
            self._advance()
        return ' '.join(parts)

    def parse_global_block(self) -> list:
        self._expect(TK_LBRACE)
        rules = []
        while self._peek().kind != TK_RBRACE:
            self._expect_ident('for')
            self._expect_ident('every')
            node_type = self._expect_ident().value
            var_name = self._expect_ident().value
            self._expect(TK_COLON)
            self._expect(TK_LBRACE)
            degree_constraints = []
            while self._peek().kind != TK_RBRACE:
                dc = self._parse_degree_constraint(var_name)
                degree_constraints.append(dc)
            self._expect(TK_RBRACE)
            rules.append(GlobalRule(
                node_type=node_type,
                var_name=var_name,
                degree_constraints=degree_constraints,
            ))
        self._expect(TK_RBRACE)
        return rules

    def _parse_degree_constraint(self, var_name: str) -> DegreeConstraint:
        # Syntax: edgelabel.to.varname.degree op NUMBER
        # e.g.  home.to.p.degree == 1
        # Tokenized as: IDENT('home') CONST('.to') CONST('.p') CONST('.degree') EQ NUMBER
        edge_label = self._expect_ident().value

        # .to or .from
        t = self._expect(TK_CONST)
        direction_word = t.value[1:]  # strip dot

        # .varname (ignored)
        self._expect(TK_CONST)

        # .degree
        t = self._expect(TK_CONST)
        if t.value[1:] != 'degree':
            raise ParseError(f"Line {t.line}: expected '.degree', got {t.value!r}")

        op_tok = self._parse_op()
        num = self._expect(TK_NUMBER)

        direction = 'incoming' if direction_word == 'to' else 'outgoing'
        return DegreeConstraint(
            edge_label=edge_label,
            direction=direction,
            op=op_tok,
            count=int(float(num.value)),
        )

    def parse_probability_block(self) -> list:
        self._expect(TK_LBRACE)
        raw_lines = []
        depth = 1
        while depth > 0 and self._peek().kind != TK_EOF:
            t = self._advance()
            if t.kind == TK_LBRACE:
                depth += 1
            elif t.kind == TK_RBRACE:
                depth -= 1
                if depth == 0:
                    break
            raw_lines.append(t.value)
        return raw_lines


# ---------------------------------------------------------------------------
# Stub constraint classes (generated dynamically)
# ---------------------------------------------------------------------------

def make_stub_constraint(class_name: str, docstring: str) -> type:
    """Dynamically create a no-op Constraint subclass with given docstring."""

    def initial_propagate(self, ctx):
        pass

    def propagate(self, ctx, node, prop):
        pass

    def propagate_edge(self, ctx, src, tgt, label, state):
        pass

    cls = type(class_name, (Constraint,), {
        '__doc__': docstring,
        'initial_propagate': initial_propagate,
        'propagate': propagate,
        'propagate_edge': propagate_edge,
    })
    return cls


# ---------------------------------------------------------------------------
# WFC Graph Builder
# ---------------------------------------------------------------------------

def _op_to_bounds(op: str, count: int):
    """Convert comparison op + count to (min_count, max_count)."""
    if op == TK_EQ:
        return (count, count)
    elif op == TK_LE:
        return (0, count)
    elif op == TK_GE:
        return (count, None)
    elif op == TK_LT:
        return (0, count - 1)
    elif op == TK_GT:
        return (count + 1, None)
    raise ValueError(f"Unknown op {op!r}")


def _compare(a, op: str, b) -> bool:
    if op == TK_EQ:
        return a == b
    elif op == TK_NEQ:
        return a != b
    elif op == TK_LT:
        return a < b
    elif op == TK_GT:
        return a > b
    elif op == TK_LE:
        return a <= b
    elif op == TK_GE:
        return a >= b
    raise ValueError(f"Unknown op {op!r}")


def _resolve_range(lo, hi, constants: dict):
    """Resolve range endpoints, which may be string refs to constants."""
    if isinstance(lo, str):
        lo = constants[lo[1:]] if lo.startswith('.') else constants[lo]
    if isinstance(hi, str):
        hi = constants[hi[1:]] if hi.startswith('.') else constants[hi]
    return float(lo), float(hi)


def build_wfc(schema: Schema, node_counts: dict, rng):
    """
    Build WFCGraph + constraints from a Schema.

    node_counts: {type_name: int}
    Returns (graph, constraints, node_type_of, node_type_ranges)
    """
    # --- Assign node indices ---
    node_type_of = []
    node_type_ranges = {}  # type -> (start, end)
    for type_name, count in node_counts.items():
        start = len(node_type_of)
        node_type_of.extend([type_name] * count)
        node_type_ranges[type_name] = (start, start + count)
    num_nodes = len(node_type_of)

    # --- Build property_specs ---
    # Union of all properties across all node types.
    # String properties are skipped with a warning.
    string_warned = set()
    property_specs = {}

    for type_name, props in schema.node_types.items():
        for pdef in props:
            if pdef.kind == 'string':
                if pdef.name not in string_warned:
                    print(
                        f"WARNING: Property '{pdef.name}' is <str> — "
                        f"skipping (not representable in WFC domain).",
                        file=sys.stderr,
                    )
                    string_warned.add(pdef.name)
                continue
            if pdef.name not in property_specs:
                if pdef.kind == 'enum':
                    property_specs[pdef.name] = frozenset(pdef.values | {None})
                else:
                    lo, hi = _resolve_range(pdef.lo, pdef.hi, schema.constants)
                    int_vals = frozenset(range(int(lo), int(hi) + 1)) | {None}
                    property_specs[pdef.name] = int_vals

    # --- Edge pairs ---
    edge_labels = list(schema.edge_types.keys())
    edge_pairs = []
    for label, edef in schema.edge_types.items():
        src_range = node_type_ranges.get(edef.source_type)
        tgt_range = node_type_ranges.get(edef.target_type)
        if src_range is None or tgt_range is None:
            continue
        for src in range(*src_range):
            for tgt in range(*tgt_range):
                if src != tgt:
                    edge_pairs.append((src, tgt, label))
        if edef.bidirectional:
            for tgt in range(*tgt_range):
                for src in range(*src_range):
                    if src != tgt:
                        edge_pairs.append((tgt, src, label))

    # --- Build graph ---
    graph = WFCGraph(
        num_nodes=num_nodes,
        property_specs=property_specs,
        edge_labels=edge_labels,
        edge_pairs=edge_pairs,
    )

    # --- Per-node domain restriction ---
    for node_idx, type_name in enumerate(node_type_of):
        node_props = {p.name: p for p in schema.node_types.get(type_name, [])}
        for prop_name in property_specs:
            if prop_name in node_props and node_props[prop_name].kind != 'string':
                pdef = node_props[prop_name]
                if pdef.kind == 'enum':
                    graph.restrict_domain(node_idx, prop_name, pdef.values)
                else:
                    lo, hi = _resolve_range(pdef.lo, pdef.hi, schema.constants)
                    graph.restrict_domain(node_idx, prop_name,
                                         frozenset(range(int(lo), int(hi) + 1)))
            else:
                # Property doesn't belong to this node type
                graph.restrict_domain(node_idx, prop_name, frozenset({None}))

    # --- Translate constraints ---
    constraints = []
    stub_index = [0]  # mutable counter for stub naming

    for label, edef in schema.edge_types.items():
        # Simple constraints
        for sc in edef.simple_constraints:
            if isinstance(sc, PropEqLiteral):
                # sc.var is either src_var or tgt_var
                if sc.var == edef.src_var:
                    # predicate checks source value
                    val = sc.value
                    constraints.append(
                        EdgeConstraint(
                            label, sc.prop, sc.prop,
                            lambda sv, tv, _v=val: sv == _v
                        )
                    )
                else:
                    # predicate checks target value
                    val = sc.value
                    constraints.append(
                        EdgeConstraint(
                            label, sc.prop, sc.prop,
                            lambda sv, tv, _v=val: tv == _v
                        )
                    )
            elif isinstance(sc, PropCompare):
                op = sc.op
                offset = sc.offset
                if sc.left_var == edef.src_var:
                    # left=src, right=tgt
                    lp, rp = sc.left_prop, sc.right_prop
                    constraints.append(
                        EdgeConstraint(
                            label, lp, rp,
                            lambda sv, tv, _op=op, _off=offset: (
                                sv is not None and tv is not None and
                                _compare(sv, _op, tv + _off)
                            )
                        )
                    )
                else:
                    # left=tgt, right=src (swap roles for EdgeConstraint)
                    lp, rp = sc.right_prop, sc.left_prop
                    constraints.append(
                        EdgeConstraint(
                            label, rp, lp,
                            lambda sv, tv, _op=op, _off=offset: (
                                sv is not None and tv is not None and
                                _compare(tv, _op, sv + _off)
                            )
                        )
                    )

        # Complex constraints (stubs)
        for fc in edef.complex_constraints:
            idx = stub_index[0]
            stub_index[0] += 1
            class_name = f"Stub_{label}_ForEvery{idx}"
            docstring = (
                f"STUB: Unsupported constraint from .gwfc:\n"
                f"  {fc.raw_text}\n"
                f"TODO: implement this constraint"
            )
            print(
                f"WARNING: Skipping complex constraint in '{label}':\n"
                f"  {fc.raw_text}\n"
                f"  → Using no-op stub {class_name} (implement in parse_graph.py)",
                file=sys.stderr,
            )
            stub_cls = make_stub_constraint(class_name, docstring)
            constraints.append(stub_cls())

    # Global rules → CardinalityConstraints
    # Global rules apply to specific node types; CardinalityConstraint applies to all nodes.
    # We wrap with a subclass that only fires for the relevant nodes.
    # When min_count > 0, also add _MandatoryEstablishConstraint because wfc.py's
    # _resolve_edges eliminates all remaining POTENTIAL edges at the end, which would
    # violate the minimum. The mandatory constraint establishes required edges early.
    for rule in schema.global_rules:
        type_start, type_end = node_type_ranges.get(rule.node_type, (0, 0))
        for dc in rule.degree_constraints:
            min_c, max_c = _op_to_bounds(dc.op, dc.count)
            if min_c > 0:
                constraints.append(
                    _MandatoryEstablishConstraint(
                        label=dc.edge_label,
                        direction=dc.direction,
                        min_count=min_c,
                        node_start=type_start,
                        node_end=type_end,
                        rng=rng,
                    )
                )
            constraints.append(
                _TypedCardinalityConstraint(
                    label=dc.edge_label,
                    direction=dc.direction,
                    min_count=min_c,
                    max_count=max_c,
                    node_start=type_start,
                    node_end=type_end,
                )
            )

    # Probability block stub
    if schema.probability_rules:
        raw = ' '.join(schema.probability_rules)
        class_name = "Stub_ProbabilityRules"
        docstring = (
            f"STUB: 'probability' block not translated from .gwfc:\n  {raw}\n"
            f"TODO: implement probability inheritance"
        )
        print(
            "WARNING: 'probability' block not translated.\n"
            "  → Using no-op stub Stub_ProbabilityRules",
            file=sys.stderr,
        )
        stub_cls = make_stub_constraint(class_name, docstring)
        constraints.append(stub_cls())

    return graph, constraints, node_type_of, node_type_ranges


class _MandatoryEstablishConstraint(Constraint):
    """
    Establishes min_count edges per qualifying node during initial_propagate.

    wfc.py's _resolve_edges eliminates all remaining POTENTIAL edges at the end.
    If a node needs at least 1 edge (min_count > 0), we must establish it during
    the solve phase. This constraint randomly picks and establishes the required
    edges so that the solver doesn't end up eliminating them all.
    """

    def __init__(self, label, direction, min_count, node_start, node_end, rng):
        self.label = label
        self.direction = direction
        self.min_count = min_count
        self.node_start = node_start
        self.node_end = node_end
        self.rng = rng

    def initial_propagate(self, ctx):
        for node in range(self.node_start, self.node_end):
            if self.direction == 'incoming':
                candidates = ctx.graph.incoming_edges(
                    node, self.label, {EdgeState.POTENTIAL}
                )
            else:
                candidates = ctx.graph.outgoing_edges(
                    node, self.label, {EdgeState.POTENTIAL}
                )
            # Count already-established edges (from previous constraints)
            if self.direction == 'incoming':
                already = len(ctx.graph.incoming_edges(
                    node, self.label, {EdgeState.ESTABLISHED}
                ))
            else:
                already = len(ctx.graph.outgoing_edges(
                    node, self.label, {EdgeState.ESTABLISHED}
                ))
            needed = self.min_count - already
            if needed <= 0:
                continue
            self.rng.shuffle(candidates)
            for i in range(min(needed, len(candidates))):
                src, tgt = candidates[i]
                ctx.set_edge_state(src, tgt, self.label, EdgeState.ESTABLISHED)

    def propagate(self, ctx, node, prop):
        pass

    def propagate_edge(self, ctx, src, tgt, label, new_state):
        pass


class _TypedCardinalityConstraint(CardinalityConstraint):
    """CardinalityConstraint that only applies to nodes in a type range."""

    def __init__(self, label, direction, min_count, max_count, node_start, node_end):
        super().__init__(label, direction, min_count, max_count)
        self.node_start = node_start
        self.node_end = node_end

    def _in_range(self, node: int) -> bool:
        return self.node_start <= node < self.node_end

    def initial_propagate(self, ctx):
        for node in range(self.node_start, self.node_end):
            self._check_node(ctx, node)

    def propagate_edge(self, ctx, src, tgt, label, new_state):
        if label != self.label:
            return
        if self.direction == 'incoming':
            if self._in_range(tgt):
                self._check_node(ctx, tgt)
        else:
            if self._in_range(src):
                self._check_node(ctx, src)


# ---------------------------------------------------------------------------
# Output formatter
# ---------------------------------------------------------------------------

def print_solution(graph, node_type_of, node_type_ranges, schema):
    print("\n=== Solution ===")
    type_counter = {t: 0 for t in node_type_ranges}
    local_idx = {t: 0 for t in node_type_ranges}

    for node_idx, type_name in enumerate(node_type_of):
        props = {}
        for prop_name in graph.property_specs:
            try:
                val = graph.get_value(node_idx, prop_name)
                if val is not None:
                    props[prop_name] = val
            except ValueError:
                # Not collapsed — shouldn't happen after solve
                domain = graph.domain(node_idx, prop_name)
                nonnull = [v for v in domain if v is not None]
                if nonnull:
                    props[prop_name] = f"[{','.join(str(v) for v in nonnull[:3])}...]"

        node_label = f"{type_name} {local_idx[type_name]}"
        local_idx[type_name] += 1

        if props:
            prop_str = '  '.join(f"{k}={v}" for k, v in props.items())
            print(f"  {node_label}:  {prop_str}")
        else:
            print(f"  {node_label}:  (no WFC properties)")

    print("\n=== Edges ===")
    local_idx = {t: 0 for t in node_type_ranges}
    # Build local index map
    node_local = {}
    cnt = {t: 0 for t in node_type_ranges}
    for node_idx, type_name in enumerate(node_type_of):
        node_local[node_idx] = (type_name, cnt[type_name])
        cnt[type_name] += 1

    for label in graph.edge_labels:
        established = graph.get_established_edges(label)
        for src, tgt in established:
            src_type, src_n = node_local[src]
            tgt_type, tgt_n = node_local[tgt]
            src_str = f"{src_type} {src_n}"
            tgt_str = f"{tgt_type} {tgt_n}"
            print(f"  {label}:  {src_str} → {tgt_str}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Parse a .gwfc file and run WFC to generate a solution."
    )
    ap.add_argument("file", help="Path to .gwfc file")
    ap.add_argument(
        "--count", action="append", metavar="TYPE=N",
        help="Node count per type, e.g. person=5"
    )
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--restarts", type=int, default=100)
    args = ap.parse_args()

    # Read and parse file
    with open(args.file) as f:
        text = f.read()

    tokens = tokenize(text)
    parser = Parser(tokens)
    schema = parser.parse_file()

    # Resolve range constants in property defs (they may be stored as strings)
    for type_name, props in schema.node_types.items():
        for pdef in props:
            if pdef.kind == 'range':
                lo, hi = _resolve_range(pdef.lo, pdef.hi, schema.constants)
                pdef.lo = lo
                pdef.hi = hi

    # Parse --count
    node_counts = {}
    if args.count:
        for item in args.count:
            if '=' not in item:
                ap.error(f"--count must be TYPE=N, got {item!r}")
            t, n = item.split('=', 1)
            node_counts[t.strip()] = int(n.strip())

    # Default count=1 for types without explicit count
    for type_name in schema.node_types:
        if type_name not in node_counts:
            print(
                f"WARNING: No --count for '{type_name}', defaulting to 1.",
                file=sys.stderr,
            )
            node_counts[type_name] = 1

    import random
    rng = random.Random(args.seed)

    graph, constraints, node_type_of, node_type_ranges = build_wfc(
        schema, node_counts, rng
    )

    solver = WFCSolver(graph, constraints, max_restarts=args.restarts, rng=rng)
    success = solver.solve()

    if success:
        print_solution(graph, node_type_of, node_type_ranges, schema)
    else:
        print("FAILED: Could not find a valid solution.", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
