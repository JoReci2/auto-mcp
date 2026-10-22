"""Explicit model downloads; never called during server startup or inference."""

import importlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType


class ModelDownloadError(ValueError):
    """An explicit model download cannot be completed safely."""


def _validate_model(path: Path) -> None:
    files = list(path.rglob("*"))
    if any(p.is_symlink() for p in files):
        raise ModelDownloadError("Downloaded model must not contain symlinks")
    modules = json.loads((path / "modules.json").read_text(encoding="utf-8"))
    if not isinstance(modules, list) or not modules:
        raise ModelDownloadError("Expected a Sentence Transformers modules.json pipeline")
    for module in modules:
        name = module.get("path") if isinstance(module, dict) else None
        if not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ModelDownloadError("Invalid model module path")
        kind = module.get("type")
        if not isinstance(kind, str) or not kind.startswith("sentence_transformers."):
            raise ModelDownloadError("Only standard Sentence Transformers modules are supported")
    if not any(p.suffix in {".safetensors", ".bin"} for p in files if p.is_file()):
        raise ModelDownloadError("Model weights are missing")


@contextmanager
def _reserve(destination: Path) -> Iterator[None]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.with_name(destination.name + ".download.lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        if destination.exists() or destination.is_symlink():
            raise ModelDownloadError("Destination already exists; choose a new directory")
        yield
    finally:
        lock.unlink(missing_ok=True)


def _load_hub() -> ModuleType:
    try:
        return importlib.import_module("huggingface_hub")
    except ImportError:
        raise ModelDownloadError("Install yamcps[models] to download models") from None


def download_model(
    repo_id: str, *, revision: str = "main", destination: Path | None = None
) -> Path:
    """Download a pinned Hugging Face Sentence Transformers snapshot to local files.

    Args:
        repo_id: Hugging Face model identifier, for example organization/model.
        revision: Branch, tag or commit to resolve to an immutable commit.
        destination: New directory; otherwise use YAMCPS_MODELS_DIR/repo/commit.

    Returns:
        Absolute model directory usable by RagConfig.model_path.

    Raises:
        ModelDownloadError: Dependency missing, invalid input, occupied destination,
            incompatible model layout or download failure. Raw provider errors are hidden.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo_id):
        raise ModelDownloadError("Use a Hugging Face model identifier in organization/model form")
    if ".." in repo_id or "--" in repo_id or not revision.strip():
        raise ModelDownloadError("Invalid model identifier or revision")
    hub = _load_hub()
    try:
        token = os.environ.get("HF_TOKEN") or False
        api = hub.HfApi(endpoint="https://huggingface.co", token=token)
        info = api.model_info(repo_id, revision=revision, timeout=30)
        commit = info.sha
        weights = (
            "*.safetensors"
            if any(
                f.rfilename.endswith(".safetensors")
                and not f.rfilename.startswith(("onnx/", "openvino/", "pytorch/"))
                for f in (info.siblings or [])
            )
            else "*.bin"
        )
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            raise ModelDownloadError("The provider did not resolve an immutable model revision")
        root = Path(os.environ.get("YAMCPS_MODELS_DIR", "~/.local/share/yamcps/models"))
        target = (
            (destination if destination is not None else root / repo_id.replace("/", "--") / commit)
            .expanduser()
            .absolute()
        )
        with _reserve(target):
            with tempfile.TemporaryDirectory(
                prefix=".yamcps-model-", dir=target.parent
            ) as temporary:
                staged = Path(temporary) / "model"
                hub.snapshot_download(
                    repo_id=repo_id,
                    revision=commit,
                    repo_type="model",
                    local_dir=str(staged),
                    endpoint="https://huggingface.co",
                    token=token,
                    allow_patterns=[
                        "*.json",
                        weights,
                        "*.txt",
                        "*.model",
                        "*.vocab",
                        "*.merges",
                        "*.tiktoken",
                        "*.md",
                        "LICENSE*",
                    ],
                    ignore_patterns=["onnx/*", "openvino/*", "pytorch/*", "*.py"],
                )
                _validate_model(staged)
                # Hub bookkeeping is not model content and must not affect its fingerprint.
                cache = staged / ".cache"
                if cache.exists():
                    shutil.rmtree(cache)
                (staged / "yamcps-model.json").write_text(
                    json.dumps(
                        {
                            "repo_id": repo_id,
                            "revision": revision,
                            "commit": commit,
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                staged.rename(target)
        return target
    except ModelDownloadError:
        raise
    except Exception:
        raise ModelDownloadError(
            "Model download failed. Check connectivity, model/revision, access rights, "
            "available disk space and destination; an active download may hold its lock."
        ) from None
