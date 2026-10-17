# Copyright 2026 The Crossplane Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Dependencies declared by referring to another resource's fields.

Providers resolve cross-resource references themselves, through fields like
vpcIdRef and vpcIdSelector that the provider turns into a value at reconcile
time. That works, but Crossplane never sees the relationship: it can't order
anything, and a provider that can't resolve a reference yet retries against
the cloud API until it can.

Reading the value through this module instead makes the relationship
visible. The function says where a value comes from, the SDK records the
dependency, and Crossplane waits rather than letting the provider discover
the problem:

    from crossplane.function import dependency

    vpc = dependency.named("vpc", VPC)

    with dependency.composing(req, rsp, "subnet") as c:
        c.update(
            Subnet(
                spec={
                    "forProvider": {
                        "region": "us-east-1",
                        "vpcId": c.external_name(vpc),  # instead of vpcIdSelector
                        "cidrBlock": c.ref(vpc.spec.forProvider.cidrBlock),
                    }
                }
            )
        )

composing scopes the work to one composed resource. Within it, c.ref and
c.external_name return the value itself, or None while it isn't available,
and the scope records that the resource depends on where each value came
from when the block exits.

Dependencies order resources only on a Crossplane that advertises
CAPABILITY_DEPENDENCIES. On any other, a resource whose value isn't available
yet is held back by leaving it out of desired state, but nothing waits for a
source to be ready, and nothing orders deletion.
"""

import contextlib
import types
import typing

import pydantic
from google.protobuf import struct_pb2 as structpb

from crossplane.function import request, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

_EXTERNAL_NAME = "@externalName"
_EXTERNAL_NAME_ANNOTATION = "crossplane.io/external-name"

CONDITION_TYPE = "DependencyValuesAvailable"
"""The XR condition composing reports whether any resource was kept.

False while a resource was kept at its current spec because a value it's
built from isn't available, naming each one. True otherwise.
"""

_COMPOSED = "composed"
_REQUIRED = "required"

M = typing.TypeVar("M", bound=pydantic.BaseModel)
V = typing.TypeVar("V")


class _Source(typing.NamedTuple):
    """The resource a reference points at."""

    kind: str  # _COMPOSED or _REQUIRED.
    name: str  # A composed resource name, or a requirement name.
    resource_name: str | None = None  # Required only: one of the matches.
    namespace: str | None = None  # Required only: namespace of resource_name.

    def describe(self) -> str:
        if self.kind == _COMPOSED:
            return self.name
        s = f"requirement {self.name}"
        if self.resource_name:
            ns = f"{self.namespace}/" if self.namespace else ""
            s += f" ({ns}{self.resource_name})"
        return s


class _Field:
    """A stand-in for a resource, or a field of one, that records its path.

    Reading an attribute or an item returns another stand-in one step deeper.
    Given the resource's model it follows the model's own fields, so a typo
    fails here rather than producing a reference to nothing, and a field whose
    JSON name isn't a valid Python name (from, class) is recorded under its
    JSON name.

    It deliberately has no value. Anything that would need one - a truth
    test, str(), iteration - raises, because code that branches on a field
    that doesn't exist yet would otherwise take the wrong branch silently.
    """

    __slots__ = ("_model", "_path", "_source")

    def __init__(self, source: _Source, path: tuple, model: typing.Any = None):
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_model", model)

    def __getattr__(self, attr: str) -> "_Field":
        # Dunder lookups come from copy, pickle, pydantic and friends probing
        # for protocols. Answering them would make a stand-in look like it
        # supports things it doesn't.
        if attr.startswith("__"):
            raise AttributeError(attr)

        key, model = _field_of(self._model, attr, self._describe())
        return _Field(self._source, (*self._path, key), model)

    def __getitem__(self, key: str | int) -> "_Field":
        return _Field(self._source, (*self._path, key), _item_of(self._model))

    def __setattr__(self, attr: str, value: typing.Any) -> None:
        msg = f"cannot set {attr} on {self._describe()}: references are read-only"
        raise AttributeError(msg)

    def __bool__(self) -> bool:
        msg = (
            f"{self._describe()} has no value yet. Read it with c.ref() inside "
            "dependency.composing(), and branch on what that returns."
        )
        raise TypeError(msg)

    def __iter__(self) -> typing.NoReturn:
        msg = f"cannot iterate {self._describe()}; index it instead, e.g. [0]"
        raise TypeError(msg)

    def __str__(self) -> str:
        msg = f"{self._describe()} has no value yet. Read it with c.ref()."
        raise TypeError(msg)

    def __repr__(self) -> str:
        return f"<reference to {self._describe()}>"

    def _describe(self) -> str:
        path = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in self._path)
        return f"{self._source.describe()}{path}"


def _unwrap(annotation: typing.Any) -> typing.Any:
    """Strip Optional, unions with None, and Annotated from a field's type."""
    while True:
        origin = typing.get_origin(annotation)
        if origin is typing.Annotated:
            annotation = typing.get_args(annotation)[0]
            continue
        if origin in (typing.Union, types.UnionType):
            args = [a for a in typing.get_args(annotation) if a is not type(None)]
            if len(args) == 1:
                annotation = args[0]
                continue
        return annotation


