"""Utilities for working with RunFunctionResponses."""

import datetime

from google.protobuf import duration_pb2 as durationpb

import crossplane.function.proto.v1beta1.run_function_pb2 as fnv1beta1

"""The default TTL for which a RunFunctionResponse may be cached."""
DEFAULT_TTL = datetime.timedelta(minutes=1)


def to(
    req: fnv1beta1.RunFunctionRequest,
    ttl: datetime.timedelta = DEFAULT_TTL,
) -> fnv1beta1.RunFunctionResponse:
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
    return fnv1beta1.RunFunctionResponse(
        meta=fnv1beta1.ResponseMeta(tag=req.meta.tag, ttl=dttl),
        desired=req.desired,
        context=req.context,
    )


def normal(rsp: fnv1beta1.RunFunctionResponse, message: str) -> None:
    """Add a normal result to the response."""
    rsp.results.append(
        fnv1beta1.Result(
            severity=fnv1beta1.SEVERITY_NORMAL,
            message=message,
        )
    )


def warning(rsp: fnv1beta1.RunFunctionResponse, message: str) -> None:
    """Add a warning result to the response."""
    rsp.results.append(
        fnv1beta1.Result(
            severity=fnv1beta1.SEVERITY_WARNING,
            message=message,
        )
    )


def fatal(rsp: fnv1beta1.RunFunctionResponse, message: str) -> None:
    """Add a fatal result to the response."""
    rsp.results.append(
        fnv1beta1.Result(
            severity=fnv1beta1.SEVERITY_FATAL,
            message=message,
        )
    )
