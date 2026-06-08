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

"""A composition function SDK."""

import dataclasses
import datetime
import hashlib

import pydantic
from google.protobuf import json_format
from google.protobuf import struct_pb2 as structpb

import crossplane.function.proto.v1.run_function_pb2 as fnv1

# TODO(negz): Do we really need dict_to_struct and struct_to_dict? They don't do
# much, but are perhaps useful for discoverability/"documentation" purposes.


def update(r: fnv1.Resource, source: dict | structpb.Struct | pydantic.BaseModel):
    """Update a composite or composed resource.

    Use update to add or update the supplied resource. If the resource doesn't
    exist, it'll be added. If the resource does exist, it'll be updated. The
    update method semantics are the same as a dictionary's update method. Fields
    that don't exist will be added. Fields that exist will be overwritten.

    The source can be a dictionary, a protobuf Struct, or a Pydantic model.
    """
    match source:
        case pydantic.BaseModel():
            # exclude_unset emits only the fields the caller explicitly set.
            # Crossplane treats desired resources as server-side apply intent,
            # so a function should own exactly the fields it has an opinion
            # about and leave the rest to the API server.
            #
            # by_alias emits each field under its alias, which is its real
            # wire name. datamodel-code-generator aliases fields whose KRM
            # name collides with a Python keyword or builtin (e.g. it emits a
            # bool_ attribute aliased to bool, continue_ aliased to continue).
            # Without by_alias those fields serialize under the Python name and
            # don't match the resource's schema. It's a no-op for ordinary
            # fields, which have no alias.
            data = source.model_dump(exclude_unset=True, by_alias=True, warnings=False)
            # apiVersion and kind identify the resource but are rarely passed
            # as kwargs, so they're usually unset. Add them back explicitly.
            data["apiVersion"] = source.apiVersion
            data["kind"] = source.kind
            r.resource.update(data)
        case structpb.Struct():
            # TODO(negz): Use struct_to_dict and update to match other semantics?
            r.resource.MergeFrom(source)
        case dict():
            r.resource.update(source)
        case _:
            t = type(source)
            msg = f"Unsupported type: {t}"
            raise TypeError(msg)


def update_status(
    r: fnv1.Resource,
    status: dict | pydantic.BaseModel,
) -> None:
    """Update a resource's status.

    Args:
        r: A composite or composed resource to update.
        status: The status to set, as a dictionary or Pydantic model.

    Sets ``r.resource.status`` from the supplied status. When the status
    is a Pydantic model, fields the caller didn't explicitly set are
    excluded and aliased fields are emitted under their wire names,
    matching the behavior of :func:`update`.
    """
    if isinstance(status, pydantic.BaseModel):
        status = status.model_dump(exclude_unset=True, by_alias=True, warnings=False)
    update(r, {"status": status})


def dict_to_struct(d: dict) -> structpb.Struct:
    """Create a Struct well-known type from the supplied dict.

    Functions must return desired resources encoded as a protobuf struct. This
    function makes it possible to work with a Python dict, then convert it to a
    struct in a RunFunctionResponse.
    """
    return json_format.ParseDict(d, structpb.Struct())


def struct_to_dict(s: structpb.Struct) -> dict:
    """Create a dict from the supplied Struct well-known type.

    Crossplane sends observed and desired resources to a function encoded as a
    protobuf struct. This function makes it possible to convert resources to a
    dictionary.
    """
    return json_format.MessageToDict(s, preserving_proto_field_name=True)


@dataclasses.dataclass
class Condition:
    """A status condition."""

    """Type of the condition - e.g. Ready."""
    typ: str

    """Status of the condition - True, False, or Unknown."""
    status: str

    """Reason for the condition status - typically CamelCase."""
    reason: str | None = None

    """Optional message."""
    message: str | None = None

    """The last time the status transitioned to this status."""
    last_transition_time: datetime.time | None = None


def get_condition(
    resource: structpb.Struct | fnv1.Resource | None,
    typ: str,
) -> Condition:
    """Get the supplied status condition of the supplied resource.

    Args:
        resource: A Crossplane resource. Can be a protobuf Struct (the raw
            resource), an fnv1.Resource wrapper, or None. When an
            fnv1.Resource is supplied, the Struct is extracted automatically.
            When None is supplied, an unknown condition is returned.
        typ: The type of status condition to get (e.g. Ready).

    Returns:
        The requested status condition.

    A status condition is always returned. If the status condition isn't present
    in the supplied resource, a condition with status "Unknown" is returned.

    Accepting fnv1.Resource and None makes it safe to pass the result of a
    protobuf map ``.get()`` call directly. This avoids auto-vivification, which
    silently inserts a default entry when using bracket access on a missing
    key::

        # Safe — .get() returns None without mutating the map.
        c = get_condition(req.observed.resources.get("bucket"), "Ready")

        # Unsafe — bracket access auto-vivifies an empty Resource.
        c = get_condition(req.observed.resources["bucket"].resource, "Ready")
    """
    unknown = Condition(typ=typ, status="Unknown")

    if isinstance(resource, fnv1.Resource):
        resource = resource.resource

    if not resource or "status" not in resource:
        return unknown

    if not resource["status"] or "conditions" not in resource["status"]:
        return unknown

    for c in resource["status"]["conditions"]:
        if c["type"] != typ:
            continue

        condition = Condition(
            typ=c["type"],
            status=c["status"],
        )
        if "message" in c:
            condition.message = c["message"]
        if "reason" in c:
            condition.reason = c["reason"]
        if "lastTransitionTime" in c:
            condition.last_transition_time = datetime.datetime.fromisoformat(
                c["lastTransitionTime"]
            )

        return condition

    return unknown


_DNS_LABEL_MAX = 63
_HASH_LEN = 5


def child_name(*parts: str, sep: str = "-") -> str:
    """Build a deterministic, DNS-label-safe name for a child resource.

    Args:
        *parts: Name components to join (e.g. parent name, suffix).
        sep: Separator between parts. Defaults to "-".

    Returns:
        A name that is at most 63 characters long.

    Composition functions often derive child resource names from a parent
    name and a discriminator. The resulting name must be a valid DNS label
    (at most 63 characters). This function joins the parts, appends a
    deterministic 5-character hash suffix for uniqueness, and truncates
    the prefix to fit within the limit.

    The hash suffix is always appended, even for short names, so that
    names are visually consistent regardless of length::

        child_name("my-xr", "bucket")       # "my-xr-bucket-a1b2c"
        child_name("my-very-long-xr-name",
                   "with-a-very-long-suffix") # truncated to 63 chars
    """
    full = sep.join(parts)
    h = hashlib.sha256(full.encode()).hexdigest()[:_HASH_LEN]
    max_prefix = _DNS_LABEL_MAX - _HASH_LEN - 1
    prefix = full[:max_prefix].rstrip(sep)
    return f"{prefix}{sep}{h}"
