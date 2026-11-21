"""Validating a decoded CBOR record against ``interfaces/records.cddl``.

Why this module exists, and what it does and does not prove
-----------------------------------------------------------
Story P1-03 (S-017) deferred one acceptance criterion to this story: the CDDL
schema must validate a record the simulator produces. A full CDDL validator
would be the obvious way to meet it, but ``pycddl`` (the usual choice) ships no
wheel for the Python version on the development machine and building it needs a
Rust toolchain, so it could not be installed, and a hand-written copy of the
rules in Python would only prove that the copy agrees with itself.

So this module reads ``interfaces/records.cddl`` at runtime, parses it with
``cddlparser`` (pure Python) and interprets the resulting syntax tree. The rules
are never duplicated in Python: change the schema file and the checks change
with it, which is the point of keeping the contract in ``interfaces/``.

What it covers is the subset of CDDL that ``records.cddl`` actually uses: maps
with optional members, arrays with an occurrence, rule references, the prelude
types ``uint``, ``int``, ``bool``, ``tstr`` and ``bstr``, literal values, type
choices, group choices via ``&``, and the ``.size`` control operator with a
plain size or a range. Anything outside that subset raises
:class:`UnsupportedConstruct` when the schema is compiled, so a construct this
interpreter does not understand fails loudly instead of passing silently.

``[Confirm]`` This is therefore schema-driven structural validation, not a
certified CDDL implementation: it is as correct as the subset it implements. If
the project later wants a reference check, run ``records.cddl`` through a full
CDDL tool in CI once one is installable (``pycddl`` with a Rust toolchain, or
the Ruby ``cddl`` gem) and keep this module for the fast in-process check.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import cddlparser
from cddlparser import Tokens, ast

from .interfaces import record_schema_path

# The entry rule every CDDL document starts from.
ROOT_RULE = "start"

# Prelude types this interpreter understands, as predicates on a decoded value.
# bool is excluded from the integer types on purpose: Python's bool is a
# subclass of int, but CBOR keeps them apart and so does the schema.
_PRELUDE: dict[str, Callable[[object], bool]] = {
    "uint": lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 0,
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "nint": lambda v: isinstance(v, int) and not isinstance(v, bool) and v < 0,
    "bool": lambda v: isinstance(v, bool),
    "tstr": lambda v: isinstance(v, str),
    "text": lambda v: isinstance(v, str),
    "bstr": lambda v: isinstance(v, bytes | bytearray),
    "bytes": lambda v: isinstance(v, bytes | bytearray),
    "any": lambda v: True,
}

# Names of the prelude types whose `.size` is measured in units other than
# characters, kept here so the operator does not have to special-case strings.
_SIZED_TYPES = frozenset({"tstr", "text", "bstr", "bytes"})


class SchemaError(ValueError):
    """Raised when a record does not match the schema."""


class UnsupportedConstruct(NotImplementedError):
    """Raised when the schema uses CDDL this interpreter does not implement.

    It is deliberately loud: a construct that is quietly ignored would make the
    validator claim more than it checks.
    """


@dataclass(frozen=True)
class _Member:
    """One named map member compiled from a group entry."""

    key: str
    check: Callable[[object, str], None]
    required: bool


@dataclass(frozen=True)
class _Element:
    """One positional array element compiled from a group entry."""

    check: Callable[[object, str], None]
    minimum: int
    maximum: float


def _occurrence_bounds(entry: ast.GroupEntry) -> tuple[int, float]:
    """The ``n..m`` bounds of a group entry's occurrence indicator.

    ``?`` is read as 0..1 rather than from the parsed bounds: the parser reports
    it as 0..infinity, which would make an optional member indistinguishable
    from a wildcard one.
    """
    occurrence = entry.occurrence
    if occurrence is None:
        return (1, 1)
    kinds = {token.type for token in occurrence.tokens}
    if Tokens.QUEST in kinds:
        return (0, 1)
    if Tokens.PLUS in kinds:
        return (1, float("inf"))
    minimum = 0 if occurrence.n is None else int(occurrence.n)
    maximum = float("inf") if occurrence.m is None else float(occurrence.m)
    return (minimum, maximum)


def _member_key(entry: ast.GroupEntry) -> str:
    key = entry.key
    if key is None:  # pragma: no cover - guarded by the caller
        raise UnsupportedConstruct("a map entry without a member key is not supported")
    if not isinstance(key.type, ast.Typename):
        raise UnsupportedConstruct(f"unsupported member key {type(key.type).__name__}")
    return key.type.name


def _group_entries(node: ast.Map | ast.Array | ast.Group) -> list[ast.GroupEntry]:
    choices = node.groupChoices
    if len(choices) != 1:
        raise UnsupportedConstruct("a group with alternative choices is not supported")
    return list(choices[0].groupEntries)


def _literal_value(node: ast.Value) -> object:
    if node.type == "number":
        text = node.value
        return float(text) if ("." in text or "e" in text.lower()) else int(text)
    if node.type == "text":
        return node.value
    raise UnsupportedConstruct(f"unsupported literal type {node.type!r}")


class Schema:
    """A compiled view of a CDDL document.

    Compilation happens once, in :meth:`from_file`, so an unsupported construct
    is reported before any record is validated rather than on the record that
    happens to reach it.
    """

    def __init__(self, text: str, source: str = "<string>") -> None:
        self._source = source
        self._tree = cddlparser.parse(text)
        self._rules: dict[str, ast.Rule] = {}
        for rule in self._tree.rules:
            self._rules[rule.name.name] = rule
        self._compiled: dict[str, Callable[[object, str], None]] = {}
        # Compile the whole document now so unsupported CDDL fails early.
        for name in self._rules:
            if not self._is_group_rule(name):
                self._rule_checker(name)

    @classmethod
    def from_file(cls, path: Path | None = None) -> Schema:
        """Compile the record schema, by default the one in ``interfaces/``."""
        schema_path = path or record_schema_path()
        return cls(schema_path.read_text(encoding="utf-8"), source=str(schema_path))

    @property
    def source(self) -> str:
        """Where the schema was read from, for error messages."""
        return self._source

    @property
    def rule_names(self) -> tuple[str, ...]:
        """Every rule name in the document, in file order."""
        return tuple(self._rules)

    # -- public checking ---------------------------------------------------

    def validate(self, value: object, rule: str = ROOT_RULE) -> None:
        """Raise :class:`SchemaError` unless ``value`` matches ``rule``."""
        self._rule_checker(rule)(value, rule)

    def matches(self, value: object, rule: str = ROOT_RULE) -> bool:
        """Return whether ``value`` matches ``rule``, without raising."""
        try:
            self.validate(value, rule)
        except SchemaError:
            return False
        return True

    def enum_values(self, rule: str) -> Mapping[str, object]:
        """Return the name-to-value mapping of a group used as an enumeration.

        ``quality = &quality-values`` in the schema turns the group's members
        into the set of allowed values. Reading them from the schema keeps the
        quality codes out of Python, where they would be a second definition.
        """
        group = self._find_group(self._require_rule(rule))
        values: dict[str, object] = {}
        for entry in _group_entries(group):
            values[_member_key(entry)] = _literal_value(self._single_type2(entry.type))
        return values

    # -- rule resolution ---------------------------------------------------

    def _require_rule(self, name: str) -> ast.Rule:
        try:
            return self._rules[name]
        except KeyError:
            raise SchemaError(f"{self._source} has no rule named {name!r}") from None

    def _is_group_rule(self, name: str) -> bool:
        """True for a rule that defines a group, which is not a type on its own."""
        return isinstance(self._rules[name].type, ast.GroupEntry)

    def _rule_checker(self, name: str) -> Callable[[object, str], None]:
        if name in self._compiled:
            return self._compiled[name]
        rule = self._require_rule(name)
        if self._is_group_rule(name):
            raise UnsupportedConstruct(f"rule {name!r} defines a group, not a type")

        # Placed before compiling so a recursive rule reference resolves.
        def deferred(value: object, path: str) -> None:
            self._compiled[name](value, path)

        self._compiled[name] = deferred
        compiled = self._compile_type(rule.type)
        self._compiled[name] = compiled
        return compiled

    def _find_group(self, rule: ast.Rule) -> ast.Group:
        node: object = rule.type
        if isinstance(node, ast.GroupEntry):
            node = node.type
        if isinstance(node, ast.Type):
            node = self._single_type2(node)
        # A map and an array are both groups in the syntax tree, so the check
        # is on the exact type: only a bare group can be used as an enumeration.
        if type(node) is not ast.Group:
            raise UnsupportedConstruct(f"rule {rule.name.name!r} is not a group")
        return node

    @staticmethod
    def _single_type2(node: ast.Type) -> ast.Type2:
        if not isinstance(node, ast.Type):
            raise UnsupportedConstruct(f"expected a type, got {type(node).__name__}")
        if len(node.types) != 1:
            raise UnsupportedConstruct("expected a single type, got a choice")
        return node.types[0]

    # -- compilation -------------------------------------------------------

    def _compile_type(self, node: object) -> Callable[[object, str], None]:
        """Compile a type, which may be a choice of alternatives."""
        if isinstance(node, ast.Type):
            checks = [self._compile_type2(t) for t in node.types]
            if len(checks) == 1:
                return checks[0]

            def check_choice(value: object, path: str) -> None:
                for check in checks:
                    try:
                        check(value, path)
                    except SchemaError:
                        continue
                    return
                raise SchemaError(f"{path}: {value!r} matches none of the allowed types")

            return check_choice
        return self._compile_type2(node)

    def _compile_type2(self, node: object) -> Callable[[object, str], None]:
        if isinstance(node, ast.Typename):
            return self._compile_typename(node)
        if isinstance(node, ast.Value):
            return self._compile_literal(node)
        if isinstance(node, ast.Map):
            return self._compile_map(node)
        if isinstance(node, ast.Array):
            return self._compile_array(node)
        if isinstance(node, ast.ChoiceFrom):
            return self._compile_choice_from(node)
        if isinstance(node, ast.Operator):
            return self._compile_operator(node)
        if isinstance(node, ast.Range):
            return self._compile_range(node)
        raise UnsupportedConstruct(f"unsupported CDDL construct {type(node).__name__}")

    def _compile_typename(self, node: ast.Typename) -> Callable[[object, str], None]:
        name = node.name
        if node.parameters is not None:
            raise UnsupportedConstruct(f"generic parameters on {name!r} are not supported")
        if node.unwrapped:
            raise UnsupportedConstruct(f"the unwrap operator on {name!r} is not supported")
        predicate = _PRELUDE.get(name)
        if predicate is not None:

            def check_prelude(value: object, path: str) -> None:
                if not predicate(value):
                    raise SchemaError(f"{path}: expected {name}, got {value!r}")

            return check_prelude

        def check_rule(value: object, path: str) -> None:
            self._rule_checker(name)(value, path)

        # Compile the referenced rule now so an unsupported construct inside it
        # is reported at compile time.
        self._rule_checker(name)
        return check_rule

    @staticmethod
    def _compile_literal(node: ast.Value) -> Callable[[object, str], None]:
        expected = _literal_value(node)

        def check_literal(value: object, path: str) -> None:
            if isinstance(value, bool) or value != expected:
                raise SchemaError(f"{path}: expected the literal {expected!r}, got {value!r}")

        return check_literal

    def _compile_range(self, node: ast.Range) -> Callable[[object, str], None]:
        low = _literal_value(node.min)
        high = _literal_value(node.max)
        inclusive = node.rangeop.type is Tokens.INCLRANGE
        if not inclusive and node.rangeop.type is not Tokens.EXCLRANGE:
            raise UnsupportedConstruct(f"unsupported range operator {node.rangeop.type}")
        span = f"{low}{'..' if inclusive else '...'}{high}"

        def check_range(value: object, path: str) -> None:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise SchemaError(f"{path}: expected a number in {span}, got {value!r}")
            if value < low or (value > high if inclusive else value >= high):
                raise SchemaError(f"{path}: {value!r} is outside {span}")

        return check_range

    def _compile_operator(self, node: ast.Operator) -> Callable[[object, str], None]:
        operator = node.name.literal
        if operator != "size":
            raise UnsupportedConstruct(f"control operator .{operator} is not supported")
        if not isinstance(node.type, ast.Typename) or node.type.name not in _SIZED_TYPES:
            raise UnsupportedConstruct(".size is only supported on a text or byte string")
        base = self._compile_type2(node.type)
        size_check = self._compile_type(node.controller)

        def check_size(value: object, path: str) -> None:
            base(value, path)
            size_check(len(value), f"{path}.size")  # type: ignore[arg-type]

        return check_size

    def _compile_choice_from(self, node: ast.ChoiceFrom) -> Callable[[object, str], None]:
        if not isinstance(node.target, ast.Typename):
            raise UnsupportedConstruct("& is only supported on a named group")
        allowed = tuple(self.enum_values(node.target.name).values())

        def check_choice_from(value: object, path: str) -> None:
            if isinstance(value, bool) or value not in allowed:
                raise SchemaError(f"{path}: {value!r} is not one of {allowed}")

        return check_choice_from

    def _compile_map(self, node: ast.Map) -> Callable[[object, str], None]:
        members: list[_Member] = []
        for entry in _group_entries(node):
            if entry.key is None:
                raise UnsupportedConstruct("a map entry without a member key is not supported")
            minimum, maximum = _occurrence_bounds(entry)
            if minimum > 1 or maximum != 1:
                # `* keytype => valuetype` and `2* a: int` both land here. The
                # schema uses neither; accepting them silently would mean not
                # checking them.
                raise UnsupportedConstruct("a repeated or wildcard map member is not supported")
            members.append(
                _Member(
                    key=_member_key(entry),
                    check=self._compile_type(entry.type),
                    required=minimum >= 1,
                )
            )
        known = {member.key for member in members}

        def check_map(value: object, path: str) -> None:
            if not isinstance(value, Mapping):
                raise SchemaError(f"{path}: expected a map, got {type(value).__name__}")
            for member in members:
                if member.key in value:
                    member.check(value[member.key], f"{path}.{member.key}")
                elif member.required:
                    raise SchemaError(f"{path}: required member {member.key!r} is missing")
            # A CDDL map is closed unless it declares a wildcard entry, which
            # this schema does not, so an unexpected key is an error.
            extra = sorted(set(value) - known)
            if extra:
                raise SchemaError(f"{path}: unexpected member(s) {extra}")

        return check_map

    def _compile_array(self, node: ast.Array) -> Callable[[object, str], None]:
        elements: list[_Element] = []
        for entry in _group_entries(node):
            if entry.key is not None:
                raise UnsupportedConstruct("a keyed entry inside an array is not supported")
            minimum, maximum = _occurrence_bounds(entry)
            elements.append(
                _Element(check=self._compile_type(entry.type), minimum=minimum, maximum=maximum)
            )

        def check_array(value: object, path: str) -> None:
            if isinstance(value, str | bytes | bytearray) or not isinstance(value, Sequence):
                raise SchemaError(f"{path}: expected an array, got {type(value).__name__}")
            index = 0
            for position, element in enumerate(elements):
                taken = 0
                while index < len(value) and taken < element.maximum:
                    try:
                        element.check(value[index], f"{path}[{index}]")
                    except SchemaError:
                        break
                    index += 1
                    taken += 1
                if taken < element.minimum:
                    # Re-run the failing check so the caller sees why.
                    if index < len(value):
                        element.check(value[index], f"{path}[{index}]")
                    raise SchemaError(
                        f"{path}: element {position} needs at least {element.minimum} "
                        f"occurrence(s), found {taken}"
                    )
            if index != len(value):
                raise SchemaError(f"{path}: {len(value) - index} unexpected trailing element(s)")

        return check_array


def load_schema(path: Path | None = None) -> Schema:
    """Compile the record schema from ``interfaces/records.cddl``."""
    return Schema.from_file(path)
