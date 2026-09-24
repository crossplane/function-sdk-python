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

Standard flags include ``--address``, ``--debug``, ``--insecure``,
``--tls-server-certs-dir``, gRPC message size limits, and ``--ttl``. Each
option also supports a corresponding environment variable (for example
``ADDRESS``, ``DEBUG``, ``TTL``).

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

import datetime
import functools
import re
from collections.abc import Callable
from typing import TypeVar

import click

from crossplane.function import logging, response, runtime
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1

F = TypeVar("F", bound=Callable)

DEFAULT_ADDRESS = "0.0.0.0:9443"
DEFAULT_MAX_RECV_MESSAGE_SIZE = 4  # MB

_UNIT_TO_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}
_DURATION_COMPONENT_RE = re.compile(r"(\d+(?:\.\d+)?)([smhd])")


def parse_duration(value: str) -> datetime.timedelta:
    """Parse a duration string into a :class:`datetime.timedelta`.

    Accepts Go-style duration strings (e.g. ``60s``, ``1m``, ``1h30m``) and bare
    integers interpreted as seconds (e.g. ``60``).

    Args:
        value: The duration string to parse.

    Returns:
        The parsed duration.

    Raises:
        ValueError: If the string is empty, invalid, or negative.
    """
    value = value.strip()
    if not value:
        msg = "duration must not be empty"
        raise ValueError(msg)

    if value.isdigit():
        return datetime.timedelta(seconds=int(value))

    total_seconds = 0.0
    pos = 0
    for match in _DURATION_COMPONENT_RE.finditer(value):
        if match.start() != pos:
            msg = f"invalid duration: {value}"
            raise ValueError(msg)
        total_seconds += float(match.group(1)) * _UNIT_TO_SECONDS[match.group(2)]
        pos = match.end()

    if pos != len(value):
        msg = f"invalid duration: {value}"
        raise ValueError(msg)

    if total_seconds < 0:
        msg = "duration must not be negative"
        raise ValueError(msg)

    return datetime.timedelta(seconds=total_seconds)


class DurationParamType(click.ParamType):
    """A Click parameter type that parses duration strings."""

    name = "duration"

    def convert(
        self,
        value: object,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> datetime.timedelta:
        """Convert a CLI value to a :class:`datetime.timedelta`."""
        if isinstance(value, datetime.timedelta):
            return value
        try:
            return parse_duration(str(value))
        except ValueError as e:
            self.fail(str(e), param, ctx)


DURATION = DurationParamType()


def standard_options(func: F) -> F:
    """Apply the standard Composition Function CLI options to a Click command."""

    @click.option(
        "--max-send-message-size",
        type=int,
        default=None,
        envvar="MAX_SEND_MESSAGE_SIZE",
        help="Maximum size of sent gRPC messages in MB. "
        "Defaults to --max-recv-message-size.",
    )
    @click.option(
        "--max-recv-message-size",
        "--max-grpc-message-size",
        type=int,
        default=DEFAULT_MAX_RECV_MESSAGE_SIZE,
        show_default=True,
        envvar=["MAX_RECV_MESSAGE_SIZE", "MAX_GRPC_MESSAGE_SIZE"],
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
    @click.option(
        "--ttl",
        type=DURATION,
        default=None,
        show_default="1m",
        envvar="TTL",
        help="Default TTL for RunFunctionResponses. "
        "Controls how long Crossplane may cache the response "
        "before re-invoking the function.",
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
    max_send_message_size: int | None,
    ttl: datetime.timedelta | None,
) -> None:
    """Start a composition function gRPC server with standard options."""
    level = logging.Level.DEBUG if debug else logging.Level.INFO
    logging.configure(level=level)

    if ttl is not None:
        response.set_default_ttl(ttl)

    if max_send_message_size is None:
        max_send_message_size = max_recv_message_size

    options = [
        ("grpc.max_receive_message_length", max_recv_message_size * 1024 * 1024),
        ("grpc.max_send_message_length", max_send_message_size * 1024 * 1024),
    ]

    runtime.serve(
        function_runner,
        address,
        creds=runtime.load_credentials(tls_certs_dir),
        insecure=insecure,
        options=options,
    )
