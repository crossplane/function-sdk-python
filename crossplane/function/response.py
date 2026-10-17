# Copyright 2023 The Crossplane Authors.
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

"""Utilities for working with RunFunctionResponses."""

import datetime

from google.protobuf import duration_pb2 as durationpb
from google.protobuf import struct_pb2 as structpb

import crossplane.function.proto.v1.run_function_pb2 as fnv1
from crossplane.function import resource

"""The default TTL for which a RunFunctionResponse may be cached."""
DEFAULT_TTL = datetime.timedelta(minutes=1)

_default_ttl = DEFAULT_TTL


def get_default_ttl() -> datetime.timedelta:
    """Return the process-wide default TTL for RunFunctionResponses."""
    return _default_ttl


def set_default_ttl(ttl: datetime.timedelta) -> None:
    """Set the process-wide default TTL for RunFunctionResponses.

    Args:
        ttl: How long Crossplane may optionally cache responses when no explicit
            TTL is passed to :func:`to`.
    """
    global _default_ttl  # noqa: PLW0603
    _default_ttl = ttl


def to(
    req: fnv1.RunFunctionRequest,
    ttl: datetime.timedelta | None = None,
) -> fnv1.RunFunctionResponse:
    """Create a response to the supplied request.

    Args:
        req: The request to respond to.
        ttl: How long Crossplane may optionally cache the response. Defaults to
            the process-wide default TTL set by :func:`set_default_ttl`.

    Returns:
        A response to the supplied request.

    The request's tag, desired resources, context, and dependencies are
    automatically copied to the response. Using response.to is a good pattern
    to ensure

    Dependencies are copied only if the request has them. An unset
    Dependencies means "no opinion" and tells Crossplane to carry forward the
    constraints it already has, while an empty one tells Crossplane to drop
    them. Copying an unset field as an empty one would turn the former into
    the latter.
    """
    if ttl is None:
        ttl = get_default_ttl()

    dttl = durationpb.Duration()
    dttl.FromTimedelta(ttl)
    return fnv1.RunFunctionResponse(
        meta=fnv1.ResponseMeta(tag=req.meta.tag, ttl=dttl),
        desired=req.desired,
        context=req.context,
        dependencies=req.dependencies if req.HasField("dependencies") else None,
    )


def normal(rsp: fnv1.RunFunctionResponse, message: str) -> None:
    """Add a normal result to the response."""
    rsp.results.append(
        fnv1.Result(
            severity=fnv1.SEVERITY_NORMAL,
            message=message,
        )
    )


def warning(rsp: fnv1.RunFunctionResponse, message: str) -> None:
    """Add a warning result to the response."""
    rsp.results.append(
        fnv1.Result(
            severity=fnv1.SEVERITY_WARNING,
            message=message,
        )
    )


def fatal(rsp: fnv1.RunFunctionResponse, message: str) -> None:
    """Add a fatal result to the response."""
    rsp.results.append(
        fnv1.Result(
            severity=fnv1.SEVERITY_FATAL,
            message=message,
        )
    )


_STATUS_MAP = {
    "True": fnv1.STATUS_CONDITION_TRUE,
    "False": fnv1.STATUS_CONDITION_FALSE,
    "Unknown": fnv1.STATUS_CONDITION_UNKNOWN,
}


def set_conditions(
    rsp: fnv1.RunFunctionResponse,
    *conditions: resource.Condition,
) -> None:
    """Set one or more conditions on the composite resource (XR).

    Args:
        rsp: The RunFunctionResponse to update.
        *conditions: The conditions to set.

    Each condition is appended to ``rsp.conditions``. Crossplane uses the
    conditions returned by a function to set custom status conditions on
    the composite resource.

    The ``last_transition_time`` field of each condition is ignored.
    Crossplane sets the transition time itself.

    Do not set the ``Ready`` condition type. Crossplane manages it based
    on resource readiness.
    """
    for condition in conditions:
        c = fnv1.Condition(
            type=condition.typ,
            status=_STATUS_MAP.get(condition.status, fnv1.STATUS_CONDITION_UNKNOWN),
            reason=condition.reason or "",
        )
        if condition.message:
            c.message = condition.message
        rsp.conditions.append(c)


def set_output(rsp: fnv1.RunFunctionResponse, output: dict | structpb.Struct) -> None:
    """Set the output field in a RunFunctionResponse for operation functions.

    Args:
        rsp: The RunFunctionResponse to update.
        output: The output data as a dictionary or protobuf Struct.

    Operation functions can return arbitrary output data that will be written
    to the Operation's status.pipeline field. This function sets that output
    on the response.
    """
    match output:
        case dict():
            rsp.output.CopyFrom(resource.dict_to_struct(output))
        case structpb.Struct():
            rsp.output.CopyFrom(output)
        case _:
            t = type(output)
            msg = f"Unsupported output type: {t}"
            raise TypeError(msg)


