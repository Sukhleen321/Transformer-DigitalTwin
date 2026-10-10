"""Inspect a newly built local image without starting an API or database."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE = """
import hashlib,json,importlib
from pathlib import Path
from app.core.config import Settings
from app.main import create_app
from ml.demo_physics.fleet import asset_ids
from ml.pipeline import PipelineSession
mods=['app.core.config','app.services.demo_telemetry','app.services.live_physics_demo',
      'app.services.ingestion_service','ml.demo_physics.scenario','ml.demo_physics.fem',
      'ml.demo_physics.fleet']
s=Settings(_env_file=None)
paths=create_app().openapi()['paths']
print(json.dumps({
 'default_demo_enabled':s.live_physics_demo_enabled,
 'default_physics_enabled':s.physics_enabled,
 'production_route_present':'/api/v1/transformers/{transformer_id}/physics' in paths,
 'demo_route_present':'/api/v1/demo/transformers/{transformer_id}/physics' in paths,
 'fleet_assets':asset_ids('/config/operational-fleet.json'),
 'source_hashes':{m:hashlib.sha256(Path(importlib.import_module(m).__file__).read_bytes()).hexdigest()
                  for m in mods},
 'demo_ml_configuration':PipelineSession().pipeline.bundle.configuration_readiness}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{32}", args.tag) is None:
        parser.error("Use the launcher's new UUID image tag")
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "python",
            "--env",
            "ML_RUNTIME_MODE=DEMO_UNVERIFIED_CONFIG",
            "--mount",
            f"type=bind,src={ROOT / 'simulator/config'},dst=/config,readonly",
            f"transformer-physics-demo-backend:{args.tag}",
            "-c",
            CODE,
        ],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=True,
    )
    data = json.loads(result.stdout)
    for module, digest in data["source_hashes"].items():
        relative = module.replace(".", "/") + ".py"
        if module.startswith("app."):
            relative = "backend/" + relative
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Image is stale for source module: " + module)
    assert not data["default_demo_enabled"] and not data["default_physics_enabled"]
    assert data["production_route_present"] and data["demo_route_present"]
    assert len(data["fleet_assets"]) == 10
    data.update(image_tag=args.tag, all_source_hashes_match=True, application_stack_started=False)
    evidence = ROOT / "docs/evidence/ten_transformer/image-source-check.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(data, indent=2) + "\n")
    print("Image source/import/default-flag checks: PASS; no application stack started")


if __name__ == "__main__":
    main()
