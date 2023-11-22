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

"""Logging utilities for composition functions."""

import enum
import logging

import structlog


class Level(enum.Enum):
    """Supported log levels."""

    DISABLED = 0
    DEBUG = 1
    INFO = 2


def configure(level: Level = Level.INFO) -> None:
    """Configure logging.

    Args:
        level: What log level to enable.

    Must be called before calling get_logger. When debug logging is enabled logs
    will be printed in a human readable fashion. When not enabled, logs will be
    printed as JSON lines.
    """

    def dropper(logger, method_name, event_dict):  # noqa: ARG001  # We need this signature.
        raise structlog.DropEvent

    if level == Level.DISABLED:
        structlog.configure(processors=[dropper])
        return

    processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
    ]

    if level == Level.DEBUG:
        structlog.configure(
            processors=[
                *processors,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
            ]
        )
        return

    # Attempt to match function-sdk-go's production logger.
    structlog.configure(
        processors=[
            *processors,
            structlog.processors.dict_tracebacks,
            structlog.processors.TimeStamper(key="ts"),
            structlog.processors.EventRenamer(to="msg"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


def get_logger() -> structlog.stdlib.BoundLogger:
    """Get a logger.

    You must call configure before calling get_logger.
    """
    return structlog.stdlib.get_logger()
