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

import typing
import unittest

import pydantic
from google.protobuf import json_format

from crossplane.function import dependency, logging, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

# Models shaped the way datamodel-codegen generates them from CRDs: JSON names
# as attribute names, and an alias only where the JSON name is a Python
# keyword.


class Metadata(pydantic.BaseModel):
    name: str | None = None
    annotations: dict[str, str] | None = None


class AtProvider(pydantic.BaseModel):
    id: str | None = None
    arn: str | None = None


class VPCStatus(pydantic.BaseModel):
    atProvider: AtProvider | None = None  # noqa: N815  # Generated models use JSON names.


class VPC(pydantic.BaseModel):
    metadata: Metadata | None = None
    status: VPCStatus | None = None


class Range(pydantic.BaseModel):
    from_: str | None = pydantic.Field(None, alias="from")


class Pool(pydantic.BaseModel):
    ranges: list[Range] | None = None


class SubnetForProvider(pydantic.BaseModel):
    region: str | None = None
    vpcId: str | None = None  # noqa: N815  # Generated models use JSON names.
    tags: list[str] | None = None


class SubnetSpec(pydantic.BaseModel):
    forProvider: SubnetForProvider  # noqa: N815  # Generated models use JSON names.


class Subnet(pydantic.BaseModel):
    apiVersion: str = "ec2.aws.m.upbound.io/v1beta1"  # noqa: N815  # Generated models use JSON names.
    kind: str = "Subnet"
    spec: SubnetSpec


def observed(**resources: dict) -> fnv1.State:
    return fnv1.State(
        resources={
            name: fnv1.Resource(resource=resource.dict_to_struct(body))
            for name, body in resources.items()
        }
    )


VPC_OBSERVED = {
    "apiVersion": "ec2.aws.m.upbound.io/v1beta1",
    "kind": "VPC",
    "metadata": {
        "name": "xr-vpc-abc12",
        "annotations": {"crossplane.io/external-name": "vpc-0123"},
    },
    "status": {"atProvider": {"id": "vpc-0123", "arn": "arn:aws:ec2:vpc/vpc-0123"}},
}

POOL_OBSERVED = {"ranges": [{"from": "10.0.0.0"}, {"from": "10.1.0.0"}]}

ORDERED = fnv1.RequestMeta(
    capabilities=[fnv1.CAPABILITY_CAPABILITIES, fnv1.CAPABILITY_DEPENDENCIES]
)
UNORDERED = fnv1.RequestMeta(capabilities=[fnv1.CAPABILITY_CAPABILITIES])


def desired_subnet(rsp: fnv1.RunFunctionResponse, vpc_id: str) -> None:
    subnet = Subnet(
        spec=SubnetSpec(forProvider=SubnetForProvider(region="us-east-1", vpcId=vpc_id))
    )
    resource.update(rsp.desired.resources["subnet"], subnet)


def edges(rsp: fnv1.RunFunctionResponse) -> list[dict]:
    return [
        json_format.MessageToDict(d, preserving_proto_field_name=True)
        for d in rsp.dependencies.items
    ]


def conditions(rsp: fnv1.RunFunctionResponse) -> list[dict]:
    return [
        json_format.MessageToDict(c, preserving_proto_field_name=True)
        for c in rsp.conditions
    ]


def kept(name: str) -> str:
    """The condition message for a resource kept while the VPC's id is missing."""
    return f"{name} kept its current spec: vpc.status.atProvider.id isn't available"


def body(rsp: fnv1.RunFunctionResponse, name: str) -> dict:
    return resource.struct_to_dict(rsp.desired.resources[name].resource)


