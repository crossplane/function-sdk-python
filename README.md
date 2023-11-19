# function-sdk-python
[![CI](https://github.com/crossplane/function-sdk-python/actions/workflows/ci.yml/badge.svg)](https://github.com/crossplane/function-sdk-python/actions/workflows/ci.yml) ![GitHub release (latest SemVer)](https://img.shields.io/github/release/crossplane/function-sdk-python)

The [Python][python] SDK for writing [composition functions][functions].

This SDK is currently a beta. We try to avoid breaking changes, but it will not
have a stable API until it reaches v1.0.0. It follows the same [contributing
guidelines] as Crossplane.

To learn how to use this SDK:

* [Learn about how composition functions work][functions]

## Contributing

This project follows the Crossplane [contributing guidelines], where applicable
to Python. It is linted, tested, and built using [Hatch][hatch].

Some useful commands:

```shell
# Generate gRPC stubs.
hatch run generate:protoc

# Lint the code, using ruff.
hatch run lint:check
hatch run lint:check-format

# Run unit tests.
hatch run test:unit

# Build an sdist and wheel
hatch build
```

[python]: https://python.org
[functions]: https://docs.crossplane.io/latest/concepts/composition-functions
[contributing guidelines]: https://github.com/crossplane/crossplane/tree/master/contributing
[hatch]: https://github.com/pypa/hatch
