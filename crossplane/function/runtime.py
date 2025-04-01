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

"""Utilities to create a composition function runtime."""

import asyncio
import os
import signal

import grpc
from grpc_reflection.v1alpha import reflection

import crossplane.function.proto.v1.run_function_pb2 as fnv1
import crossplane.function.proto.v1.run_function_pb2_grpc as grpcv1
import crossplane.function.proto.v1beta1.run_function_pb2 as fnv1beta1
import crossplane.function.proto.v1beta1.run_function_pb2_grpc as grpcv1beta1

SERVICE_NAMES = (
    reflection.SERVICE_NAME,
    fnv1.DESCRIPTOR.services_by_name["FunctionRunnerService"].full_name,
    fnv1beta1.DESCRIPTOR.services_by_name["FunctionRunnerService"].full_name,
)

SHUTDOWN_GRACE_PERIOD_SECONDS = 5


def load_credentials(tls_certs_dir: str) -> grpc.ServerCredentials:
    """Load TLS credentials for a composition function gRPC server.

    Args:
        tls_certs_dir: A directory containing tls.crt, tls.key, and ca.crt.

    Returns:
        gRPC mTLS server credentials.

    tls.crt and tls.key must be the function's PEM-encoded certificate and
    private key. ca.cert must be a PEM-encoded CA certificate used to
    authenticate callers (i.e. Crossplane).
    """
    if tls_certs_dir is None:
        return None

    with open(os.path.join(tls_certs_dir, "tls.crt"), "rb") as f:
        crt = f.read()

    with open(os.path.join(tls_certs_dir, "tls.key"), "rb") as f:
        key = f.read()

    with open(os.path.join(tls_certs_dir, "ca.crt"), "rb") as f:
        ca = f.read()

    return grpc.ssl_server_credentials(
        private_key_certificate_chain_pairs=[(key, crt)],
        root_certificates=ca,
        require_client_auth=True,
    )


def serve(
    function: grpcv1.FunctionRunnerService,
    address: str,
    *,
    creds: grpc.ServerCredentials,
    insecure: bool,
) -> None:
    """Start a gRPC server and serve requests asychronously.

    Args:
        function: The function (class) to use to serve requests.
        address: The address at which to listen for requests.
        creds: The credentials used to authenticate requests.
        insecure: Serve insecurely, without credentials or encryption.

    Raises:
        ValueError if creds is None and insecure is False.

    If insecure is true requests will be served insecurely, even if credentials
    are supplied.
    """
    # Define the loop before the server so everything uses the same loop.
    loop = asyncio.get_event_loop()

    server = grpc.aio.server()

    loop.add_signal_handler(
        signal.SIGTERM,
        lambda: asyncio.ensure_future(server.stop(grace=SHUTDOWN_GRACE_PERIOD_SECONDS)),
    )

    grpcv1.add_FunctionRunnerServiceServicer_to_server(function, server)
    grpcv1beta1.add_FunctionRunnerServiceServicer_to_server(
        BetaFunctionRunner(wrapped=function), server
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    if creds is None and insecure is False:
        msg = (
            "no credentials were provided - did you provide credentials or use "
            "the insecure flag?"
        )
        raise ValueError(msg)

    if creds is not None:
        server.add_secure_port(address, creds)

    if insecure:
        server.add_insecure_port(address)

    async def start():
        await server.start()
        await server.wait_for_termination()

    try:
        loop.run_until_complete(start())
    finally:
        loop.run_until_complete(server.stop(grace=SHUTDOWN_GRACE_PERIOD_SECONDS))
        loop.close()


class BetaFunctionRunner(grpcv1beta1.FunctionRunnerService):
    """A BetaFunctionRunner handles beta gRPC RunFunctionRequests.

    It handles requests by passing them to a wrapped v1.FunctionRunnerService.
    Incoming v1beta1 requests are converted to v1 by round-tripping them through
    serialization. Outgoing requests are converted from v1 to v1beta1 the same
    way.
    """

    def __init__(self, wrapped: grpcv1.FunctionRunnerService):
        """Create a new BetaFunctionRunner."""
        self.wrapped = wrapped

    async def RunFunction(  # noqa: N802  # gRPC requires this name.
        self, req: fnv1beta1.RunFunctionRequest, context: grpc.aio.ServicerContext
    ) -> fnv1beta1.RunFunctionResponse:
        """Run the underlying function."""
        gareq = fnv1.RunFunctionRequest()
        gareq.ParseFromString(req.SerializeToString())

        garsp = await self.wrapped.RunFunction(gareq, context)
        rsp = fnv1beta1.RunFunctionResponse()
        rsp.ParseFromString(garsp.SerializeToString())

        return rsp
