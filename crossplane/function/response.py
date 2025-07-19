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


def to(
    req: fnv1.RunFunctionRequest,
    ttl: datetime.timedelta = DEFAULT_TTL,
) -> fnv1.RunFunctionResponse:
    """Create a response to the supplied request.

    Args:
        req: The request to respond to.
        ttl: How long Crossplane may optionally cache the response.

    Returns:
        A response to the supplied request.

    The request's tag, desired resources, and context is automatically copied to
    the response. Using response.to is a good pattern to ensure
    """
    dttl = durationpb.Duration()
    dttl.FromTimedelta(ttl)
    return fnv1.RunFunctionResponse(
        meta=fnv1.ResponseMeta(tag=req.meta.tag, ttl=dttl),
        desired=req.desired,
        context=req.context,
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
        ValueError: If both match_name and match_labels are provided, or neither.

    This tells Crossplane to fetch the specified resources and include them
    in the next call to the function in req.required_resources[name].
    """
    if (match_name is None) == (match_labels is None):
        msg = "Exactly one of match_name or match_labels must be provided"
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
