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

from google.protobuf import duration_pb2 as durationpb
from google.protobuf import json_format
from google.protobuf import struct_pb2 as structpb

from crossplane.function import logging, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1


class TestResponse(unittest.TestCase):
    def setUp(self) -> None:
        logging.configure(level=logging.Level.DISABLED)

    def test_to(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            req: fnv1.RunFunctionRequest
            ttl: datetime.timedelta
            want: fnv1.RunFunctionResponse

        cases = [
            TestCase(
                reason="Tag, desired, and context should be copied.",
                req=fnv1.RunFunctionRequest(
                    meta=fnv1.RequestMeta(tag="hi"),
                    desired=fnv1.State(
                        resources={
                            "ready-composed-resource": fnv1.Resource(),
                        }
                    ),
                    context=resource.dict_to_struct({"cool-key": "cool-value"}),
                ),
                ttl=datetime.timedelta(minutes=10),
                want=fnv1.RunFunctionResponse(
                    meta=fnv1.ResponseMeta(
                        tag="hi", ttl=durationpb.Duration(seconds=60 * 10)
                    ),
                    desired=fnv1.State(
                        resources={
                            "ready-composed-resource": fnv1.Resource(),
                        }
                    ),
                    context=resource.dict_to_struct({"cool-key": "cool-value"}),
                ),
            ),
        ]

        for case in cases:
            got = response.to(case.req, case.ttl)
            self.assertEqual(
                json_format.MessageToJson(case.want, sort_keys=True),
                json_format.MessageToJson(got, sort_keys=True),
                "-want, +got",
            )

    def test_set_conditions(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            conditions: list[resource.Condition]
            want_types: list[str]
            want_statuses: list[fnv1.Status.ValueType]
            want_reasons: list[str]
            want_messages: list[str]

        cases = [
            TestCase(
                reason="A single True condition should work.",
                conditions=[
                    resource.Condition(
                        typ="DatabaseReady",
                        status="True",
                        reason="Available",
                        message="The database is ready",
                    ),
                ],
                want_types=["DatabaseReady"],
                want_statuses=[fnv1.STATUS_CONDITION_TRUE],
                want_reasons=["Available"],
                want_messages=["The database is ready"],
            ),
            TestCase(
                reason="Multiple conditions should all be appended.",
                conditions=[
                    resource.Condition(
                        typ="DatabaseReady",
                        status="True",
                        reason="Available",
                    ),
                    resource.Condition(
                        typ="CacheReady",
                        status="False",
                        reason="Creating",
                    ),
                    resource.Condition(
                        typ="NetworkReady",
                        status="Unknown",
                    ),
                ],
                want_types=["DatabaseReady", "CacheReady", "NetworkReady"],
                want_statuses=[
                    fnv1.STATUS_CONDITION_TRUE,
                    fnv1.STATUS_CONDITION_FALSE,
                    fnv1.STATUS_CONDITION_UNKNOWN,
                ],
                want_reasons=["Available", "Creating", ""],
                want_messages=["", "", ""],
            ),
        ]

        for case in cases:
            rsp = fnv1.RunFunctionResponse()
            response.set_conditions(rsp, *case.conditions)

            self.assertEqual(len(case.conditions), len(rsp.conditions), case.reason)
            for i, got in enumerate(rsp.conditions):
                self.assertEqual(case.want_types[i], got.type, case.reason)
                self.assertEqual(case.want_statuses[i], got.status, case.reason)
                self.assertEqual(case.want_reasons[i], got.reason, case.reason)
                self.assertEqual(case.want_messages[i], got.message, case.reason)

    def test_set_output(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            rsp: fnv1.RunFunctionResponse
            output: dict | structpb.Struct
            want_output: dict

        cases = [
            TestCase(
                reason="Setting output from dict should work.",
                rsp=fnv1.RunFunctionResponse(),
                output={"status": "success", "processed": 42},
                want_output={"status": "success", "processed": 42},
            ),
            TestCase(
                reason="Setting output from Struct should work.",
                rsp=fnv1.RunFunctionResponse(),
                output=resource.dict_to_struct({"result": "completed", "count": 3}),
                want_output={"result": "completed", "count": 3},
            ),
        ]

        for case in cases:
            response.set_output(case.rsp, case.output)
            got_output = resource.struct_to_dict(case.rsp.output)
            self.assertEqual(case.want_output, got_output, case.reason)

    def test_set_output_invalid_type(self) -> None:
        rsp = fnv1.RunFunctionResponse()
        with self.assertRaises(TypeError):
            response.set_output(rsp, "invalid-string-type")

    def test_require_resources(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            rsp: fnv1.RunFunctionResponse
            name: str
            api_version: str
            kind: str
            match_name: str | None
            match_labels: dict[str, str] | None
            namespace: str | None
            want_selector: fnv1.ResourceSelector

        cases = [
            TestCase(
                reason="Should create requirement with match_name.",
                rsp=fnv1.RunFunctionResponse(),
                name="test-pods",
                api_version="v1",
                kind="Pod",
                match_name="my-pod",
                match_labels=None,
                namespace="default",
                want_selector=fnv1.ResourceSelector(
                    api_version="v1",
                    kind="Pod",
                    match_name="my-pod",
                    namespace="default",
                ),
            ),
            TestCase(
                reason="Should create requirement with match_labels.",
                rsp=fnv1.RunFunctionResponse(),
                name="app-pods",
                api_version="v1",
                kind="Pod",
                match_name=None,
                match_labels={"app": "web", "version": "v1.2.3"},
                namespace="production",
                want_selector=fnv1.ResourceSelector(
                    api_version="v1",
                    kind="Pod",
                    match_labels=fnv1.MatchLabels(
                        labels={"app": "web", "version": "v1.2.3"}
                    ),
                    namespace="production",
                ),
            ),
            TestCase(
                reason="Should create requirement without namespace.",
                rsp=fnv1.RunFunctionResponse(),
                name="cluster-resources",
                api_version="v1",
                kind="Node",
                match_name="worker-1",
                match_labels=None,
                namespace=None,
                want_selector=fnv1.ResourceSelector(
                    api_version="v1",
                    kind="Node",
                    match_name="worker-1",
                ),
            ),
        ]

        for case in cases:
            response.require_resources(
                case.rsp,
                case.name,
                case.api_version,
                case.kind,
                match_name=case.match_name,
                match_labels=case.match_labels,
                namespace=case.namespace,
            )

            # Check that the requirement was added
            self.assertIn(case.name, case.rsp.requirements.resources, case.reason)
            got_selector = case.rsp.requirements.resources[case.name]

            self.assertEqual(
                json_format.MessageToJson(case.want_selector, sort_keys=True),
                json_format.MessageToJson(got_selector, sort_keys=True),
                case.reason,
            )

    def test_require_resources_invalid_args(self) -> None:
        rsp = fnv1.RunFunctionResponse()

        # Should raise ValueError if both match_name and match_labels are provided
        with self.assertRaises(ValueError):
            response.require_resources(
                rsp,
                "test",
                "v1",
                "Pod",
                match_name="pod-name",
                match_labels={"app": "test"},
            )

        # Should raise ValueError if neither match_name nor match_labels are provided
        with self.assertRaises(ValueError):
            response.require_resources(
                rsp,
                "test",
                "v1",
                "Pod",
                match_name=None,
                match_labels=None,
            )

    def test_require_schema(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            rsp: fnv1.RunFunctionResponse
            name: str
            api_version: str
            kind: str
            want_selector: fnv1.SchemaSelector

        cases = [
            TestCase(
                reason="Should create schema requirement.",
                rsp=fnv1.RunFunctionResponse(),
                name="bucket-schema",
                api_version="s3.aws.upbound.io/v1beta2",
                kind="Bucket",
                want_selector=fnv1.SchemaSelector(
                    api_version="s3.aws.upbound.io/v1beta2",
                    kind="Bucket",
                ),
            ),
            TestCase(
                reason="Should create schema requirement for core types.",
                rsp=fnv1.RunFunctionResponse(),
                name="pod-schema",
                api_version="v1",
                kind="Pod",
                want_selector=fnv1.SchemaSelector(
                    api_version="v1",
                    kind="Pod",
                ),
            ),
        ]

        for case in cases:
            response.require_schema(
                case.rsp,
                case.name,
                case.api_version,
                case.kind,
            )

            # Check that the requirement was added
            self.assertIn(case.name, case.rsp.requirements.schemas, case.reason)
            got_selector = case.rsp.requirements.schemas[case.name]

            self.assertEqual(
                json_format.MessageToJson(case.want_selector, sort_keys=True),
                json_format.MessageToJson(got_selector, sort_keys=True),
                case.reason,
            )


if __name__ == "__main__":
    unittest.main()
