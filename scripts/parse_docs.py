#!/usr/bin/env python3

import argparse
import shutil
from pathlib import Path
from loguru import logger

from parser.mdx_converter import generate_mdx_docs
from utils import ensure_directories

DEFAULT_BUILD_DIR = Path("build")
DEFAULT_RAW_DOCS_DIR = DEFAULT_BUILD_DIR / "json"
DEFAULT_OUTPUT_DIR = Path("dist")

def build_docs_for_version(version: str, data_dir: Path, output_dir: Path, is_latest: bool, enable_i18n: bool = False, json_slug: str = "docs"):
    logger.info(f"Building mdx docs for version: {version}")
    
    final_output_dir = output_dir / version

    if final_output_dir.exists():
        shutil.rmtree(final_output_dir)
    
    final_output_dir.mkdir(parents=True, exist_ok=True)
    
    json_filename = f"{json_slug}_{version}.json"
    json_path = data_dir / json_filename

    if not json_path.exists():
        logger.error(f"JSON for {version} does not exist at path: {json_path}, generate it using fetch_json.py")
        return

    logger.info(f"Generating MDX for {version} into {final_output_dir}")
    generate_mdx_docs(json_path, final_output_dir, version, is_latest) # TODO: i18n (versioning) dynamic links
    
    logger.success(f"Completed {version}")


def parse_args():
    parser = argparse.ArgumentParser(description="Typst Docs to MDX Converter CLI")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_RAW_DOCS_DIR, help="JSON output data directory")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--enable-i18n", action="store_true", help="Enable i18n")
    parser.add_argument("--version", type=str, help="Version to build")
    parser.add_argument("--unpack-latest", action="store_true", help="Unpack latest version")
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.data_dir.exists():
        logger.error(f"Data directory {args.data_dir} does not exist, generate it using fetch_json.py")
        exit(1)
    
    if not args.version:
        target_versions = []
        target_files = list(args.data_dir.iterdir())

        if len(target_files) == 0:
            logger.error(f"No files found in {args.data_dir}")
            exit(1)
        
        for child in target_files:
            if child.suffix != ".json":
                logger.warning("Skipping non-JSON file: " + child.name)
                continue
            target_versions.append(child.stem.split("_")[1])
    else:
        target_versions = [args.version]

    ensure_directories([args.output_dir])

    shutil.rmtree(args.output_dir, ignore_errors=True)
    
    for version in target_versions:
        is_latest = version == target_versions[-1]
        build_docs_for_version(version, args.data_dir, args.output_dir, is_latest, args.enable_i18n)
    
    if args.unpack_latest:
        target_version_path = args.output_dir / target_versions[-1]
        if not target_version_path.exists():
            logger.error(f"Docs for version {target_versions[-1]} does not exist for some reason, cannot unpack")
            exit(1)
        shutil.copytree(target_version_path, args.output_dir, dirs_exist_ok=True)
        shutil.rmtree(target_version_path)

if __name__ == "__main__":
    main()
