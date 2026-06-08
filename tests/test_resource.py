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

import dataclasses
import datetime
import unittest

import pydantic
from google.protobuf import json_format
from google.protobuf import struct_pb2 as structpb

import crossplane.function.proto.v1.run_function_pb2 as fnv1
from crossplane.function import logging, resource
from tests.testdata.models.io.k8s.api.resource import v1 as resourcev1
from tests.testdata.models.io.upbound.aws.s3 import v1beta2 as s3v1beta2
from tests.testdata.models.io.upbound.m.aws.iam.accountalias import (
    v1beta1 as accountaliasv1beta1,
)


class TestResource(unittest.TestCase):
    def setUp(self) -> None:
        logging.configure(level=logging.Level.DISABLED)

    def test_update_status(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            r: fnv1.Resource
            status: dict | pydantic.BaseModel
            want: dict

        cases = [
            TestCase(
                reason="Setting status from a dict should work.",
                r=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {"apiVersion": "example.org", "kind": "XR"}
                    ),
                ),
                status={"ready": True},
                want={
                    "apiVersion": "example.org",
                    "kind": "XR",
                    "status": {"ready": True},
                },
            ),
            TestCase(
                reason="Setting status from a Pydantic model should work.",
                r=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {"apiVersion": "example.org", "kind": "XR"}
                    ),
                ),
                status=s3v1beta2.ForProvider(region="us-west-2"),
                want={
                    "apiVersion": "example.org",
                    "kind": "XR",
                    "status": {"region": "us-west-2"},
                },
            ),
            TestCase(
                reason="Fields the caller set should be kept, while unset "
                "fields are omitted.",
                r=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {"apiVersion": "example.org", "kind": "XR"}
                    ),
                ),
                status=s3v1beta2.ForProvider(region="us-west-2", forceDestroy=False),
                want={
                    "apiVersion": "example.org",
                    "kind": "XR",
                    "status": {"region": "us-west-2", "forceDestroy": False},
                },
            ),
            TestCase(
                reason="Setting status from a Pydantic model with keyword-"
                "aliased fields should emit the fields under their aliases.",
                r=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {"apiVersion": "example.org", "kind": "XR"}
                    ),
                ),
                status=resourcev1.DeviceAttribute(**{"bool": True}),
                want={
                    "apiVersion": "example.org",
                    "kind": "XR",
                    "status": {"bool": True},
                },
            ),
            TestCase(
                reason="Setting status on an empty resource should work.",
                r=fnv1.Resource(),
                status={"replicas": 3},
                want={"status": {"replicas": 3}},
            ),
        ]

        for case in cases:
            resource.update_status(case.r, case.status)
            got = resource.struct_to_dict(case.r.resource)
            self.assertEqual(case.want, got, case.reason)

    def test_add(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            r: fnv1.Resource
            source: dict | structpb.Struct | pydantic.BaseModel
            want: fnv1.Resource

        cases = [
            TestCase(
                reason="Updating from a dict should work.",
                r=fnv1.Resource(),
                source={"apiVersion": "example.org", "kind": "Resource"},
                want=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {"apiVersion": "example.org", "kind": "Resource"}
                    ),
                ),
            ),
            TestCase(
                reason="Updating an existing resource from a dict should work.",
                r=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {"apiVersion": "example.org", "kind": "Resource"}
                    ),
                ),
                source={
                    "metadata": {"name": "cool"},
                },
                want=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.org",
                            "kind": "Resource",
                            "metadata": {"name": "cool"},
                        }
                    ),
                ),
            ),
            TestCase(
                reason="Updating from a struct should work.",
                r=fnv1.Resource(),
                source=resource.dict_to_struct(
                    {"apiVersion": "example.org", "kind": "Resource"}
                ),
                want=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {"apiVersion": "example.org", "kind": "Resource"}
                    ),
                ),
            ),
            TestCase(
                # This model uses the default_factory form that older
                # datamodel-code-generator emits for fields with an object
                # default. providerConfigRef has such a default but isn't set
                # here, so it must not be emitted.
                reason="Updating from a Pydantic model with default_factory "
                "object defaults should omit unset fields.",
                r=fnv1.Resource(),
                source=s3v1beta2.Bucket(
                    spec=s3v1beta2.Spec(
                        forProvider=s3v1beta2.ForProvider(region="us-west-2"),
                    ),
                ),
                want=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "s3.aws.upbound.io/v1beta2",
                            "kind": "Bucket",
                            "spec": {"forProvider": {"region": "us-west-2"}},
                        }
                    ),
                ),
            ),
            TestCase(
                # This model uses the validate_default=True form that newer
                # datamodel-code-generator emits for fields with an object
                # default. providerConfigRef has such a default but isn't set
                # here, so it must not be emitted.
                reason="Updating from a Pydantic model with validate_default "
                "object defaults should omit unset fields.",
                r=fnv1.Resource(),
                source=accountaliasv1beta1.AccountAlias(
                    spec=accountaliasv1beta1.Spec(forProvider={"x": "y"}),
                ),
                want=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "iam.aws.m.upbound.io/v1beta1",
                            "kind": "AccountAlias",
                            "spec": {"forProvider": {"x": "y"}},
                        }
                    ),
                ),
            ),
            TestCase(
                # datamodel-code-generator can't name a field bool or int, so
                # it emits bool_ aliased to bool and int_ aliased to int. The
                # alias is the resource's real wire name, so update must emit
                # fields under their aliases.
                reason="Updating from a Pydantic model with keyword-aliased "
                "fields should emit the fields under their aliases.",
                r=fnv1.Resource(),
                source=resourcev1.ResourceSlice(
                    spec=resourcev1.Spec(
                        devices=[
                            resourcev1.Device(
                                name="gpu",
                                attributes={
                                    "powered": resourcev1.DeviceAttribute(
                                        **{"bool": True},
                                    ),
                                    "lanes": resourcev1.DeviceAttribute(
                                        **{"int": 16},
                                    ),
                                },
                            ),
                        ],
                    ),
                ),
                want=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "resource.k8s.io/v1",
                            "kind": "ResourceSlice",
                            "spec": {
                                "devices": [
                                    {
                                        "name": "gpu",
                                        "attributes": {
                                            "powered": {"bool": True},
                                            "lanes": {"int": 16},
                                        },
                                    },
                                ],
                            },
                        }
                    ),
                ),
            ),
            TestCase(
                # managementPolicies defaults to ["*"] and is set to ["*"]
                # here. A field the caller sets is one it has an opinion about
                # and should own, even when the value equals the default.
                reason="A field the caller explicitly set to its default value "
                "should be emitted.",
                r=fnv1.Resource(),
                source=accountaliasv1beta1.AccountAlias(
                    spec=accountaliasv1beta1.Spec(
                        forProvider={"x": "y"},
                        managementPolicies=["*"],
                    ),
                ),
                want=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "iam.aws.m.upbound.io/v1beta1",
                            "kind": "AccountAlias",
                            "spec": {
                                "forProvider": {"x": "y"},
                                "managementPolicies": ["*"],
                            },
                        }
                    ),
                ),
            ),
        ]

        for case in cases:
            resource.update(case.r, case.source)
            self.assertEqual(
                json_format.MessageToDict(case.want),
                json_format.MessageToDict(case.r),
                "-want, +got",
            )

    def test_model_round_trip(self) -> None:
        # A function reads an observed resource (wire names), validates it into
        # a model, then writes it back via update. A field that goes in under
        # its wire name must come back out under the same wire name. This pins
        # the property the by_alias fix exists to guarantee: validation accepts
        # the alias, and serialization must emit the alias, not the Python
        # attribute name. It does not assert anything about fields the model
        # doesn't define (pydantic drops them) or value types (Struct coerces
        # numbers to float).
        @dataclasses.dataclass
        class TestCase:
            reason: str
            # The resource as it arrives from Crossplane, using wire names.
            observed: dict
            # The model type to validate the observed resource into.
            model: type[pydantic.BaseModel]

        cases = [
            TestCase(
                reason="A model with keyword-aliased fields should round-trip "
                "through validation and update with its fields under the same "
                "wire names (bool, int) they arrived under.",
                observed={
                    "apiVersion": "resource.k8s.io/v1",
                    "kind": "ResourceSlice",
                    "spec": {
                        "devices": [
                            {
                                "name": "gpu",
                                "attributes": {
                                    "powered": {"bool": True},
                                    "lanes": {"int": 16},
                                    "model": {"string": "h100"},
                                },
                            },
                        ],
                    },
                },
                model=resourcev1.ResourceSlice,
            ),
            TestCase(
                reason="A model with only ordinary fields should round-trip unchanged.",
                observed={
                    "apiVersion": "s3.aws.upbound.io/v1beta2",
                    "kind": "Bucket",
                    "spec": {"forProvider": {"region": "us-west-2"}},
                },
                model=s3v1beta2.Bucket,
            ),
        ]

        for case in cases:
            # Mimic the SDK flow: a function reads an observed resource (wire
            # names), validates it into a model, then writes it back out.
            m = case.model.model_validate(case.observed)
            r = fnv1.Resource()
            resource.update(r, m)
            got = resource.struct_to_dict(r.resource)
            self.assertEqual(case.observed, got, case.reason)

    def test_get_condition(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            res: structpb.Struct | fnv1.Resource | None
            typ: str
            want: resource.Condition

        cases = [
            TestCase(
                reason="Return an unknown condition if the resource is None.",
                res=None,
                typ="Ready",
                want=resource.Condition(typ="Ready", status="Unknown"),
            ),
            TestCase(
                reason="Return an unknown condition if the resource has no status.",
                res=resource.dict_to_struct({}),
                typ="Ready",
                want=resource.Condition(typ="Ready", status="Unknown"),
            ),
            TestCase(
                reason="Return an unknown condition if the resource has no conditions.",
                res=resource.dict_to_struct({"status": {}}),
                typ="Ready",
                want=resource.Condition(typ="Ready", status="Unknown"),
            ),
            TestCase(
                reason="Return an unknown condition if the resource does not have the "
                "requested type of condition.",
                res=resource.dict_to_struct(
                    {
                        "status": {
                            "conditions": [
                                {
                                    "type": "Cool",
                                    "status": "True",
                                }
                            ]
                        }
                    }
                ),
                typ="Ready",
                want=resource.Condition(typ="Ready", status="Unknown"),
            ),
            TestCase(
                reason="Return a minimal condition if it exists.",
                res=resource.dict_to_struct(
                    {
                        "status": {
                            "conditions": [
                                {
                                    "type": "Ready",
                                    "status": "True",
                                }
                            ]
                        }
                    }
                ),
                typ="Ready",
                want=resource.Condition(typ="Ready", status="True"),
            ),
            TestCase(
                reason="Return a full condition if it exists.",
                res=resource.dict_to_struct(
                    {
                        "status": {
                            "conditions": [
                                {
                                    "type": "Ready",
                                    "status": "True",
                                    "reason": "Cool",
                                    "message": "This condition is very cool",
                                    "lastTransitionTime": "2023-10-02T16:30:00Z",
                                }
                            ]
                        }
                    }
                ),
                typ="Ready",
                want=resource.Condition(
                    typ="Ready",
                    status="True",
                    reason="Cool",
                    message="This condition is very cool",
                    last_transition_time=datetime.datetime(
                        year=2023,
                        month=10,
                        day=2,
                        hour=16,
                        minute=30,
                        tzinfo=datetime.UTC,
                    ),
                ),
            ),
            TestCase(
                reason="Unwrap an fnv1.Resource to get the condition from its Struct.",
                res=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "status": {
                                "conditions": [
                                    {
                                        "type": "Ready",
                                        "status": "True",
                                    }
                                ]
                            }
                        }
                    ),
                ),
                typ="Ready",
                want=resource.Condition(typ="Ready", status="True"),
            ),
            TestCase(
                reason="Return an unknown condition from an empty fnv1.Resource.",
                res=fnv1.Resource(),
                typ="Ready",
                want=resource.Condition(typ="Ready", status="Unknown"),
            ),
        ]

        for case in cases:
            got = resource.get_condition(case.res, case.typ)
            self.assertEqual(
                dataclasses.asdict(case.want), dataclasses.asdict(got), "-want, +got"
            )

    def test_dict_to_struct(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            d: dict
            want: structpb.Struct

        cases = [
            TestCase(
                reason="Convert an empty dictionary to a struct.",
                d={},
                want=structpb.Struct(),
            ),
            TestCase(
                reason="Convert a dictionary with a single field to a struct.",
                d={"foo": "bar"},
                want=structpb.Struct(
                    fields={"foo": structpb.Value(string_value="bar")}
                ),
            ),
            TestCase(
                reason="Convert a nested dictionary to a struct.",
                d={"foo": {"bar": "baz"}},
                want=structpb.Struct(
                    fields={
                        "foo": structpb.Value(
                            struct_value=structpb.Struct(
                                fields={"bar": structpb.Value(string_value="baz")}
                            )
                        )
                    }
                ),
            ),
            TestCase(
                reason="Convert a nested dictionary containing lists to a struct.",
                d={"foo": {"bar": ["baz", "qux"]}},
                want=structpb.Struct(
                    fields={
                        "foo": structpb.Value(
                            struct_value=structpb.Struct(
                                fields={
                                    "bar": structpb.Value(
                                        list_value=structpb.ListValue(
                                            values=[
                                                structpb.Value(string_value="baz"),
                                                structpb.Value(string_value="qux"),
                                            ]
                                        )
                                    )
                                }
                            )
                        )
                    }
                ),
            ),
        ]
        for case in cases:
            got = resource.dict_to_struct(case.d)
            self.assertEqual(case.want, got, "-want, +got")

    def test_struct_to_dict(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            s: structpb.Struct
            want: dict

        cases = [
            TestCase(
                reason="Convert a struct with no fields to an empty dictionary.",
                s=structpb.Struct(),
                want={},
            ),
            TestCase(
                reason="Convert a struct with a single field to a dictionary.",
                s=structpb.Struct(fields={"foo": structpb.Value(string_value="bar")}),
                want={"foo": "bar"},
            ),
            TestCase(
                reason="Convert a nested struct to a dictionary.",
                s=structpb.Struct(
                    fields={
                        "foo": structpb.Value(
                            struct_value=structpb.Struct(
                                fields={"bar": structpb.Value(string_value="baz")}
                            )
                        )
                    }
                ),
                want={"foo": {"bar": "baz"}},
            ),
            TestCase(
                reason="Convert a nested struct containing ListValues to a dictionary.",
                s=structpb.Struct(
                    fields={
                        "foo": structpb.Value(
                            struct_value=structpb.Struct(
                                fields={
                                    "bar": structpb.Value(
                                        list_value=structpb.ListValue(
                                            values=[
                                                structpb.Value(string_value="baz"),
                                                structpb.Value(string_value="qux"),
                                            ]
                                        )
                                    )
                                }
                            )
                        )
                    }
                ),
                want={"foo": {"bar": ["baz", "qux"]}},
            ),
        ]

        for case in cases:
            got = resource.struct_to_dict(case.s)
            self.assertEqual(case.want, got, "-want, +got")

    def test_child_name(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            parts: list[str]
            want: str

        cases = [
            TestCase(
                reason="A short name should be joined with a hash suffix.",
                parts=["my-xr", "bucket"],
                want="my-xr-bucket-05ecb",
            ),
            TestCase(
                reason="A single part should get a hash suffix.",
                parts=["my-xr"],
                want="my-xr-9d53f",
            ),
            TestCase(
                reason="A long name should be truncated to fit within 63 characters.",
                parts=["a" * 40, "b" * 40],
                want="a" * 40 + "-" + "b" * 16 + "-" + "f5e42",
            ),
            TestCase(
                reason="A name that would end with a trailing separator "
                "after truncation should have the separator stripped.",
                parts=["a" * 56 + "-", "x"],
                # Without stripping, this would be "aaa..a--<hash>".
                # The trailing separator from the truncation is stripped.
                want="a" * 56 + "-" + "995eb",
            ),
            TestCase(
                reason="The same inputs should always produce the same name.",
                parts=["parent", "child"],
                want="parent-child-2f0c9",
            ),
        ]

        for case in cases:
            got = resource.child_name(*case.parts)
            self.assertEqual(case.want, got, case.reason)
            self.assertLessEqual(len(got), 63, case.reason)

    def test_child_name_deterministic(self) -> None:
        a = resource.child_name("parent", "child")
        b = resource.child_name("parent", "child")
        self.assertEqual(a, b)

    def test_child_name_unique(self) -> None:
        a = resource.child_name("parent", "child-a")
        b = resource.child_name("parent", "child-b")
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
