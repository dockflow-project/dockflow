# Python baseline

This document defines general Python language-level expectations.

The goal is to keep Python code clear, modern, testable, and easy to maintain
without forcing project-specific architecture into reusable package rules.

## Runtime

Use modern, supported Python.

The initial minimum Python version is Python 3.12 unless a project-specific
specification chooses another supported version.

Avoid compatibility workarounds for unsupported Python versions unless another
specs package explicitly requires them.

## Code clarity

Prefer straightforward Python over clever or surprising constructs.

Python code should use clear names, explicit control flow, and cohesive modules.
Small abstractions are useful when they make behavior easier to understand or
test; they should not be introduced merely to make the code look more generic.

Keep modules focused. A module should not mix unrelated domain behavior,
configuration parsing, external I/O, persistence details, and user-interface
translation unless the project is intentionally small enough that separating
them would add noise.

## Types

Public functions, stable boundaries, domain models, and adapter contracts should
declare types when practical.

Project packages may define static type checking tools and configuration. This
baseline only defines where type annotations are expected to carry useful
meaning.

## Paths

Use `pathlib.Path` for filesystem paths.

Convert to strings only at boundaries that require string paths, such as some
third-party APIs, serialization formats, or user-facing output.

## Time

Use timezone-aware UTC timestamps internally when representing an actual moment
in time.

Use ISO 8601 representations at interfaces when timestamps need to be
serialized, displayed, or exchanged with another system.

Naive datetimes may be used only when the value intentionally represents a
local calendar concept rather than a moment in time.

## Errors

Raise meaningful exception types for expected domain or application failures.

Translate internal exceptions into user-facing, process-facing, or
protocol-facing results only at outer boundaries. Core logic should not need to
know how an error will be rendered by a specific interface.

Avoid catching broad exceptions unless the code is at a boundary that can add
useful context, recover intentionally, or translate the failure safely.

## Logging

Use Python's standard logging framework.

Logs should provide enough context to understand what operation was attempted
and why it failed or succeeded. The exact contextual fields are project-specific
and should be chosen by the implementation or project-specific specs.

Never log secrets, credentials, access tokens, private keys, or full sensitive
payloads.

## I/O boundaries

Keep I/O-heavy behavior near the edges of the system when practical.

Core behavior should be testable without real network access, persistent
services, uncontrolled filesystem effects, subprocess execution, or other
external side effects.

This does not require artificial layering for small projects, but it does mean
that important decisions and transformations should be possible to test without
depending on live external state.
