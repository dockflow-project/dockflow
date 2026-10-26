#!/usr/bin/env python3
"""Serve a fresh disposable project for real browser/Docker qualification.

The supplied directory must not exist and must be beneath repository tmp/ or the
system temporary directory. The fixture uses an already cached Python image;
it never pulls images, resets existing state or touches a running user service.
Stop it with Ctrl+C or SIGTERM. Its disposable state remains for inspection.
"""

from __future__ import annotations

import argparse
import csv
import json
import socket
import struct
import tempfile
import uuid
import zlib
from pathlib import Path

IMAGE = "python:3.13-slim"


def contents_samples(directory: Path) -> list[tuple[Path, str]]:
    """Portable, generated data for preview qualification and manual inspection."""
    root = directory / "inputs" / "contents"
    root.mkdir(parents=True, exist_ok=False)
    dataset = root / "large.csv"
    with dataset.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", "label", "value", "notes"])
        for index in range(250000):
            writer.writerow(
                [
                    index,
                    f"Sample {index}",
                    index / 10,
                    'Quoted "text", café' if index % 2 else "Two\nlines",
                ]
            )
    data = root / "data.json"
    data.write_text(
        json.dumps(
            {
                "info": {
                    "title": "Example contents",
                    "large_number": 9007199254740993,
                    "literal_text": "<img src=x onerror=alert(1)>",
                },
                "items": [
                    {"id": i, "active": i % 2 == 0, "value": None} for i in range(250)
                ],
            },
            indent=2,
        )
    )
    width, height = 320, 160

    def chunk(name, payload):
        return (
            struct.pack(">I", len(payload))
            + name
            + payload
            + struct.pack(">I", zlib.crc32(name + payload))
        )

    pixels = b"".join(
        b"\0"
        + bytes(
            component
            for x in range(width)
            for component in (x * 255 // width, y * 255 // height, 160)
        )
        for y in range(height)
    )
    image = root / "image.png"
    image.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )
    text = root / "notes.txt"
    text.write_text("Example UTF-8 text: café.\n" * 5000)
    directory_root = root / "directory"
    (directory_root / "empty").mkdir(parents=True)
    nested = directory_root / "nested"
    (nested / "tables").mkdir(parents=True)
    (nested / "data.json").write_bytes(data.read_bytes())
    (nested / "broken.json").write_text('{"incomplete":')
    (directory_root / "image.png").write_bytes(image.read_bytes())
    (directory_root / "README.txt").write_text(
        "A registered directory with nested preview examples.\n"
    )
    (directory_root / "unknown.bin").write_bytes(b"binary\0example")
    with (nested / "tables" / "example.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", "label"])
        writer.writerows([i, f"Nested sample {i}"] for i in range(350))
    return [
        (dataset, "Preview CSV"),
        (data, "Preview JSON"),
        (image, "Preview image"),
        (directory_root, "Preview directory"),
        (text, "Preview text"),
    ]


PREPARE = """import json,pathlib,sys,time
request=json.loads(sys.argv[1])
parameters=request['inputs']['parameterValues']
value=int(parameters['value'])
delay=int(parameters['delay_seconds'])
if not 0 <= delay <= 60:
    raise ValueError('delay_seconds must be between 0 and 60')
print('Preparing dataset for value',value,flush=True)
time.sleep(delay)
outputs=request['outputs']['artifacts']
dataset=pathlib.Path(outputs['dataset']['artifacts'][0]['uri'])
dataset.parent.mkdir(parents=True,exist_ok=True)
dataset.write_text(json.dumps({'value':value}))
wire={'parameterValues':{'base':value*2},'artifacts':{}}
for name,output in outputs.items():
    metadata={'rows':1} if name=='dataset' else {'score':value/10.0,'samples':1}
    wire['artifacts'][name]={'artifacts':[{'name':name,'uri':output['artifacts'][0]['uri'],'metadata':metadata}]}
pathlib.Path(request['outputs']['outputFile']).write_text(json.dumps(wire))
print('Dataset and metrics prepared',flush=True)
"""

