import argparse
import json
import os
import tarfile
import time
import io
from pathlib import Path

import zstandard as zstd
from zst_model_archive import INDEX_MEMBER


def iter_model_dirs(models_dir: Path, names: list[str]) -> list[Path]:
    if names:
        return [models_dir / name for name in names]
    return [
        path for path in sorted(models_dir.iterdir())
        if path.is_dir() and not path.name.startswith("_")
    ]


def collect_model_files(source_dir: Path) -> list[tuple[Path, str]]:
    result = []
    for root, dirs, files in os.walk(source_dir):
        dirs.sort()
        files.sort()
        root_path = Path(root)
        for filename in files:
            file_path = root_path / filename
            arcname = file_path.relative_to(source_dir).as_posix()
            result.append((file_path, arcname))
    return result


def add_index(tar: tarfile.TarFile, files: list[tuple[Path, str]]):
    data = json.dumps({"files": [arcname for _path, arcname in files]}, separators=(",", ":")).encode("utf-8")
    info = tarfile.TarInfo(INDEX_MEMBER)
    info.size = len(data)
    info.mtime = int(time.time())
    tar.addfile(info, io.BytesIO(data))


def add_directory_contents(tar: tarfile.TarFile, files: list[tuple[Path, str]]):
    for file_path, arcname in files:
        tar.add(file_path, arcname=arcname, recursive=False)


def convert_model_dir(source_dir: Path, output_path: Path, level: int, force: bool):
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Model directory not found: {source_dir}")
    if output_path.exists() and not force:
        print(f"skip {source_dir.name}: {output_path.name} already exists")
        return

    compressor = zstd.ZstdCompressor(level=level)
    files = collect_model_files(source_dir)
    with output_path.open("wb") as raw_file:
        with compressor.stream_writer(raw_file, closefd=False) as zstd_file:
            with tarfile.open(fileobj=zstd_file, mode="w|") as tar:
                add_index(tar, files)
                add_directory_contents(tar, files)
    print(f"wrote {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert model folders under models/ into tar.zst archives without deleting folders."
    )
    parser.add_argument(
        "names",
        nargs="*",
        help="Optional model folder names to convert. Defaults to all non-underscore folders.",
    )
    parser.add_argument(
        "--models-dir",
        default="models",
        help="Models directory. Defaults to ./models.",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=10,
        help="Zstandard compression level. Defaults to 10.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .zst files.",
    )
    args = parser.parse_args()

    models_dir = Path(args.models_dir).resolve()
    if not models_dir.is_dir():
        raise FileNotFoundError(f"Models directory not found: {models_dir}")

    model_dirs = iter_model_dirs(models_dir, args.names)
    if not model_dirs:
        print("no model folders found")
        return

    for model_dir in model_dirs:
        output_path = models_dir / f"{model_dir.name}.zst"
        convert_model_dir(model_dir, output_path, args.level, args.force)


if __name__ == "__main__":
    main()