def _is_model(t: typing.Any) -> bool:
    return isinstance(t, type) and issubclass(t, pydantic.BaseModel)


def _field_of(model: typing.Any, attr: str, where: str) -> tuple[str, typing.Any]:
    """Return the JSON key for attr on model, and the type of that field.

    Without a model there is nothing to check against, so the attribute is the
    key and the result is untyped.
    """
    if not _is_model(model):
        return attr, None

    fields = model.model_fields
    if attr in fields:
        info = fields[attr]
        return info.alias or attr, _unwrap(info.annotation)

    # Accept the JSON name too, so from and from_ both work.
    for info in fields.values():
        if info.alias == attr:
            return attr, _unwrap(info.annotation)

    msg = f"{where} has no field {attr!r}; {model.__name__} has {', '.join(fields)}"
    raise AttributeError(msg)


def _item_of(model: typing.Any) -> typing.Any:
    """Return the element type of a list or dict type, if it has one."""
    origin, args = typing.get_origin(model), typing.get_args(model)
    if origin is list and args:
        return _unwrap(args[0])
    if origin is dict and len(args) == 2:  # noqa: PLR2004
        return _unwrap(args[1])
    return None


@typing.overload
def named(name: str, model: type[M]) -> M: ...
@typing.overload
def named(name: str, model: None = None) -> typing.Any: ...
def named(name: str, model: type[M] | None = None) -> typing.Any:
    """Name a composed resource so its fields can be referenced.

    Args:
        name: The composed resource's name, the key into desired and observed
            state.
        model: The resource's generated model, if it has one. Fields are then
            checked against it as they're read, and editors can complete them.

    Returns:
        A stand-in that reads like the resource itself:

            vpc = dependency.named("vpc", VPC)

            with dependency.composing(req, rsp, "subnet") as c:
                vpc_id = c.ref(vpc.status.atProvider.id)
    """
    return _Field(_Source(_COMPOSED, name), (), model)


@typing.overload
def named_required(
    requirement_name: str,
    model: type[M],
    *,
    name: str | None = None,
    namespace: str | None = None,
) -> M: ...
@typing.overload
def named_required(
    requirement_name: str,
    model: None = None,
    *,
    name: str | None = None,
    namespace: str | None = None,
) -> typing.Any: ...
def named_required(
    requirement_name: str,
    model: type[M] | None = None,
    *,
    name: str | None = None,
    namespace: str | None = None,
) -> typing.Any:
    """Name a resource the function requires but doesn't compose.

    Args:
        requirement_name: The requirement name, as passed to
            response.require_resources.
        model: The resource's generated model, if it has one.
        name: Name of one resource the requirement matched. Needed when it
            can match more than one; a reference declines to guess.
        namespace: Namespace of name, for a namespaced resource.

    Returns:
        A stand-in that reads like the resource itself.

    Crossplane never deletes a resource it didn't compose, so the dependency
    this records orders only creation and updates.
    """
    return _Field(_Source(_REQUIRED, requirement_name, name, namespace), (), model)


