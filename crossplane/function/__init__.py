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

"""Python SDK for writing Crossplane composition functions.

This SDK provides the building blocks for implementing [Crossplane composition
functions](https://docs.crossplane.io/latest/concepts/composition-functions) in
Python. Composition functions are serverless components that extend Crossplane's
composition capability, allowing you to programmatically control how infrastructure
is composed and managed.

## Quick Start

Install the SDK:

```shell
pip install crossplane-function-sdk-python
```

Create a composition function by subclassing `Runtime`:

```python
from crossplane.function.runtime import Runtime
from crossplane.function.request import RunFunctionRequest
from crossplane.function.response import RunFunctionResponse


class MyFunction(Runtime):
    def Run(self, request: RunFunctionRequest) -> RunFunctionResponse:
        # Your composition logic here
        return response.to(request)
```

## Modules

- **runtime** — Base class for implementing the function runtime and gRPC server.
- **request** — Types and utilities for parsing `RunFunctionRequest` messages.
- **response** — Types and utilities for building `RunFunctionResponse` messages.
- **resource** — Kubernetes resource types used in function pipelines.
- **logging** — Structured logging utilities for function output.

## Protobuf Types

The `RunFunctionRequest` and `RunFunctionResponse` types are generated from
proto3 schema definitions. See the proto modules for API reference:

- [`proto.v1.run_function_pb2`][crossplane.function.proto.v1.run_function_pb2]
  — Current API
- [`proto.v1beta1.run_function_pb2`][crossplane.function.proto.v1beta1.run_function_pb2]
  — Legacy API

Proto-generated fields behave like standard Python types but follow
[protobuf Python conventions](https://protobuf.dev/reference/python/python-generated/).
"""
