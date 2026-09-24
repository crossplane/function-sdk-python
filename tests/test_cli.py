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

import dataclasses
import datetime
import unittest
from unittest import mock

import click
from click.testing import CliRunner
from google.protobuf import duration_pb2 as durationpb
from google.protobuf import json_format

from crossplane.function import cli, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1


class TestParseDuration(unittest.TestCase):
    def test_parse_duration(self) -> None:
        @dataclasses.dataclass
        class TestCase:
            reason: str
            value: str
            want: datetime.timedelta

        cases = [
            TestCase(
                reason="Bare integers are interpreted as seconds.",
                value="60",
                want=datetime.timedelta(seconds=60),
            ),
            TestCase(
                reason="Seconds suffix should work.",
                value="60s",
                want=datetime.timedelta(seconds=60),
            ),
            TestCase(
                reason="Minutes suffix should work.",
                value="1m",
                want=datetime.timedelta(minutes=1),
            ),
            TestCase(
                reason="Hours suffix should work.",
                value="1h",
                want=datetime.timedelta(hours=1),
            ),
            TestCase(
                reason="Days suffix should work.",
                value="1d",
                want=datetime.timedelta(days=1),
            ),
            TestCase(
                reason="Combined durations should be summed.",
                value="1h30m",
                want=datetime.timedelta(hours=1, minutes=30),
            ),
            TestCase(
                reason="Zero seconds should work.",
                value="0s",
                want=datetime.timedelta(seconds=0),
            ),
            TestCase(
                reason="Zero as a bare integer should work.",
                value="0",
                want=datetime.timedelta(seconds=0),
            ),
            TestCase(
                reason="Fractional seconds should work.",
                value="1.5s",
                want=datetime.timedelta(seconds=1.5),
            ),
        ]

        for case in cases:
            got = cli.parse_duration(case.value)
            self.assertEqual(case.want, got, case.reason)

    def test_parse_duration_invalid(self) -> None:
        for value in ("", "1x", "-5m", "1m2"):
            with self.assertRaises(ValueError, msg=value):
                cli.parse_duration(value)


class TestStandardOptions(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_default_ttl = response.get_default_ttl()

    def tearDown(self) -> None:
        response.set_default_ttl(self._saved_default_ttl)

    def test_run_sets_default_ttl_from_flag(self) -> None:
        @click.command()
        @cli.standard_options
        def main(**kwargs):
            cli.run(mock.Mock(), **kwargs)

        runner = CliRunner()
        with mock.patch("crossplane.function.cli.runtime.serve"):
            result = runner.invoke(main, ["--ttl", "5m", "--insecure"])
        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(datetime.timedelta(minutes=5), response.get_default_ttl())

    def test_run_sets_default_ttl_from_env(self) -> None:
        @click.command()
        @cli.standard_options
        def main(**kwargs):
            cli.run(mock.Mock(), **kwargs)

        runner = CliRunner()
        with mock.patch("crossplane.function.cli.runtime.serve"):
            result = runner.invoke(
                main,
                ["--insecure"],
                env={"TTL": "10m"},
            )
        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(datetime.timedelta(minutes=10), response.get_default_ttl())

    def test_run_leaves_default_ttl_when_flag_omitted(self) -> None:
        response.set_default_ttl(response.DEFAULT_TTL)

        @click.command()
        @cli.standard_options
        def main(**kwargs):
            cli.run(mock.Mock(), **kwargs)

        runner = CliRunner()
        with mock.patch("crossplane.function.cli.runtime.serve"):
            result = runner.invoke(main, ["--insecure"])
        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(response.DEFAULT_TTL, response.get_default_ttl())

    def test_invalid_ttl_flag(self) -> None:
        @click.command()
        @cli.standard_options
        def main(**kwargs):
            cli.run(mock.Mock(), **kwargs)

        runner = CliRunner()
        result = runner.invoke(main, ["--ttl", "1x", "--insecure"])
        self.assertNotEqual(0, result.exit_code)

    def test_ttl_flag_affects_response_to(self) -> None:
        @click.command()
        @cli.standard_options
        def main(**kwargs):
            cli.run(mock.Mock(), **kwargs)

        runner = CliRunner()
        with mock.patch("crossplane.function.cli.runtime.serve"):
            result = runner.invoke(main, ["--ttl", "5m", "--insecure"])
        self.assertEqual(0, result.exit_code, result.output)

        req = fnv1.RunFunctionRequest(meta=fnv1.RequestMeta(tag="hi"))
        got = response.to(req)
        want = fnv1.RunFunctionResponse(
            meta=fnv1.ResponseMeta(tag="hi", ttl=durationpb.Duration(seconds=60 * 5)),
            desired=req.desired,
            context=req.context,
        )
        self.assertEqual(
            json_format.MessageToJson(want, sort_keys=True),
            json_format.MessageToJson(got, sort_keys=True),
        )


class TestDurationParamType(unittest.TestCase):
    def test_convert(self) -> None:
        param_type = cli.DurationParamType()
        got = param_type.convert("5m", None, None)
        self.assertEqual(datetime.timedelta(minutes=5), got)

    def test_convert_invalid(self) -> None:
        param_type = cli.DurationParamType()
        with self.assertRaises(click.BadParameter):
            param_type.convert("1x", None, None)


if __name__ == "__main__":
    unittest.main()