_MISSING = object()


def _value_at(obj: typing.Any, path: list) -> typing.Any:
    for key in path:
        if isinstance(key, int):
            if not isinstance(obj, list) or not -len(obj) <= key < len(obj):
                return _MISSING
            obj = obj[key]
        elif isinstance(obj, dict) and key in obj:
            obj = obj[key]
        else:
            return _MISSING
    return obj


def _lookup(req: fnv1.RunFunctionRequest, s: _Source) -> typing.Any:
    """Return the resource a reference points at, or _MISSING."""
    if s.kind == _COMPOSED:
        if s.name not in req.observed.resources:
            return _MISSING
        return resource.struct_to_dict(req.observed.resources[s.name].resource)

    items = request.get_required_resources(req, s.name)
    if s.resource_name is None:
        # With several matches and nothing to pick by there is no right
        # answer, so decline rather than guess.
        return items[0] if len(items) == 1 else _MISSING
    for item in items:
        meta = item.get("metadata", {})
        if meta.get("name") == s.resource_name and (
            s.namespace is None or meta.get("namespace") == s.namespace
        ):
            return item
    return _MISSING


def _read(req: fnv1.RunFunctionRequest, s: _Source, path: list) -> typing.Any:
    """Return the value a reference points at, or _MISSING if there isn't one."""
    src = _lookup(req, s)
    if src is _MISSING:
        return _MISSING
    if path == [_EXTERNAL_NAME]:
        v = _value_at(src, ["metadata", "annotations", _EXTERNAL_NAME_ANNOTATION])
        if v is _MISSING:
            v = _value_at(src, ["metadata", "name"])
    else:
        v = _value_at(src, path)
    return _MISSING if v is None else v


def _record(
    rsp: fnv1.RunFunctionResponse, name: str, sources: typing.Iterable[_Source]
) -> None:
    """Add a dependency of name on each source, skipping any already declared."""
    declared = {
        (d.resource, d.WhichOneof("depends_on"), _target(d))
        for d in rsp.dependencies.items
    }
    for s in sorted(sources, key=lambda s: tuple(p or "" for p in s)):
        if s.kind == _COMPOSED:
            key = (name, "composed_resource", s.name)
            if s.name == name or key in declared:
                continue
            response.add_dependency(rsp, name, s.name)
        else:
            key = (name, "required_resource", (s.name, s.resource_name, s.namespace))
            if key in declared:
                continue
            response.add_required_resource_dependency(
                rsp, name, s.name, name=s.resource_name, namespace=s.namespace
            )
        declared.add(key)


def _target(d: fnv1.Dependency) -> typing.Any:
    if d.WhichOneof("depends_on") == "required_resource":
        r = d.required_resource
        return (
            r.requirement_name,
            r.name if r.HasField("name") else None,
            r.namespace if r.HasField("namespace") else None,
        )
    return d.composed_resource


