# Quickstart project

This small, self-contained project generates integers and calculates their count,
sum and mean. Follow the [tutorial](../../docs/quickstart.md) from the repository
root. It needs no external data or Python packages inside its component image.

`components/*/main.py` are independent programs with ordinary path arguments.
KFP wrappers are under `orchestration/kfp/definitions/`; the checked-in compiled
definition is under `orchestration/kfp/compiled/`. Dockflow reads that definition
and runs the prepared image. It does not import the wrappers or compile Python.

The configuration keeps state, artifacts and execution work under this example.
Those generated directories are ignored by Git. The example deliberately uses
`images.pull_policy = "never"`: build the image in the selected engine first.

To regenerate the definition after changing its wrappers, from the repository root:

```bash
uv run --all-packages --all-extras python examples/quickstart/orchestration/kfp/compile.py
```

Rebuild and change the component image tag when changing its code. For a
deployment, compile with an image reference reachable by that deployment's
Docker engine; use an immutable digest when distributing it to other hosts.
