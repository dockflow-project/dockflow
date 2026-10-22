"""Installed-distribution extension discovery and the shared command boundary."""

import re
import sys
from importlib import metadata

import typer
from typer.main import get_command


def _provider(entry) -> str:
    dist = getattr(entry, "dist", None)
    return f"{dist.name} ({entry.value})" if dist else entry.value


def create_app() -> typer.Typer:
    app = typer.Typer(
        add_completion=False,
        no_args_is_help=False,
        help="Dockflow — installed workflow tools.",
        pretty_exceptions_enable=False,
    )
    entries = sorted(
        metadata.entry_points(group="dockflow_cli.modules"),
        key=lambda entry: (entry.name, _provider(entry)),
    )
    seen = {}
    for entry in entries:
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", entry.name):
            raise RuntimeError(f"Invalid module {entry.name!r} from {_provider(entry)}")
        if entry.name in {"help", "version"} or entry.name in seen:
            other = _provider(seen[entry.name]) if entry.name in seen else "built-in"
            raise RuntimeError(
                f"Module {entry.name!r} conflicts: {_provider(entry)} and {other}"
            )
        seen[entry.name] = entry
    for entry in entries:
        try:
            plugin = entry.load()
            if not isinstance(plugin, typer.Typer):
                raise TypeError("entry point must export a typer.Typer instance")
            get_command(plugin)
            app.add_typer(plugin, name=entry.name)
        except Exception as exc:
            raise RuntimeError(
                f"Cannot load module {entry.name!r} from {_provider(entry)}: {exc}"
            ) from exc

    @app.callback(invoke_without_command=True)
    def root(
        ctx: typer.Context,
        version: bool = typer.Option(
            False, "--version", help="Show the installed Dockflow version."
        ),
    ):
        if ctx.invoked_subcommand is None:
            typer.echo(ctx.get_help())
            if not entries:
                typer.echo(
                    "Install a Dockflow feature package in this Python environment "
                    "to add command groups."
                )

    return app


def main() -> None:
    """Run the console host, preserving deliberate command exit statuses."""
    # Root options precede module words. Never discover providers for --version.
    root_args = sys.argv[1:]
    if root_args and root_args[0] == "--version":
        if len(root_args) != 1:
            typer.echo("--version does not accept command arguments", err=True)
            raise SystemExit(2)
        try:
            typer.echo(f"dockflow {metadata.version('dockflow-cli')}")
        except metadata.PackageNotFoundError:
            typer.echo(
                "dockflow-cli metadata is missing; reinstall dockflow-cli", err=True
            )
            raise SystemExit(1) from None
        return
    try:
        create_app()()
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as exc:
        typer.echo(f"Dockflow: {exc}", err=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