class Scope:
    """Resolves references for one composed resource as they're read.

    Get one from composing. The scope knows which resource is asking, so a
    reference resolves to its value as soon as it's read, in a field of any
    type, and the scope records the dependency.
    """

    def __init__(
        self, req: fnv1.RunFunctionRequest, rsp: fnv1.RunFunctionResponse, name: str
    ):
        """Create a Scope. Use composing rather than calling this directly."""
        self.req = req
        self.rsp = rsp
        self.name = name
        self._sources: set[_Source] = set()
        self._unresolved: list[str] = []
        self._kept = False

    def ref(self, value: V) -> V:
        """Read a field of a named resource, and depend on that resource.

        Args:
            value: A field read through a stand-in from named or
                named_required, for example vpc.status.atProvider.id.

        Returns:
            The field's observed value, or None if it isn't available yet.
            None leaves the field out when the model is written to desired
            state, and the dependency means Crossplane doesn't create this
            resource until the value exists.

            A resource named with its model returns the value as the model
            types it: a nested object comes back as its model, and a list of
            them as a list of models, rather than as the JSON observed state
            stores. Without a model the value is the JSON.

        Raises:
            TypeError: value isn't a field of a named resource.
            ValueError: value is the whole resource rather than a field of
                it, or the observed value doesn't fit the model's type for it.
        """
        if not isinstance(value, _Field):
            msg = (
                "ref() expects a field of a resource from named() or named_required(), "
                "for example c.ref(vpc.status.atProvider.id), "
                f"not {type(value).__name__}"
            )
            raise TypeError(msg)
        if not value._path:
            msg = (
                f"ref() needs a field, not the whole {value._describe()} resource. "
                "Use external_name() to reference its external name."
            )
            raise ValueError(msg)
        v = self._get(value._source, list(value._path), value._describe())
        if v is None or value._model is None:
            return typing.cast(V, v)
        try:
            return typing.cast(V, pydantic.TypeAdapter(value._model).validate_python(v))
        except pydantic.ValidationError as e:
            msg = f"{value._describe()} doesn't match its model: {e}"
            raise ValueError(msg) from e

    def external_name(self, named_resource: typing.Any) -> str | None:
        """Read a named resource's external name, and depend on that resource.

        Args:
            named_resource: A stand-in from named or named_required.

        Returns:
            The external name, or None if the resource doesn't exist yet.

        Raises:
            TypeError: named_resource isn't a stand-in for a resource.
        """
        if not isinstance(named_resource, _Field) or named_resource._path:
            msg = "external_name() expects a resource from named() or named_required()"
            raise TypeError(msg)
        return self._get(
            named_resource._source,
            [_EXTERNAL_NAME],
            f"{named_resource._describe()} external name",
        )

    def update(self, source: dict | structpb.Struct | pydantic.BaseModel) -> None:
        """Write this scope's composed resource to desired state.

        Args:
            source: The resource, as resource.update accepts it.

        Writing it with resource.update, or any helper that calls it, works
        the same way.
        """
        resource.update(self.rsp.desired.resources[self.name], source)

    def _get(self, s: _Source, path: list, what: str) -> typing.Any:
        self._sources.add(s)
        v = _read(self.req, s, path)
        if v is _MISSING:
            self._unresolved.append(what)
            return None
        return v

    def _close(self) -> None:
        exists = self.name in self.req.observed.resources

        # In a scope None is what a reference returns for a value that isn't
        # available yet, and sending it would ask the API server to clear the
        # field. Strip it however the resource was written: through c.update,
        # resource.update, or a helper that calls it.
        if self.name in self.rsp.desired.resources:
            r = self.rsp.desired.resources[self.name]
            body = resource.struct_to_dict(r.resource)
            cleaned = _without_none(body)
            if cleaned != body:
                r.resource.CopyFrom(resource.dict_to_struct(cleaned))

        if self._unresolved:
            if exists:
                self._keep_current_spec()
            elif not request.has_capability(self.req, fnv1.CAPABILITY_DEPENDENCIES):
                # Crossplane won't create the resource until the dependency
                # is ready. One that doesn't enforce dependencies would create
                # it without the field, so hold it back by leaving it out.
                self.rsp.desired.resources.pop(self.name, None)

        # Declare dependencies only for a resource that's composed or exists.
        # A scope that composed nothing has nothing to order, and Crossplane
        # would ignore the dependencies, with an event saying so.
        if self.name in self.rsp.desired.resources or exists:
            _record(self.rsp, self.name, self._sources)

        _report(self.rsp, self.name, self._unresolved if self._kept else [])

    def _keep_current_spec(self) -> None:
        """Keep an existing resource's spec while a reference it needs is gone.

        The fields that refer to what's missing came back None and were left
        out, and applying that would unset them. A function that didn't
        compose the resource at all, because the value it needed wasn't
        there, would have it deleted. Either way, keep what the resource
        already has for anything this function doesn't set, and say so in
        the CONDITION_TYPE condition.
        """
        observed = resource.struct_to_dict(
            self.req.observed.resources[self.name].resource
        )
        if self.name in self.rsp.desired.resources:
            r = self.rsp.desired.resources[self.name]
            body = resource.struct_to_dict(r.resource)
            if "spec" in observed:
                body["spec"] = _overlay(observed["spec"], body.get("spec", {}))
            r.resource.CopyFrom(resource.dict_to_struct(body))
        else:
            meta = observed.get("metadata", {})
            body = {
                "apiVersion": observed.get("apiVersion"),
                "kind": observed.get("kind"),
                "metadata": {k: meta[k] for k in ("name", "namespace") if k in meta},
            }
            if "spec" in observed:
                body["spec"] = observed["spec"]
            resource.update(self.rsp.desired.resources[self.name], body)

        self._kept = True


