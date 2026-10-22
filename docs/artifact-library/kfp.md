# KFP integration

Install the `kfp` extra in the authoring environment and the `s3` extra in
component images that publish to object storage. The qualified SDK is KFP 2.17.0.
Standalone authoring installs also need the documented
[KFP dependency override](../installation.md#kfp-dependency-override); the locked
Dockflow workspace applies it automatically.

A component wrapper runs the independent business script into a temporary output
directory, calls `Publisher.publish`, then returns `receipt.uri` as a string.
For this output it does not declare an automatically uploaded `Output[Model]`.
The pipeline registers the URI using the standard importer:

```python
from kfp import dsl
from dockflow_artifacts.kfp import importer_component

import_model = importer_component(dsl.Model, name="import-published-model")

@dsl.pipeline
def workflow():
    produced = training_wrapper()  # Your wrapper returns a URI string.
    model = import_model(uri=produced.output).set_display_name("Published model")
    evaluate(model=model.output)
```

`training_wrapper` and `evaluate` are your project components. See the complete
[synthetic authoring example](../../packages/artifacts/examples/kfp_pipeline.py).

Create the importer component **outside** the parent pipeline function, as in
the example. It contains a standard typed importer in a small sub-pipeline.
This exposes the published URI as a parent input: native KFP 2.17
[cannot resolve an upstream task parameter directly in its importer](https://github.com/kubeflow/pipelines/blob/2.17.0/backend/src/v2/component/importer_launcher.go).
The adapter uses supported nested graph IR and needs no KFP changes. Static JSON
metadata and `reimport` may be configured on the factory; dynamic metadata
channels are outside this initial portable contract.

The helper is usable with native KFP and Dockflow's supported importer profile. Model/Dataset typing and metadata remain
available, but the graph and artifact lineage include the importer. The
training task produces the URI parameter rather than a direct artifact output.
KFP's [importer documentation](https://www.kubeflow.org/docs/components/pipelines/user-guides/components/importer-component/)
explains this contract.

There is one durable payload copy. Temporary producer files and consumer
downloads can still exist. Native metadata-only Metrics artifacts can coexist.
Cached or reused executions keep their original URI. If destination context is
a changing pipeline input, it can prevent a cache hit. Immutable paths are
essential: KFP caching is not a replacement for content integrity checks.

The deployment must give publishing containers storage access and give the
orchestrator access to import the same URIs. Mount filesystem roots consistently
or configure S3 endpoints/credentials on both sides. Kubernetes secrets and
trusted Docker task mounts are deployment concerns. Do not put credentials in
compiled YAML. A host `file://` path is not automatically available in a pod.

Custom publications are external references to Dockflow; allow their URI prefix
or filesystem root explicitly. Their retention and backup belong to the custom
store. No changes to Dockflow's default managed artifact layout are necessary.

For deterministic naming, the pipeline passes `pipeline_name`, `exploration_id`
(default `global`), `step_number`, `step_digits` and `component_version` as real
inputs to every publishing wrapper. Declare computational steps in order and
compute `step_digits = len(str(len(steps)))`; importers do not consume numbers.
The wrapper calculates `publication_id` from those resolved parameters, its
business parameters and input fingerprints, then calls `step_path`. See the
[complete naming example](storage.md#deterministic-exploration-paths).

The pipeline name is part of cache context even when two pipelines call the
same component. Within the same pipeline/context, repeated identical inputs
can reuse native cache entries and return the same URI; changed parameters
produce another component directory beneath the pipeline. Renaming a pipeline,
changing exploration or changing step width intentionally changes invocation
inputs. No random execution ID is passed. Independently registered artifacts
with identical bytes may still have different native cache identities.

Use immutable/versioned external sources. A publication ID is computed only
when a wrapper runs; it cannot make native KFP rehash mutable external objects
before a cache hit. Disable caching or change the source version when needed.