def require_resources(  # noqa: PLR0913
    rsp: fnv1.RunFunctionResponse,
    name: str,
    api_version: str,
    kind: str,
    *,
    match_name: str | None = None,
    match_labels: dict[str, str] | None = None,
    namespace: str | None = None,
) -> None:
    """Add a resource requirement to the response.

    Args:
        rsp: The RunFunctionResponse to update.
        name: The name to use for this requirement.
        api_version: The API version of resources to require.
        kind: The kind of resources to require.
        match_name: Match a resource by name (mutually exclusive with match_labels).
        match_labels: Match resources by labels (mutually exclusive with match_name).
        namespace: The namespace to search in (optional).

    Raises:
        ValueError: If both match_name and match_labels are provided.

    This tells Crossplane to fetch the specified resources and include them
    in the next call to the function in req.required_resources[name].

    If neither match_name nor match_labels is provided, all resources of the
    given api_version and kind are matched.
    """
    if match_name is not None and match_labels is not None:
        msg = "match_name and match_labels are mutually exclusive"
        raise ValueError(msg)

    selector = fnv1.ResourceSelector(
        api_version=api_version,
        kind=kind,
    )

    if match_name is not None:
        selector.match_name = match_name

    if match_labels is not None:
        selector.match_labels.labels.update(match_labels)

    if namespace is not None:
        selector.namespace = namespace

    rsp.requirements.resources[name].CopyFrom(selector)


def require_schema(
    rsp: fnv1.RunFunctionResponse,
    name: str,
    api_version: str,
    kind: str,
) -> None:
    """Add a schema requirement to the response.

    Args:
        rsp: The RunFunctionResponse to update.
        name: The name to use for this requirement.
        api_version: The API version of the resource kind, e.g. "example.org/v1".
        kind: The kind of resource, e.g. "MyResource".

    This tells Crossplane to fetch the OpenAPI schema for the specified resource
    kind and include it in the next call to the function in
    req.required_schemas[name]. Use request.get_required_schema to retrieve it.

    For CRDs, Crossplane returns the spec.versions[].schema.openAPIV3Schema field.
    If Crossplane cannot find a schema for the requested kind, the schema will be
    empty (get_required_schema will return None).
    """
    selector = fnv1.SchemaSelector(
        api_version=api_version,
        kind=kind,
    )
    rsp.requirements.schemas[name].CopyFrom(selector)


def clear_dependencies(rsp: fnv1.RunFunctionResponse) -> None:
    """Declare that no composed resources should be ordered.

    Args:
        rsp: The RunFunctionResponse to update.

    This returns an empty set of dependencies, which tells Crossplane to drop
    the constraints declared by the functions before this one. It's different
    from leaving dependencies unset, which means "no opinion" and carries the
    existing constraints forward.

    Note that response.to copies the request's dependencies to the response.
    Call this on a response it created to drop them.
    """
    rsp.dependencies.Clear()
    rsp.dependencies.SetInParent()


def add_dependency(
    rsp: fnv1.RunFunctionResponse,
    resource_name: str,
    depends_on: str,
    *,
    create_before_destroy: bool = False,
) -> None:
    """Declare that one composed resource depends on another.

    Args:
        rsp: The RunFunctionResponse to update.
        resource_name: Name of the composed resource that has the dependency. A key
            into the desired or observed state's resources.
        depends_on: Name of the composed resource it depends on. Also a key
            into the desired or observed state's resources.
        create_before_destroy: Let the resource be created without waiting for
            what it depends on to be deleted. Use for a replacement that must
            exist before its predecessor is torn down.

    By default ordering is symmetric: the resource is created only once what
    it depends on is ready, and what it depends on is deleted only once the
    resource is gone.

    Dependencies express ordering only. They don't move any data between
    resources.

    Remember that a function must return the full set of dependencies it
    wants. response.to copies forward the ones the request carried, so build
    on a response created by it rather than an empty one.

    Only Crossplane versions that advertise CAPABILITY_DEPENDENCIES honor
    dependencies. Use request.has_capability to check before relying on them:

        if request.has_capability(req, fnv1.CAPABILITY_DEPENDENCIES):
            response.add_dependency(rsp, "database", "network")
    """
    lifecycle = (
        fnv1.DEPENDENCY_LIFECYCLE_CREATE_BEFORE_DESTROY
        if create_before_destroy
        else fnv1.DEPENDENCY_LIFECYCLE_UNSPECIFIED
    )
    rsp.dependencies.items.append(
        fnv1.Dependency(
            resource=resource_name,
            composed_resource=depends_on,
            lifecycle=lifecycle,
        )
    )


def add_required_resource_dependency(
    rsp: fnv1.RunFunctionResponse,
    resource_name: str,
    requirement_name: str,
    *,
    name: str | None = None,
    namespace: str | None = None,
) -> None:
    """Declare that a composed resource depends on a required resource.

    Args:
        rsp: The RunFunctionResponse to update.
        resource_name: Name of the composed resource that has the dependency. A key
            into the desired or observed state's resources.
        requirement_name: The requirement name, as passed to require_resources.
        name: Name of a single resource within the set the requirement
            matched. If unset, every matched resource must be ready.
        namespace: Namespace of name, for a namespaced resource. Leave unset
            for a cluster scoped resource.

    Crossplane never deletes a resource it didn't compose, so a dependency on
    a required resource constrains only the order resources are created and
    updated, never the order they're deleted.
    """
    required = fnv1.RequiredResourceDependency(requirement_name=requirement_name)

    if name is not None:
        required.name = name

    if namespace is not None:
        required.namespace = namespace

    rsp.dependencies.items.append(
        fnv1.Dependency(resource=resource_name, required_resource=required)
    )