SUMMARIZE = """import json,pathlib,sys
request=json.loads(sys.argv[1])
parameters=request['inputs']['parameterValues']
if parameters['fail']:
    print('Intentional browser fixture failure',file=sys.stderr,flush=True)
    raise SystemExit(23)
dataset=pathlib.Path(request['inputs']['artifacts']['dataset']['artifacts'][0]['uri'])
result=int(parameters['base'])+json.loads(dataset.read_text())['value']
pathlib.Path(request['outputs']['outputFile']).write_text(json.dumps({'parameterValues':{'result':result}}))
print('Computed result:',result,flush=True)
"""


def pipeline() -> dict:
    integer = {"parameterType": "NUMBER_INTEGER"}
    boolean = {"parameterType": "BOOLEAN"}
    dataset = {
        "artifactType": {"schemaTitle": "system.Dataset", "schemaVersion": "0.0.1"}
    }
    metrics = {
        "artifactType": {"schemaTitle": "system.Metrics", "schemaVersion": "0.0.1"}
    }
    return {
        "pipelineInfo": {"name": "browser-qualification"},
        "schemaVersion": "2.1.0",
        "sdkVersion": "kfp-2.17.0",
        "components": {
            "comp-prepare": {
                "executorLabel": "exec-prepare",
                "inputDefinitions": {
                    "parameters": {"value": integer, "delay_seconds": integer}
                },
                "outputDefinitions": {
                    "parameters": {"base": integer},
                    "artifacts": {"dataset": dataset, "metrics": metrics},
                },
            },
            "comp-summarize": {
                "executorLabel": "exec-summarize",
                "inputDefinitions": {
                    "parameters": {"base": integer, "fail": boolean},
                    "artifacts": {"dataset": dataset},
                },
                "outputDefinitions": {"parameters": {"result": integer}},
            },
        },
        "deploymentSpec": {
            "executors": {
                "exec-prepare": {
                    "container": {
                        "image": IMAGE,
                        "command": ["python", "-c", PREPARE],
                        "args": ["{{$}}"],
                    }
                },
                "exec-summarize": {
                    "container": {
                        "image": IMAGE,
                        "command": ["python", "-c", SUMMARIZE],
                        "args": ["{{$}}"],
                    }
                },
            }
        },
        "root": {
            "inputDefinitions": {
                "parameters": {
                    "value": {**integer, "defaultValue": 7.0},
                    "delay_seconds": {**integer, "defaultValue": 0.0},
                    "fail": {**boolean, "defaultValue": False},
                }
            },
            "outputDefinitions": {
                "parameters": {"result": integer},
                "artifacts": {"metrics": metrics},
            },
            "dag": {
                "tasks": {
                    "prepare": {
                        "componentRef": {"name": "comp-prepare"},
                        "cachingOptions": {"enableCache": True},
                        "inputs": {
                            "parameters": {
                                "value": {"componentInputParameter": "value"},
                                "delay_seconds": {
                                    "componentInputParameter": "delay_seconds"
                                },
                            }
                        },
                    },
                    "summarize": {
                        "componentRef": {"name": "comp-summarize"},
                        "cachingOptions": {"enableCache": True},
                        "inputs": {
                            "parameters": {
                                "base": {
                                    "taskOutputParameter": {
                                        "producerTask": "prepare",
                                        "outputParameterKey": "base",
                                    }
                                },
                                "fail": {"componentInputParameter": "fail"},
                            },
                            "artifacts": {
                                "dataset": {
                                    "taskOutputArtifact": {
                                        "producerTask": "prepare",
                                        "outputArtifactKey": "dataset",
                                    }
                                }
                            },
                        },
                    },
                },
                "outputs": {
                    "parameters": {
                        "result": {
                            "valueFromParameter": {
                                "producerSubtask": "summarize",
                                "outputParameterKey": "result",
                            }
                        }
                    },
                    "artifacts": {
                        "metrics": {
                            "artifactSelectors": [
                                {
                                    "producerSubtask": "prepare",
                                    "outputArtifactKey": "metrics",
                                }
                            ]
                        }
                    },
                },
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Seed disposable manual artifacts and orphan files for cleanup testing",
    )
    parser.add_argument(
        "--contents",
        action="store_true",
        help="Seed generated CSV, JSON, image, directory and text previews",
    )
    arguments = parser.parse_args()
    directory = arguments.directory.resolve()
    allowed = (
        Path(__file__).resolve().parents[1] / "tmp",
        Path(tempfile.gettempdir()).resolve(),
    )
    if directory.exists():
        parser.error("--directory must be a new, absent directory")
    if not any(directory.is_relative_to(parent) for parent in allowed):
        parser.error("--directory must be below repository tmp/ or system temp")
    if not 0 <= arguments.port <= 65535:
        parser.error("--port must be between 0 and 65535 (0 selects a free port)")
    token_file = arguments.token_file.resolve() if arguments.token_file else None
    if token_file and not token_file.is_file():
        parser.error("--token-file must identify an existing secret file")

    import docker
    import uvicorn
    from dockflow_pipelines.config import load_settings
    from dockflow_pipelines.definitions import load_definition
    from dockflow_pipelines.service import create_app

    document = pipeline()
    load_definition(document)
    client = docker.from_env()
    try:
        client.ping()
        image = client.images.get(IMAGE)
        image_id = image.id
    finally:
        client.close()

    # Reserve the selected port until Uvicorn takes over, avoiding a port race.
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", arguments.port))
    listener.listen(128)
    port = listener.getsockname()[1]
    project_id = "web-fixture-" + uuid.uuid4().hex
    try:
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "inputs").mkdir()
        (directory / "inputs" / "external.csv").write_text("feature,label\n1,0\n2,1\n")
        compiled = directory / "pipeline.json"
        compiled.write_text(json.dumps(document, indent=2) + "\n")
        config = directory / "pipelines.toml"
        text = (
            f"schema_version=1\n[project]\nid={json.dumps(project_id)}\n"
            '[images]\npull_policy="never"\n'
            '[artifacts]\nexternal_roots=["inputs"]\n'
            f'[service]\nhost="127.0.0.1"\nport={port}\n'
            "[execution]\nshutdown_grace_seconds=3\n"
        )
        if token_file:
            text = text.replace(
                "[service]\n",
                "[service]\ntoken_file=" + json.dumps(str(token_file)) + "\n",
            )
        config.write_text(text)
        app = create_app(load_settings(config), execute=True)
        if arguments.cleanup:
            import sqlite3

            database = directory / "inputs" / "manual-database.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE example (value TEXT)")
                connection.execute(
                    "INSERT INTO example VALUES ('disposable test data')"
                )
            core = app.state.core
            with core.store.owner():
                core.initialize()
                core.upload_pipeline(json.dumps(document), "Cleanup test pipeline")
                typ = {"schema_title": "system.Dataset", "schema_version": "0.0.1"}
                core.artifacts.register(
                    database.as_uri(),
                    typ,
                    managed=True,
                    version="Manual database snapshot",
                )
                pinned = core.artifacts.register(
                    (directory / "inputs/external.csv").as_uri(),
                    typ,
                    managed=True,
                    version="Pinned manual dataset",
                )
                core.artifacts.pin(pinned["artifact_id"], True)
                (core.artifacts.managed_root / "cleanup-orphan.bin").write_bytes(
                    b"disposable orphan\n" * 64
                )
        if arguments.contents:
            core = app.state.core
            with core.store.owner():
                core.initialize()
                for source, label in contents_samples(directory):
                    core.artifacts.register(
                        source.as_uri(),
                        {"schema_title": "system.Dataset", "schema_version": "0.0.1"},
                        managed=True,
                        version=label,
                    )
        print(
            json.dumps(
                {
                    "event": "fixture_prepared",
                    "directory": str(directory),
                    "config": str(config),
                    "compiled_pipeline": str(compiled),
                    "external_artifact_uri": (
                        directory / "inputs" / "external.csv"
                    ).as_uri(),
                    "endpoint": f"http://127.0.0.1:{port}",
                    "project_id": project_id,
                    "image": IMAGE,
                    "image_id": image_id,
                    "authenticated": token_file is not None,
                    "ready_probe": "/health/ready",
                    "expected_default_result": 21,
                }
            ),
            flush=True,
        )
        uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port)).run(
            sockets=[listener]
        )
        return 0
    finally:
        listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
