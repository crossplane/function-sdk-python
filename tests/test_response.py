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
                json_format.MessageToJson(case.want),
                json_format.MessageToJson(got),
                "-want, +got",
            )


if __name__ == "__main__":
    unittest.main()
