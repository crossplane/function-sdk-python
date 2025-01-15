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
from tests.testdata.models.io.upbound.aws.s3 import v1beta2


class TestResource(unittest.TestCase):
    def setUp(self) -> None:
        logging.configure(level=logging.Level.DISABLED)

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
                reason="Updating from a Pydantic model should work.",
                r=fnv1.Resource(),
                source=v1beta2.Bucket(
                    spec=v1beta2.Spec(
                        forProvider=v1beta2.ForProvider(region="us-west-2"),
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
        ]

        for case in cases:
            resource.update(case.r, case.source)
            self.assertEqual(
                json_format.MessageToDict(case.want),
                json_format.MessageToDict(case.r),
                "-want, +got",
            )

    def test_get_condition(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            res: structpb.Struct
            typ: str
            want: resource.Condition

        cases = [
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
        ]

        for case in cases:
            got = resource.get_condition(case.res, case.typ)
            self.assertEqual(
                dataclasses.asdict(case.want), dataclasses.asdict(got), "-want, +got"
            )

    def test_get_credentials(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            req: structpb.Struct
            name: str
            want: resource.Credentials

        cases = [
            TestCase(
                reason="Return the specified credentials if they exist.",
                req=resource.dict_to_struct(
                    {"credentials": {"test": {"type": "data", "data": {"foo": "bar"}}}}
                ),
                name="test",
                want=resource.Credentials(type="data", data={"foo": "bar"}),
            ),
            TestCase(
                reason="Return empty credentials if no credentials section exists.",
                req=resource.dict_to_struct({}),
                name="test",
                want=resource.Credentials(type="data", data={}),
            ),
            TestCase(
                reason="Return empty credentials if the specified name does not exist.",
                req=resource.dict_to_struct(
                    {
                        "credentials": {
                            "nottest": {"type": "data", "data": {"foo": "bar"}}
                        }
                    }
                ),
                name="test",
                want=resource.Credentials(type="data", data={}),
            ),
        ]

        for case in cases:
            got = resource.get_credentials(case.req, case.name)
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


if __name__ == "__main__":
    unittest.main()
