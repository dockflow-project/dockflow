# Task reuse and historical selection

## Eligibility and policy

Task reuse substitutes a verified historical successful result for computation;
it is not Run deduplication. Every independent submission still creates a Run.
A reused Task records its original producing attempt/output identities and
reason, with no synthetic process attempt or new artifact producer.

The default scope is global within this configured project and accessible store,
subject to compiled KFP cache policy. Compiled enable_cache=false and local
cache_safe=false always disable substitution. Missing implementation/environment/
input identity, mutable unverified data or
untracked upstream local-cache results disable reuse. Explain the reason in
the plan. A caller's scope/key cannot override these conditions.

| Scope | Meaning |
| --- | --- |
| global | Equivalent committed results in the same project's permitted catalog/store. |
| keyed | Same equivalence plus the same caller-supplied namespaced key. |
| run | Same equivalence within this Run's pre-dispatch scope token. |
| none | Execute selected tasks; no historical substitution. |

Resolve task scope from explicit task policy, submission override, configuration,
then global default; compiled cache disablement remains strongest. A keyed scope
requires a nonempty key before acceptance. Experiments and display names are not
cache identity. Opaque application keys have no business meaning to Dockflow.
The selected scope/key is recorded; do not persist credentials as keys.

Compiled KFP cache enablement is the author's declaration that reuse is safe;
Dockflow cannot prove arbitrary container code deterministic. Known or declared
mutable dependencies must be versioned or disable caching. The pinned KFP default
when cache policy is absent must be recorded in the compatibility manifest.

A component depending on time, randomness, mutable external lookups, network
responses or output-path identity must disable reuse or declare/resolve those
dependencies as computational inputs. A negative lookup is not an immutable
artifact; missing external data must be rechecked when the graph executes again.

## Signature format

Use a versioned signature envelope with algorithm sha256 and format
dockflow-task-signature-v1. Include:

- Project identity, scope policy and resolved scope key/token.
- The selected component's normalized executable definition, command/arguments,
  declared input/output contracts and any result-affecting adapter mapping.
- Resolved computational parameter values including defaults, by name and type.
- Named input artifact identities/fingerprints, type/version, consumer-visible
  metadata and source revision where applicable.
- Actual immutable image identity and selected OS/architecture, explicit
  result-affecting environment/resource configuration, and execution/adapter
  compatibility identity.

Do not hash the entire pipeline, unrelated downstream parameters, timestamps,
Run/attempt IDs (except run scope token), work/output directories, credentials,
pure display metadata or unrelated tasks. Preserve dependency locality: changing
a downstream training parameter must not invalidate unchanged preparation work.
For nested graphs use actual primitive invocation bindings and qualified paths;
graph display/name changes alone are not a new computation.

Treat credentials as access mechanisms; include non-secret endpoint/namespace/
dataset-version identity where it affects which data is observed. Input artifact
URIs that are observably meaningful to the computation belong in its identity.
Physical materialization paths are execution details; path-sensitive computations
must disable reuse. Materializing a registered artifact retains its logical identity; independently
registering equal bytes may create a distinct identity. Content deduplication
across unrelated artifact IDs is not required initially.

## Canonical digest encoding

Use dockflow-json-v1 for all normalized JSON digest views. This is an explicit
typed tree, not an ordinary serializer's incidental representation:

| JSON value | Canonical tree node |
| --- | --- |
| null | ["null"] |
| boolean | ["bool", true-or-false] |
| integer | ["int", decimal-string] |
| float | ["float64", sixteen-lowercase-hex-digits] |
| string | ["string", exact-string] |
| array | ["array", ordered-list-of-canonical-nodes] |
| object | ["object", ordered-list-of-[key,canonical-node]-pairs] |

Integer strings have no leading plus/zeros; zero is "0". Portable JSON and KFP
integer parameter values are limited to plus/minus 9007199254740991; reject
larger integers instead of rounding. Float digits are the big-endian IEEE754
binary64 bit pattern; reject NaN/infinities, retain signed zero distinctly.
Preserve string contents without case/Unicode normalization; reject unpaired
surrogates. Sort object keys by Unicode code point, preserve array order,
serialize the tree as compact UTF-8 JSON with no insignificant whitespace and
literal non-ASCII characters, then hash those bytes with SHA-256.

Typed KFP NUMBER_DOUBLE inputs are encoded as float64 even when their JSON spelling
is integral; NUMBER_INTEGER inputs use integer encoding. No string/number/bool
coercion occurs. Definition hashing retains original-byte SHA-256 for source
identity separately from normalized semantic hashing for reuse. Persist the
format/adapter version. [Canonical digest vectors](resources/canonical-digests.json)
provide normative primitive/container examples for independent implementations.

Filesystem payload SHA-256 hashes bytes directly. Directory fingerprints hash a
canonical ordered inventory of relative POSIX paths, entry kind, file byte
length/SHA-256 and empty-directory entries, as defined in
[Artifacts](006_artifacts.md). Metadata-only artifacts hash their declared type
and canonical metadata. The digest format is part of persisted compatibility.

## Candidate selection and substitution

Select the latest compatible successful producing attempt by committed completion
time, with attempt ID ascending as deterministic tie break. Before substitution
verify signature/profile equivalence, complete output-set commit, metadata
consistency, required output accessibility and integrity, and retained lifecycle
status. An unavailable/corrupt result is a cache miss even if history says success.
Do not choose an incompatible candidate merely because its data is accessible.

Record candidate rejections, chosen producer and per-output binding in the Task
manifest. Materialize historical inputs beneath the current runner-visible root
and acquire active references before dispatch. Never expose another Run's
unprotected private path directly. Reuse cannot create new computation provenance.

## Partial execution and explicit historical inputs

--from TASK selects that qualified task and its downstream closure.
--tasks selects exactly the named task subset. These options are mutually
exclusive. Initial partial execution supports static acyclic regions only;
reject selections crossing conditional, loop or unsupported graph boundaries.
Qualified nested task paths are unambiguous and retained in the accepted plan.

Resolve omitted prerequisites from explicit artifact bindings, an explicitly
selected producing attempt's named outputs, or verified compatible historical
results, in that order. Preflight all resolved prerequisite bindings before
dispatch and reject unresolved/ambiguous/incompatible/unavailable inputs.
Do not silently run omitted prerequisites; users can submit a larger selection.

An omitted ordering-only dependency, including an explicit after edge, requires
a compatible historical successful producer satisfying the same reuse/safety
policy, even when its committed output set is empty. Otherwise reject the
selection or include that prerequisite explicitly. Binding artifact inputs alone
cannot erase a control dependency or assert that its external effects happened.

--bind TASK.INPUT=ARTIFACT_ID intentionally supplies that input after contract/
availability checks. --use-execution TASK=ATTEMPT_ID selects a producer whose
named outputs satisfy the omitted prerequisite task's output contract. This may
be a deliberate different historical dataset; record it as a manual input choice,
not an equivalent cache hit. The consuming task's signature includes the actual
bound inputs.

Every partial request creates a new Run with its exact selection and resolved
producers. Show the plan/provenance before execution, including cached and manual
bindings. Equivalent selected tasks still obey scope/cache policy. --scope none
forces selected computation; it does not invent missing prerequisites.

Active Run references and explicit retained pins protect source artifacts from
cleanup. Pins survive process restarts until explicitly removed. Pinning affects
retention, not equivalence or data integrity. Rebuild/reconciliation preserves
reuse and manual-selection provenance.
