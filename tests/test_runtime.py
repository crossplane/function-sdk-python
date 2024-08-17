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
import unittest

import grpc

import crossplane.function.proto.v1.run_function_pb2 as fnv1
import crossplane.function.proto.v1.run_function_pb2_grpc as grpcv1
import crossplane.function.proto.v1beta1.run_function_pb2 as fnv1beta1
from crossplane.function import logging, runtime


class TestRuntime(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logging.configure(level=logging.Level.DISABLED)

    async def test_run_function(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            runner: grpcv1.FunctionRunnerService
            req: fnv1beta1.RunFunctionRequest
            want: fnv1beta1.RunFunctionResponse

        cases = [
            TestCase(
                reason="The v1 response should be returned as a v1beta1 response.",
                runner=EchoRunner(),
                req=fnv1beta1.RunFunctionRequest(meta=fnv1beta1.RequestMeta(tag="hi")),
                want=fnv1beta1.RunFunctionResponse(
                    meta=fnv1beta1.ResponseMeta(tag="hi")
                ),
            ),
        ]

        for case in cases:
            beta_runner = runtime.BetaFunctionRunner(wrapped=case.runner)
            rsp = await beta_runner.RunFunction(case.req, None)

            self.assertEqual(rsp, case.want, "-want, +got")


class EchoRunner(grpcv1.FunctionRunnerService):
    def __init__(self):
        self.log = logging.get_logger()

    async def RunFunction(  # noqa: N802  # gRPC requires this name.
        self,
        req: fnv1.RunFunctionRequest,
        _: grpc.aio.ServicerContext,
    ) -> fnv1beta1.RunFunctionResponse:
        return fnv1beta1.RunFunctionResponse(
            meta=fnv1beta1.ResponseMeta(tag=req.meta.tag)
        )


if __name__ == "__main__":
    unittest.main()
