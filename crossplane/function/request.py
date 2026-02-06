# Copyright 2025 The Crossplane Authors.
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

"""Utilities for working with RunFunctionRequests."""

import dataclasses

import crossplane.function.proto.v1.run_function_pb2 as fnv1
from crossplane.function import resource


@dataclasses.dataclass
class Credentials:
    """Credentials."""

    type: str
    data: dict


def get_required_resources(req: fnv1.RunFunctionRequest, name: str) -> list[dict]:
    """Get required resources by name from the request.

    Args:
        req: The RunFunctionRequest containing required resources.
        name: The name of the required resource set to get.

    Returns:
        A list of resources as dictionaries. Empty list if not found.

    Required resources are previously called "extra resources" in composition
    functions. For operation functions, there are no observed resources, so
    all resources are "required" resources that the function requested.

    Note: This returns an empty list both when the requirement hasn't been
    resolved yet, and when it was resolved but no resources matched. To
    distinguish between these cases, check whether Crossplane resolved the
    requirement using `name in req.required_resources`:

        # Always declare requirements - Crossplane considers them satisfied
        # when they stabilize across calls.
        response.require_resources(rsp, name, ...)

        if name in req.required_resources:
            resources = request.get_required_resources(req, name)
            if not resources:
                # Crossplane resolved the requirement, but found no matches
                response.fatal(rsp, "no matching resources found")
    """
    if name not in req.required_resources:
        return []

    return [
        resource.struct_to_dict(item.resource)
        for item in req.required_resources[name].items
    ]


def get_watched_resource(req: fnv1.RunFunctionRequest) -> dict | None:
    """Get the watched resource that triggered this operation.

    Args:
        req: The RunFunctionRequest to check for a watched resource.

    Returns:
        The watched resource as a dictionary, or None if not found.

    When a WatchOperation creates an Operation, it injects the resource that
    changed using the special requirement name 'ops.crossplane.io/watched-resource'.
    This helper makes it easy to access that resource.
    """
    watched = get_required_resources(req, "ops.crossplane.io/watched-resource")
    return watched[0] if watched else None


def get_required_resource(req: fnv1.RunFunctionRequest, name: str) -> dict | None:
    """Get a single required resource by name from the request.

    Args:
        req: The RunFunctionRequest containing required resources.
        name: The name of the required resource to get.

    Returns:
        The first resource as a dictionary, or None if not found.

    This is a convenience function for when you know there should be exactly
    one resource with the given requirement name.
    """
    resources = get_required_resources(req, name)
    return resources[0] if resources else None


def get_credentials(req: fnv1.RunFunctionRequest, name: str) -> Credentials:
    """Get the supplied credentials from the request.

    Args:
        req: The RunFunctionRequest containing credentials.
        name: The name of the credentials to get.

    Returns:
        The requested credentials with type and data.

    If the credentials don't exist, returns empty credentials with type "data"
    and empty data dictionary.
    """
    empty = Credentials(type="data", data={})

    if not req or name not in req.credentials:
        return empty

    cred = req.credentials[name]

    # Use WhichOneof to determine which field in the oneof is set
    source_type = cred.WhichOneof("source")
    if source_type == "credential_data":
        # Convert bytes data to string data for backward compatibility
        data = {}
        for key, value in cred.credential_data.data.items():
            data[key] = value.decode("utf-8")
        return Credentials(type="credential_data", data=data)

    # If no recognized source type is set, return empty
    return empty


def advertises_capabilities(req: fnv1.RunFunctionRequest) -> bool:
    """Check whether Crossplane advertises its capabilities.

    Args:
        req: The RunFunctionRequest to check.

    Returns:
        True if Crossplane advertises its capabilities.

    Crossplane v2.2 and later advertise their capabilities in the request
    metadata. If this returns False, the calling Crossplane predates capability
    advertisement and has_capability will always return False, even for features
    the older Crossplane does support.

        if not request.advertises_capabilities(req):
            # Pre-v2.2 Crossplane, capabilities are unknown.
            ...
        elif request.has_capability(req, fnv1.CAPABILITY_REQUIRED_SCHEMAS):
            response.require_schema(rsp, "xr", xr_api_version, xr_kind)
    """
    return fnv1.CAPABILITY_CAPABILITIES in req.meta.capabilities


def has_capability(
    req: fnv1.RunFunctionRequest,
    cap: fnv1.Capability.ValueType,
) -> bool:
    """Check whether Crossplane advertises a particular capability.

    Args:
        req: The RunFunctionRequest to check.
        cap: The capability to check for, e.g. fnv1.CAPABILITY_REQUIRED_SCHEMAS.

    Returns:
        True if the capability is present in the request metadata.

    Crossplane sends its capabilities in the request metadata. Functions can use
    this to determine whether Crossplane will honor certain fields in their
    response, or populate certain fields in their request.

    Use advertises_capabilities to check whether Crossplane advertises its
    capabilities at all. If it doesn't, has_capability always returns False even
    for features the older Crossplane does support.

        if request.has_capability(req, fnv1.CAPABILITY_REQUIRED_SCHEMAS):
            response.require_schema(rsp, "xr", xr_api_version, xr_kind)
    """
    return cap in req.meta.capabilities


def get_required_schema(req: fnv1.RunFunctionRequest, name: str) -> dict | None:
    """Get a required OpenAPI schema by name from the request.

    Args:
        req: The RunFunctionRequest containing required schemas.
        name: The name of the required schema to get.

    Returns:
        The OpenAPI v3 schema as a dictionary, or None if not found.

    Note: This returns None both when the requirement hasn't been resolved yet,
    and when it was resolved but the schema wasn't found. To distinguish between
    these cases, check whether Crossplane resolved the requirement using
    `name in req.required_schemas`:

        # Always declare requirements - Crossplane considers them satisfied
        # when they stabilize across calls.
        response.require_schema(rsp, name, "example.org/v1", "MyKind")

        if name in req.required_schemas:
            schema = request.get_required_schema(req, name)
            if schema is None:
                # Crossplane resolved the requirement, but couldn't find it
                response.fatal(rsp, "schema not found")

    The returned schema can be used with libraries like openapi-schema-validator
    or jsonschema for validation:

        schema = request.get_required_schema(req, "my-schema")
        if schema:
            from openapi_schema_validator import validate
            validate(resource, schema)
    """
    if name not in req.required_schemas:
        return None

    schema = req.required_schemas[name]
    if not schema.HasField("openapi_v3"):
        return None

    return resource.struct_to_dict(schema.openapi_v3)
