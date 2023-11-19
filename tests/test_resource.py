import dataclasses
import datetime
import unittest

from google.protobuf import struct_pb2 as structpb

from crossplane.function import logging, resource


class TestResource(unittest.TestCase):
    def setUp(self) -> None:
        logging.configure(level=logging.Level.DISABLED)

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


if __name__ == "__main__":
    unittest.main()