class TestNamed(unittest.TestCase):
    def setUp(self) -> None:
        logging.configure(level=logging.Level.DISABLED)

    def read(
        self,
        observed_state: fnv1.State,
        fn: typing.Callable[[dependency.Scope], object],
    ) -> object:
        req = fnv1.RunFunctionRequest(meta=ORDERED, observed=observed_state)
        with dependency.composing(req, response.to(req), "subnet") as c:
            return fn(c)

    def test_follows_model_fields(self) -> None:
        vpc = dependency.named("vpc", VPC)
        self.assertEqual(
            self.read(
                observed(vpc=VPC_OBSERVED), lambda c: c.ref(vpc.status.atProvider.arn)
            ),
            "arn:aws:ec2:vpc/vpc-0123",
        )

    def test_typo_fails_where_it_is_written(self) -> None:
        vpc = dependency.named("vpc", VPC)
        with self.assertRaisesRegex(
            AttributeError, "vpc.status has no field 'atprovider'"
        ):
            _ = vpc.status.atprovider

    def test_keyword_field_is_read_by_its_json_name(self) -> None:
        pool = dependency.named("pool", Pool)
        for field in (
            pool.ranges[0].from_,
            pool.ranges[0]["from"],
            getattr(pool.ranges[0], "from"),
        ):
            self.assertEqual(
                self.read(observed(pool=POOL_OBSERVED), lambda c, f=field: c.ref(f)),
                "10.0.0.0",
            )

    def test_untyped_reads_what_it_is_given(self) -> None:
        vpc = dependency.named("vpc")
        got = self.read(
            observed(vpc=VPC_OBSERVED),
            lambda c: c.ref(vpc.metadata.annotations["crossplane.io/external-name"]),
        )
        self.assertEqual(got, "vpc-0123")

    def test_has_no_value(self) -> None:
        vpc = dependency.named("vpc", VPC)
        field = vpc.status.atProvider.id
        with self.assertRaisesRegex(TypeError, "has no value yet"):
            bool(field)
        with self.assertRaisesRegex(TypeError, "has no value yet"):
            str(field)
        with self.assertRaises(TypeError):
            iter(field)
        with self.assertRaises(AttributeError):
            field.id = "x"

    def test_ref_rejects_values(self) -> None:
        with self.assertRaisesRegex(TypeError, "expects a field"):
            self.read(fnv1.State(), lambda c: c.ref("vpc-0123"))

    def test_ref_rejects_whole_resource(self) -> None:
        with self.assertRaisesRegex(ValueError, "external_name"):
            self.read(fnv1.State(), lambda c: c.ref(dependency.named("vpc", VPC)))

    def test_external_name_rejects_fields(self) -> None:
        vpc = dependency.named("vpc", VPC)
        with self.assertRaises(TypeError):
            self.read(fnv1.State(), lambda c: c.external_name(vpc.status))

    def test_forgetting_ref_fails_validation(self) -> None:
        vpc = dependency.named("vpc", VPC)
        with self.assertRaises(pydantic.ValidationError):
            SubnetForProvider(vpcId=vpc.status.atProvider.id)


class DnsForProvider(pydantic.BaseModel):
    enableDnsSupport: bool | None = None  # noqa: N815  # Generated models use JSON names.


class Dns(pydantic.BaseModel):
    apiVersion: str = "example.org/v1"  # noqa: N815  # Generated models use JSON names.
    kind: str = "Dns"
    spec: DnsForProvider


