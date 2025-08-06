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
