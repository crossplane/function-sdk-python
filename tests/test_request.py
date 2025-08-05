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

import dataclasses
import unittest

import crossplane.function.proto.v1.run_function_pb2 as fnv1
from crossplane.function import logging, request, resource


class TestRequest(unittest.TestCase):
    def setUp(self) -> None:
        logging.configure(level=logging.Level.DISABLED)

    def test_get_required_resources(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            req: fnv1.RunFunctionRequest
            name: str
            want: list[dict]

        cases = [
            TestCase(
                reason="Should return empty list when requirement name not found.",
                req=fnv1.RunFunctionRequest(),
                name="non-existent",
                want=[],
            ),
            TestCase(
                reason="Should return resources when requirement name exists.",
                req=fnv1.RunFunctionRequest(
                    required_resources={
                        "test-resources": fnv1.Resources(
                            items=[
                                fnv1.Resource(
                                    resource=resource.dict_to_struct(
                                        {
                                            "apiVersion": "v1",
                                            "kind": "Pod",
                                            "metadata": {"name": "test-pod"},
                                        }
                                    )
                                ),
                                fnv1.Resource(
                                    resource=resource.dict_to_struct(
                                        {
                                            "apiVersion": "v1",
                                            "kind": "Service",
                                            "metadata": {"name": "test-svc"},
                                        }
                                    )
                                ),
                            ]
                        )
                    }
                ),
                name="test-resources",
                want=[
                    {
                        "apiVersion": "v1",
                        "kind": "Pod",
                        "metadata": {"name": "test-pod"},
                    },
                    {
                        "apiVersion": "v1",
                        "kind": "Service",
                        "metadata": {"name": "test-svc"},
                    },
                ],
            ),
        ]

        for case in cases:
            got = request.get_required_resources(case.req, case.name)
            self.assertEqual(case.want, got, case.reason)

    def test_get_watched_resource(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            req: fnv1.RunFunctionRequest
            want: dict | None

        cases = [
            TestCase(
                reason="Should return None when no watched resource exists.",
                req=fnv1.RunFunctionRequest(),
                want=None,
            ),
            TestCase(
                reason="Should return watched resource when it exists.",
                req=fnv1.RunFunctionRequest(
                    required_resources={
                        "ops.crossplane.io/watched-resource": fnv1.Resources(
                            items=[
                                fnv1.Resource(
                                    resource=resource.dict_to_struct(
                                        {
                                            "apiVersion": "example.org/v1",
                                            "kind": "App",
                                            "metadata": {"name": "watched-app"},
                                        }
                                    )
                                )
                            ]
                        )
                    }
                ),
                want={
                    "apiVersion": "example.org/v1",
                    "kind": "App",
                    "metadata": {"name": "watched-app"},
                },
            ),
        ]

        for case in cases:
            got = request.get_watched_resource(case.req)
            self.assertEqual(case.want, got, case.reason)

    def test_get_required_resource(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            req: fnv1.RunFunctionRequest
            name: str
            want: dict | None

        cases = [
            TestCase(
                reason="Should return None when requirement name not found.",
                req=fnv1.RunFunctionRequest(),
                name="non-existent",
                want=None,
            ),
            TestCase(
                reason="Should return first resource when requirement name exists.",
                req=fnv1.RunFunctionRequest(
                    required_resources={
                        "single-resource": fnv1.Resources(
                            items=[
                                fnv1.Resource(
                                    resource=resource.dict_to_struct(
                                        {
                                            "apiVersion": "v1",
                                            "kind": "ConfigMap",
                                            "metadata": {"name": "test-cm"},
                                        }
                                    )
                                )
                            ]
                        )
                    }
                ),
                name="single-resource",
                want={
                    "apiVersion": "v1",
                    "kind": "ConfigMap",
                    "metadata": {"name": "test-cm"},
                },
            ),
            TestCase(
                reason="Should return first resource when multiple resources exist.",
                req=fnv1.RunFunctionRequest(
                    required_resources={
                        "multi-resource": fnv1.Resources(
                            items=[
                                fnv1.Resource(
                                    resource=resource.dict_to_struct(
                                        {
                                            "apiVersion": "v1",
                                            "kind": "Secret",
                                            "metadata": {"name": "first-secret"},
                                        }
                                    )
                                ),
                                fnv1.Resource(
                                    resource=resource.dict_to_struct(
                                        {
                                            "apiVersion": "v1",
                                            "kind": "Secret",
                                            "metadata": {"name": "second-secret"},
                                        }
                                    )
                                ),
                            ]
                        )
                    }
                ),
                name="multi-resource",
                want={
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {"name": "first-secret"},
                },
            ),
        ]

        for case in cases:
            got = request.get_required_resource(case.req, case.name)
            self.assertEqual(case.want, got, case.reason)

    def test_get_credentials(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            req: fnv1.RunFunctionRequest
            name: str
            want: request.Credentials

        cases = [
            TestCase(
                reason="Should return empty credentials when no credentials exist.",
                req=fnv1.RunFunctionRequest(),
                name="test",
                want=request.Credentials(type="data", data={}),
            ),
            TestCase(
                reason="Should return empty credentials when specified name not found.",
                req=fnv1.RunFunctionRequest(
                    credentials={
                        "other-cred": fnv1.Credentials(
                            credential_data=fnv1.CredentialData(data={"key": b"value"})
                        )
                    }
                ),
                name="test",
                want=request.Credentials(type="data", data={}),
            ),
            TestCase(
                reason="Should return credentials when they exist.",
                req=fnv1.RunFunctionRequest(
                    credentials={
                        "test": fnv1.Credentials(
                            credential_data=fnv1.CredentialData(
                                data={"username": b"admin", "password": b"secret"}
                            )
                        )
                    }
                ),
                name="test",
                want=request.Credentials(
                    type="credential_data",
                    data={"username": "admin", "password": "secret"},
                ),
            ),
        ]

        for case in cases:
            got = request.get_credentials(case.req, case.name)
            self.assertEqual(
                dataclasses.asdict(case.want), dataclasses.asdict(got), case.reason
            )


if __name__ == "__main__":
    unittest.main()