class TestComposing(unittest.TestCase):
    def setUp(self) -> None:
        logging.configure(level=logging.Level.DISABLED)

    def test_returns_values_and_records_edges(self) -> None:
        req = fnv1.RunFunctionRequest(meta=ORDERED, observed=observed(vpc=VPC_OBSERVED))
        rsp = response.to(req)
        vpc = dependency.named("vpc", VPC)

        with dependency.composing(req, rsp, "subnet") as c:
            vpc_id = c.ref(vpc.status.atProvider.id)
            name = c.external_name(vpc)
            desired_subnet(rsp, vpc_id)

        self.assertEqual(vpc_id, "vpc-0123")
        self.assertEqual(name, "vpc-0123")
        self.assertEqual(
            edges(rsp), [{"resource": "subnet", "composed_resource": "vpc"}]
        )
        self.assertEqual(rsp.results, [])

    def test_typed_values_come_back_as_models(self) -> None:
        req = fnv1.RunFunctionRequest(
            meta=ORDERED, observed=observed(pool=POOL_OBSERVED)
        )
        rsp = response.to(req)
        pool = dependency.named("pool", Pool)

        with dependency.composing(req, rsp, "subnet") as c:
            ranges = c.ref(pool.ranges)
            first = c.ref(pool.ranges[0])
            start = c.ref(pool.ranges[0].from_)

        self.assertEqual(
            ranges, [Range(**{"from": "10.0.0.0"}), Range(**{"from": "10.1.0.0"})]
        )
        self.assertIsInstance(first, Range)
        self.assertEqual(start, "10.0.0.0")

    def test_untyped_values_come_back_as_json(self) -> None:
        req = fnv1.RunFunctionRequest(
            meta=ORDERED, observed=observed(pool=POOL_OBSERVED)
        )
        rsp = response.to(req)
        pool = dependency.named("pool")

        with dependency.composing(req, rsp, "subnet") as c:
            ranges = c.ref(pool.ranges)

        self.assertEqual(ranges, [{"from": "10.0.0.0"}, {"from": "10.1.0.0"}])

    def test_values_that_dont_fit_the_model_fail(self) -> None:
        req = fnv1.RunFunctionRequest(
            meta=ORDERED, observed=observed(pool={"ranges": [{"from": 7}]})
        )
        rsp = response.to(req)
        pool = dependency.named("pool", Pool)

        with (
            self.assertRaisesRegex(ValueError, "pool.ranges doesn't match its model"),
            dependency.composing(req, rsp, "subnet") as c,
        ):
            c.ref(pool.ranges)

    def test_works_in_fields_that_are_not_strings(self) -> None:
        vpc_body = {"spec": {"forProvider": {"enableDnsSupport": True}}}
        req = fnv1.RunFunctionRequest(meta=ORDERED, observed=observed(vpc=vpc_body))
        rsp = response.to(req)
        vpc = dependency.named("vpc")

        with dependency.composing(req, rsp, "subnet") as c:
            c.update(
                Dns(
                    spec=DnsForProvider(
                        enableDnsSupport=c.ref(vpc.spec.forProvider.enableDnsSupport)
                    )
                )
            )

        self.assertEqual(body(rsp, "subnet")["spec"], {"enableDnsSupport": True})

    def test_missing_source_returns_none_and_keeps_edge(self) -> None:
        req = fnv1.RunFunctionRequest(meta=ORDERED)
        rsp = response.to(req)
        vpc = dependency.named("vpc", VPC)

        with dependency.composing(req, rsp, "subnet") as c:
            vpc_id = c.ref(vpc.status.atProvider.id)
            c.update(
                Subnet(
                    spec=SubnetSpec(
                        forProvider=SubnetForProvider(region="us-east-1", vpcId=vpc_id)
                    )
                )
            )

        self.assertIsNone(vpc_id)
        self.assertEqual(
            body(rsp, "subnet")["spec"]["forProvider"], {"region": "us-east-1"}
        )
        self.assertEqual(
            edges(rsp), [{"resource": "subnet", "composed_resource": "vpc"}]
        )
        self.assertEqual(rsp.results, [])

    def test_existing_resource_keeps_its_spec(self) -> None:
        subnet = {"spec": {"forProvider": {"region": "us-east-1", "vpcId": "vpc-0123"}}}
        req = fnv1.RunFunctionRequest(meta=ORDERED, observed=observed(subnet=subnet))
        rsp = response.to(req)
        vpc = dependency.named("vpc", VPC)

        with dependency.composing(req, rsp, "subnet") as c:
            c.update(
                Subnet(
                    spec=SubnetSpec(
                        forProvider=SubnetForProvider(
                            region="us-west-2", vpcId=c.ref(vpc.status.atProvider.id)
                        )
                    )
                )
            )

        # The function's own change wins; the field it couldn't fill is kept.
        self.assertEqual(
            body(rsp, "subnet")["spec"]["forProvider"],
            {"region": "us-west-2", "vpcId": "vpc-0123"},
        )
        self.assertEqual(rsp.results, [])
        self.assertEqual(
            conditions(rsp),
            [
                {
                    "type": "DependencyValuesAvailable",
                    "status": "STATUS_CONDITION_FALSE",
                    "reason": "KeptCurrentSpec",
                    "message": kept("subnet"),
                }
            ],
        )

    def test_condition_is_true_when_nothing_is_kept(self) -> None:
        # Returned even so: Crossplane keeps a condition a function set
        # earlier, so one only returned while False would never clear.
        req = fnv1.RunFunctionRequest(meta=ORDERED)
        rsp = response.to(req)
        with dependency.composing(req, rsp, "subnet") as c:
            c.ref(dependency.named("vpc", VPC).status.atProvider.id)

        self.assertEqual(
            conditions(rsp),
            [
                {
                    "type": "DependencyValuesAvailable",
                    "status": "STATUS_CONDITION_TRUE",
                    "reason": "Available",
                }
            ],
        )

    def test_condition_names_every_kept_resource(self) -> None:
        existing = {
            "spec": {"forProvider": {"region": "us-east-1", "vpcId": "vpc-0123"}}
        }
        req = fnv1.RunFunctionRequest(
            meta=ORDERED, observed=observed(a=existing, b=existing, c=VPC_OBSERVED)
        )
        rsp = response.to(req)
        vpc = dependency.named("vpc", VPC)

        # A kept resource, one that's fine, then another kept one: the one
        # that's fine mustn't turn the condition back to True.
        for name in ("a", "c", "b"):
            with dependency.composing(req, rsp, name) as c:
                if name == "c":
                    continue
                c.ref(vpc.status.atProvider.id)

        self.assertEqual(
            conditions(rsp),
            [
                {
                    "type": "DependencyValuesAvailable",
                    "status": "STATUS_CONDITION_FALSE",
                    "reason": "KeptCurrentSpec",
                    "message": f"{kept('a')}; {kept('b')}",
                }
            ],
        )

    def test_composing_nothing_declares_nothing(self) -> None:
        req = fnv1.RunFunctionRequest(meta=ORDERED)
        rsp = response.to(req)
        vpc = dependency.named("vpc", VPC)

        with dependency.composing(req, rsp, "subnet") as c:
            vpc_id = c.ref(vpc.status.atProvider.id)
            if vpc_id:
                desired_subnet(rsp, vpc_id)

        self.assertNotIn("subnet", rsp.desired.resources)
        self.assertEqual(edges(rsp), [])

    def test_existing_resource_not_composed_is_kept(self) -> None:
        subnet = {
            "apiVersion": "ec2.aws.m.upbound.io/v1beta1",
            "kind": "Subnet",
            "metadata": {"name": "xr-subnet-1", "uid": "abc", "resourceVersion": "7"},
            "spec": {"forProvider": {"region": "us-east-1", "vpcId": "vpc-0123"}},
            "status": {"atProvider": {"id": "subnet-9"}},
        }
        req = fnv1.RunFunctionRequest(meta=ORDERED, observed=observed(subnet=subnet))
        rsp = response.to(req)
        vpc = dependency.named("vpc", VPC)

        with dependency.composing(req, rsp, "subnet") as c:
            vpc_id = c.ref(vpc.status.atProvider.id)
            if vpc_id:
                desired_subnet(rsp, vpc_id)

        # Kept rather than deleted, as its spec, without what the API server
        # owns: uid, resourceVersion and status.
        self.assertEqual(
            body(rsp, "subnet"),
            {
                "apiVersion": "ec2.aws.m.upbound.io/v1beta1",
                "kind": "Subnet",
                "metadata": {"name": "xr-subnet-1"},
                "spec": {"forProvider": {"region": "us-east-1", "vpcId": "vpc-0123"}},
            },
        )
        self.assertEqual(
            edges(rsp), [{"resource": "subnet", "composed_resource": "vpc"}]
        )
        self.assertEqual(conditions(rsp)[0]["reason"], "KeptCurrentSpec")

    def test_without_capability_holds_back_by_omission(self) -> None:
        req = fnv1.RunFunctionRequest(meta=UNORDERED)
        rsp = response.to(req)
        vpc = dependency.named("vpc", VPC)

        with dependency.composing(req, rsp, "subnet") as c:
            desired_subnet(rsp, c.ref(vpc.status.atProvider.id))

        self.assertNotIn("subnet", rsp.desired.resources)

    def test_exception_records_nothing(self) -> None:
        req = fnv1.RunFunctionRequest(meta=ORDERED, observed=observed(vpc=VPC_OBSERVED))
        rsp = response.to(req)
        vpc = dependency.named("vpc", VPC)

        with (
            self.assertRaises(RuntimeError),
            dependency.composing(req, rsp, "subnet") as c,
        ):
            c.ref(vpc.status.atProvider.id)
            raise RuntimeError

        self.assertEqual(edges(rsp), [])

    def test_required(self) -> None:
        req = fnv1.RunFunctionRequest(
            meta=ORDERED,
            required_resources={
                "dbs": fnv1.Resources(
                    items=[
                        fnv1.Resource(
                            resource=resource.dict_to_struct(
                                {
                                    "metadata": {"name": "a"},
                                    "status": {"address": "db.a"},
                                }
                            )
                        )
                    ]
                )
            },
        )
        rsp = response.to(req)
        db = dependency.named_required("dbs")

        with dependency.composing(req, rsp, "app-config") as c:
            host = c.ref(db.status.address)
            c.update(
                {"apiVersion": "v1", "kind": "ConfigMap", "data": {"DB_HOST": host}}
            )

        self.assertEqual(host, "db.a")
        self.assertEqual(
            edges(rsp),
            [
                {
                    "resource": "app-config",
                    "required_resource": {"requirement_name": "dbs"},
                }
            ],
        )

    def test_external_name(self) -> None:
        req = fnv1.RunFunctionRequest(meta=ORDERED, observed=observed(vpc=VPC_OBSERVED))
        with dependency.composing(req, response.to(req), "subnet") as c:
            self.assertEqual(c.external_name(dependency.named("vpc")), "vpc-0123")

    def test_external_name_falls_back_to_name(self) -> None:
        req = fnv1.RunFunctionRequest(
            meta=ORDERED, observed=observed(vpc={"metadata": {"name": "xr-vpc-abc12"}})
        )
        with dependency.composing(req, response.to(req), "subnet") as c:
            self.assertEqual(c.external_name(dependency.named("vpc")), "xr-vpc-abc12")

    def test_missing_field_on_existing_source_is_none(self) -> None:
        req = fnv1.RunFunctionRequest(
            meta=ORDERED, observed=observed(vpc={"metadata": {"name": "xr-vpc-abc12"}})
        )
        rsp = response.to(req)
        with dependency.composing(req, rsp, "subnet") as c:
            vpc_id = c.ref(dependency.named("vpc", VPC).status.atProvider.id)
            desired_subnet(rsp, vpc_id)

        self.assertIsNone(vpc_id)
        self.assertNotIn("vpcId", body(rsp, "subnet")["spec"]["forProvider"])

    def test_none_is_stripped_however_the_resource_is_written(self) -> None:
        req = fnv1.RunFunctionRequest(meta=ORDERED, observed=observed(vpc=VPC_OBSERVED))
        rsp = response.to(req)
        vpc = dependency.named("vpc", VPC)
        gone = dependency.named("gone", VPC)

        # resource.update rather than c.update, as a helper would call it. A
        # model field set to None is emitted as a null, because it was set.
        with dependency.composing(req, rsp, "subnet") as c:
            resource.update(
                rsp.desired.resources["subnet"],
                Subnet(
                    spec=SubnetSpec(
                        forProvider=SubnetForProvider(
                            region="us-east-1", vpcId=c.ref(gone.status.atProvider.id)
                        )
                    )
                ),
            )

        # A dict can carry None nested, and in a list.
        with dependency.composing(req, rsp, "tags") as c:
            resource.update(
                rsp.desired.resources["tags"],
                {
                    "spec": {
                        "vpcId": c.ref(gone.status.atProvider.id),
                        "tags": [
                            "static",
                            c.ref(vpc.status.atProvider.arn),
                            c.ref(gone.status.atProvider.arn),
                        ],
                    }
                },
            )

        self.assertEqual(
            body(rsp, "subnet")["spec"]["forProvider"], {"region": "us-east-1"}
        )
        self.assertEqual(
            body(rsp, "tags")["spec"], {"tags": ["static", "arn:aws:ec2:vpc/vpc-0123"]}
        )

    def test_does_not_duplicate_declared_dependencies(self) -> None:
        req = fnv1.RunFunctionRequest(meta=ORDERED, observed=observed(vpc=VPC_OBSERVED))
        rsp = response.to(req)
        response.add_dependency(rsp, "subnet", "vpc")
        vpc = dependency.named("vpc", VPC)

        with dependency.composing(req, rsp, "subnet") as c:
            c.update(
                {
                    "a": c.ref(vpc.status.atProvider.id),
                    "b": c.ref(vpc.status.atProvider.arn),
                }
            )

        self.assertEqual(
            edges(rsp), [{"resource": "subnet", "composed_resource": "vpc"}]
        )

    def test_self_reference_declares_nothing(self) -> None:
        req = fnv1.RunFunctionRequest(meta=ORDERED, observed=observed(vpc=VPC_OBSERVED))
        rsp = response.to(req)
        vpc = dependency.named("vpc", VPC)

        with dependency.composing(req, rsp, "vpc") as c:
            c.update({"tag": c.ref(vpc.status.atProvider.id)})

        self.assertEqual(edges(rsp), [])

    def required(self, *items: dict) -> fnv1.RunFunctionRequest:
        return fnv1.RunFunctionRequest(
            meta=ORDERED,
            required_resources={
                "dbs": fnv1.Resources(
                    items=[
                        fnv1.Resource(resource=resource.dict_to_struct(i))
                        for i in items
                    ]
                )
            },
        )

    def test_required_named_match(self) -> None:
        req = self.required(
            {
                "metadata": {"name": "a", "namespace": "x"},
                "status": {"address": "db.xa"},
            },
            {
                "metadata": {"name": "a", "namespace": "y"},
                "status": {"address": "db.ya"},
            },
        )
        rsp = response.to(req)
        db = dependency.named_required("dbs", name="a", namespace="y")

        with dependency.composing(req, rsp, "app-config") as c:
            host = c.ref(db.status.address)
            c.update(
                {"apiVersion": "v1", "kind": "ConfigMap", "data": {"DB_HOST": host}}
            )

        self.assertEqual(host, "db.ya")
        self.assertEqual(
            edges(rsp)[0]["required_resource"],
            {"requirement_name": "dbs", "name": "a", "namespace": "y"},
        )

    def test_required_declines_to_guess_between_matches(self) -> None:
        req = self.required(
            {"metadata": {"name": "a"}, "status": {"address": "db.a"}},
            {"metadata": {"name": "b"}, "status": {"address": "db.b"}},
        )
        with dependency.composing(req, response.to(req), "app-config") as c:
            self.assertIsNone(c.ref(dependency.named_required("dbs").status.address))

    def test_rejects_values(self) -> None:
        req = fnv1.RunFunctionRequest(meta=ORDERED)
        rsp = response.to(req)
        with (
            self.assertRaises(TypeError),
            dependency.composing(req, rsp, "subnet") as c,
        ):
            c.ref("vpc-0123")


if __name__ == "__main__":
    unittest.main()
