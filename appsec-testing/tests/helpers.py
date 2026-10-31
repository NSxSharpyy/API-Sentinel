"""Shared test helper: load a service app from its folder."""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_app(service_dir):
    folder = ROOT / "services" / service_dir
    sys.path.insert(0, str(folder))
    try:
        spec = importlib.util.spec_from_file_location(
            f"{service_dir}_app", folder / "app.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.app
    finally:
        sys.path.remove(str(folder))
