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

import crossplane.function.proto.v1.run_function_pb2 as fnv1

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
