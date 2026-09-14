# Copyright 2026 The Crossplane Authors.
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

"""Standard CLI options for Python composition functions.

Provides reusable options and a run helper so that every composition
function shares a standard set of flags, environment variables, and defaults.

Usage in a function's main.py::

    import click
    from crossplane.function import cli as sdkcli
    from function import fn

    @click.command()
    @sdkcli.standard_options
    def cli(**kwargs):
        sdkcli.run(fn.FunctionRunner(), **kwargs)

To add custom options, stack them with the decorator::

    @click.command()
    @sdkcli.standard_options
    @click.option("--cache-size", default=100, envvar="CACHE_SIZE")
    def cli(cache_size, **kwargs):
        runner = fn.FunctionRunner(cache_size=cache_size)
        sdkcli.run(runner, **kwargs)
"""

import functools
from collections.abc import Callable
from typing import TypeVar

import click

from crossplane.function import logging, runtime
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1

F = TypeVar("F", bound=Callable)

DEFAULT_ADDRESS = "0.0.0.0:9443"
DEFAULT_MAX_RECV_MESSAGE_SIZE = 4  # MB


def standard_options(func: F) -> F:
    """Apply the standard Composition Function CLI options to a Click command."""

    @click.option(
        "--max-recv-message-size",
        type=int,
        default=DEFAULT_MAX_RECV_MESSAGE_SIZE,
        show_default=True,
        envvar="MAX_RECV_MESSAGE_SIZE",
        help="Maximum size of received gRPC messages in MB.",
    )
    @click.option(
        "--insecure",
        is_flag=True,
        envvar="INSECURE",
        help="Run without mTLS credentials. "
        "If you supply this flag --tls-server-certs-dir will be ignored.",
    )
    @click.option(
        "--tls-server-certs-dir",
        "--tls-certs-dir",
        "tls_certs_dir",
        envvar="TLS_SERVER_CERTS_DIR",
        help="Serve using mTLS certificates.",
    )
    @click.option(
        "--address",
        default=DEFAULT_ADDRESS,
        show_default=True,
        envvar="ADDRESS",
        help="Address at which to listen for gRPC connections.",
    )
    @click.option(
        "--debug",
        "-d",
        is_flag=True,
        envvar="DEBUG",
        help="Emit debug logs.",
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def run(  # noqa: PLR0913
    function_runner: grpcv1.FunctionRunnerServiceServicer,
    *,
    debug: bool,
    address: str,
    tls_certs_dir: str | None,
    insecure: bool,
    max_recv_message_size: int,
) -> None:
    """Start a composition function gRPC server with standard options."""
    level = logging.Level.DEBUG if debug else logging.Level.INFO
    logging.configure(level=level)

    size_bytes = max_recv_message_size * 1024 * 1024
    options = [
        ("grpc.max_receive_message_length", size_bytes),
        ("grpc.max_send_message_length", size_bytes),
    ]

    runtime.serve(
        function_runner,
        address,
        creds=runtime.load_credentials(tls_certs_dir),
        insecure=insecure,
        options=options,
    )