def _report(rsp: fnv1.RunFunctionResponse, name: str, missing: list[str]) -> None:
    """Report on CONDITION_TYPE for one scope.

    Every scope reports, so the condition is always returned: Crossplane
    keeps a condition a function set earlier until the function sets it
    again, so one returned only while something was kept would stay False
    after it recovered. Scopes in one function share the condition, which
    turns False on the first that kept its resource and names each.

    The message is built from resource names and field paths only, so it
    holds still while the situation does. Crossplane then leaves the
    condition alone, where a result would be an event every reconcile.
    """
    c = next((c for c in rsp.conditions if c.type == CONDITION_TYPE), None)
    if c is None:
        c = rsp.conditions.add(
            type=CONDITION_TYPE, status=fnv1.STATUS_CONDITION_TRUE, reason="Available"
        )

    if not missing:
        return

    line = f"{name} kept its current spec: {', '.join(missing)} isn't available"
    if c.status == fnv1.STATUS_CONDITION_TRUE:
        c.status = fnv1.STATUS_CONDITION_FALSE
        c.reason = "KeptCurrentSpec"
        c.message = line
    else:
        c.message = f"{c.message}; {line}"


def _without_none(v: typing.Any) -> typing.Any:
    """Return v with every None value left out, recursing into dicts and lists."""
    if isinstance(v, dict):
        return {k: _without_none(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_without_none(x) for x in v if x is not None]
    return v


def _overlay(base: dict, top: dict) -> dict:
    """Return base with top written over it, recursing into nested dicts."""
    out = dict(base)
    for k, v in top.items():
        out[k] = (
            _overlay(out[k], v)
            if isinstance(v, dict) and isinstance(out.get(k), dict)
            else v
        )
    return out


@contextlib.contextmanager
def composing(
    req: fnv1.RunFunctionRequest, rsp: fnv1.RunFunctionResponse, name: str
) -> typing.Iterator[Scope]:
    """Compose one resource, depending on whatever it reads from others.

    Args:
        req: The RunFunctionRequest, whose observed and required resources
            references are read from.
        rsp: The RunFunctionResponse to update.
        name: The composed resource being built, a key into desired state.

    Yields:
        A Scope whose ref and external_name return real values, and record
        that this resource depends on the resources they came from:

            vpc = dependency.named("vpc", VPC)

            with dependency.composing(req, rsp, "subnet") as c:
                c.update(Subnet(spec={"forProvider": {
                    "region": "us-east-1",
                    "vpcId": c.external_name(vpc),
                    "mapPublicIpOnLaunch": c.ref(vpc.spec.forProvider.enableDnsSupport),
                }}))

    The dependencies are recorded when the block exits, so an exception
    inside it records nothing.

    A value that isn't available yet comes back as None, and the field is left
    out: when the block exits, None fields are removed from the resource
    however it was written, because sending one would clear the field. If the
    resource doesn't exist yet that's what ordering is for: Crossplane waits
    for the dependency before creating it. If it does exist, it keeps its
    current spec for the fields that were left out, and the XR's
    DependencyValuesAvailable condition turns False, saying why. That holds
    even if the block doesn't compose the resource at all because the value it
    needed is missing: an existing resource is kept rather than deleted.

    Dependencies are declared only for a resource that's composed or already
    exists. A block that composes nothing declares nothing.
    """
    scope = Scope(req, rsp, name)
    yield scope
    scope._close()
