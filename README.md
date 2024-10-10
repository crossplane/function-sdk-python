# function-sdk-python
[![CI](https://github.com/crossplane/function-sdk-python/actions/workflows/ci.yml/badge.svg)](https://github.com/crossplane/function-sdk-python/actions/workflows/ci.yml) [![GitHub release (latest SemVer)](https://img.shields.io/github/release/crossplane/function-sdk-python)](https://github.com/crossplane/function-sdk-python/releases) [![PyPI - Version](https://img.shields.io/pypi/v/crossplane-function-sdk-python)](https://pypi.org/project/crossplane-function-sdk-python/)


The [Python][python] SDK for writing [composition functions][functions].

This SDK is currently a beta. We try to avoid breaking changes, but it will not
have a stable API until it reaches v1.0.0. It follows the same [contributing
guidelines] as Crossplane.

To learn how to use this SDK:

* [Follow the guide to writing a composition function in Python][function guide]
* [Learn about how composition functions work][functions]
* [Read the package documentation][package docs]

The `RunFunctionRequest` and `RunFunctionResponse` types provided by this SDK
are generated from a proto3 protocol buffer schema. Their fields behave
similarly to built-in Python types like lists and dictionaries, but there are
some differences. Read the [generated code documentation][python-protobuf] to
familiarize yourself with the the differences.

If you just want to jump in and get started, consider using the
[function-template-python] template repository.

## Contributing

This project follows the Crossplane [contributing guidelines], where applicable
to Python. It is linted, tested, and built using [Hatch][hatch].

Some useful commands:

```shell
# Generate gRPC stubs.
hatch run generate:protoc

# Format and lint the code.
hatch fmt

# Run unit tests.
hatch test

# Build an sdist and wheel.
hatch build
```

[python]: https://python.org
[functions]: https://docs.crossplane.io/latest/concepts/composition-functions
[python-protobuf]: https://protobuf.dev/reference/python/python-generated/
[function-template-python]: https://github.com/crossplane/function-template-python
[function guide]: https://docs.crossplane.io/knowledge-base/guides/write-a-composition-function-in-python
[package docs]: https://crossplane.github.io/function-sdk-python
[contributing guidelines]: https://github.com/crossplane/crossplane/tree/master/contributing
[hatch]: https://github.com/pypa/hatch
