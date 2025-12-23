import os
import re
import shutil
import argparse
import subprocess
from pathlib import Path

import semantic_version
from git import Repo
from loguru import logger
from rich.progress import Progress, SpinnerColumn, TextColumn

from utils import RichCloneProgress, run_process_with_progress, ensure_directories

SCCACHE_PATH = shutil.which("sccache")
if SCCACHE_PATH:
    logger.success(f"Found sccache at {SCCACHE_PATH}, build acceleration enabled")
else:
    logger.warning("sccache not found, using default cargo")

MINIMAL_TYPST_VERSION = "0.11.0" # Minimal Typst version with JSON docs

DEFAULT_BUILD_DIR = Path("build")
DEFAULT_OUTPUT_DIR = DEFAULT_BUILD_DIR / "json"
DEFAULT_ASSETS_DIR = DEFAULT_BUILD_DIR / "assets"

def get_pinned_rust_version(repo_dir: Path) -> str | None:
    ci_path = repo_dir / ".github" / "workflows" / "ci.yml"
    if ci_path.exists():
        try:
            content = ci_path.read_text(encoding="utf-8")
            match = re.search(r'rust-toolchain@(\d+\.\d+(?:\.\d+)?)', content) or \
                    re.search(r'toolchain:\s*"?(\d+\.\d+(?:\.\d+)?)"?', content)
            if match:
                logger.success(f"Found pinned Rust version from CI workflow: {match.group(1)}")
                return match.group(1)
        except Exception as e:
            logger.warning(f"Failed to parse Rust version from CI workflow: {e}")

    cargo_path = repo_dir / "Cargo.toml"
    if cargo_path.exists():
        try:
            content = cargo_path.read_text(encoding="utf-8")
            match = re.search(r'rust-version\s*=\s*"(\d+\.\d+(?:\.\d+)?)"', content)
            if match:
                logger.success(f"Found pinned Rust version from Cargo.toml: {match.group(1)}")
                return match.group(1)
        except Exception as e:
            logger.warning(f"Failed to parse Rust version from Cargo.toml: {e}")
    
    return None

def is_toolchain_installed(version: str) -> bool:
    if not version: return False
    try:
        result = subprocess.run(
            ["rustup", "toolchain", "list"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        return any(line.startswith(version) for line in result.stdout.splitlines())
    except subprocess.CalledProcessError:
        return False
    
def manage_toolchain(version: str, action: str):
    if not version or version == "stable":
        return

    cmd = ["rustup", "toolchain", action, version]
    if action == "install":
        cmd.extend(["--profile", "minimal", "--no-self-update"])
    
    logger.info(f"Rustup: {action} {version}...")
    
    try:
        subprocess.run(
            cmd, 
            check=True,
        )
        logger.success(f"Rust {version} {action}ed successfully")
    except subprocess.CalledProcessError:
        logger.error(f"Failed to {action} toolchain {version}")

def get_typst_repo(typst_dir: Path) -> Repo:
    REPO_URL = "https://github.com/typst/typst.git"
    
    if typst_dir.exists():
        logger.info(f"Opening existing repo at {typst_dir}")
        try:
            repo = Repo(typst_dir)
            logger.info("Fetching updates...")
            repo.remotes.origin.fetch()
            return repo
        except Exception as e:
            logger.error(f"Failed to open repo: {e}")
            exit(1)

    logger.info(f"Cloning {REPO_URL} (Blobless mode)...")
    try:
        repo = Repo.clone_from(
            REPO_URL, 
            typst_dir, 
            multi_options=["--filter=blob:none", "--no-checkout"],
            progress=RichCloneProgress()
        )
    except Exception as e:
        logger.error(f"Failed to clone {REPO_URL}: {e}")
        exit(1)
        
    return repo

def get_typst_tags(repo: Repo, min_version: str = MINIMAL_TYPST_VERSION) -> list[str]:
    tags = []
    semantic_min_version = semantic_version.Version(min_version)
    
    logger.info("Fetching and filtering tags...")
    
    for tag in repo.tags:
        name = tag.name
        clean_version = name.lstrip('v')
        
        try:
            ver = semantic_version.Version(clean_version)
            if ver >= semantic_min_version and not ver.prerelease:
                tags.append((name, ver))
        except ValueError:
            continue
            
    tags.sort(key=lambda x: x[1])
    sorted_tag_names = [t[0] for t in tags]
    
    logger.success(f"Found {len(sorted_tag_names)} relevant versions: {', '.join(sorted_tag_names)}")
    return sorted_tag_names


def should_build(target_version: str, output_dir: Path, assets_dir: Path):
    json_exists = (output_dir / f"docs_{target_version}.json").exists()
    assets_exist = (assets_dir / target_version).exists()
    if not json_exists or not assets_exist:
        return True
    logger.success(f"JSON and assets for {target_version} already exist, skipping build")
    return False


def build_json_for_ref(
    repo: Repo,
    ref_name: str,
    build_dir: Path,
    assets_dir: Path,
    output_dir: Path,
    output_filename: str,
):
    logger.info(f"Generating JSON for Typst Docs ({ref_name})")

    try:
        logger.info(f"Checking out {ref_name}...")
        repo.git.checkout(ref_name, force=True)
    except Exception as e:
        logger.error(f"Failed to checkout {ref_name}: {e}")
        return

    typst_dir = build_dir / "typst"
    json_path = output_dir / output_filename
    
    cmd = [
        "cargo", "run", 
        "--package", "typst-docs", 
        "--color", "always", 
        "--release",
        "--locked",
        "--", 
        "--assets-dir", str(assets_dir.resolve()), 
        "--out-file", str(json_path.resolve())
    ]

    build_env = os.environ.copy()
    if SCCACHE_PATH:
        build_env["RUSTC_WRAPPER"] = SCCACHE_PATH
    
    logger.info(f"Building {ref_name} with system Rust...")
    return_code = run_process_with_progress(cmd, f"Building {ref_name} (System Rust)", cwd=typst_dir, env=build_env)

    if return_code == 0 and json_path.exists():
        logger.success(f"Build successful for {ref_name} (System Rust)")
        return json_path
    
    logger.warning(f"Build failed for {ref_name} with system Rust, trying with pinned Rust...")
    
    required_version = get_pinned_rust_version(typst_dir)
    if not required_version:
        logger.error(f"No pinned Rust version found, skipping build")
        return
    
    toolchain_was_installed = is_toolchain_installed(required_version)
    installed_by_us = False
    
    logger.info(f"Detected required Rust version: {required_version}")
    try:
        if not toolchain_was_installed:
            logger.info(f"Toolchain {required_version} not found. Installing...")
            manage_toolchain(required_version, "install")
            installed_by_us = True
        else:
            logger.info(f"Toolchain {required_version} is already installed. Using it.")

        specific_cmd = list(cmd)
        specific_cmd.insert(1, f"+{required_version}")

        logger.info(f"Attempting build for {ref_name} with pinned Rust...")
        return_code = run_process_with_progress(
            specific_cmd, f"Building {ref_name} (Pinned Rust)", cwd=typst_dir, env=build_env
        )

        if return_code != 0 or not json_path.exists():
            logger.error(f"Build failed for {ref_name} with pinned Rust, skipping generation")
            return
    finally:
        if installed_by_us and required_version != "stable":
            manage_toolchain(required_version, "uninstall")
    
    logger.success(f"Build successful for {ref_name} (Pinned Rust)")
    return json_path

def parse_args():
    parser = argparse.ArgumentParser(description="Typst Docs JSON builder CLI")
    
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR, help="Build artifacts directory")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="JSON output data directory")
    parser.add_argument("--assets-dir", type=Path, default=DEFAULT_ASSETS_DIR, help="Assets output directory")
    parser.add_argument("--force", action="store_true", help="Force rebuild JSON files")
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--target-version", type=str, help="Build JSON for specific version (e.g. v0.12.0)")
    group.add_argument("--all-versions", action="store_true", help=f"Build JSON for all found versions >= {MINIMAL_TYPST_VERSION}")

    return parser.parse_args()

def main():
    args = parse_args()

    ensure_directories([args.build_dir, args.output_dir, args.assets_dir])

    typst_dir = args.build_dir / "typst"
    
    repo = get_typst_repo(typst_dir)
    typst_versions = get_typst_tags(repo)

    json_targets = []

    if args.all_versions:
        json_targets.extend(typst_versions)
    elif args.target_version:
        if args.target_version not in typst_versions:
            logger.error(f"Version {args.target_version} not found")
            exit(1)
        json_targets.append(args.target_version)
    else:
        # Default to latest tag
        ref = typst_versions[-1]
        json_targets.append(ref)

    if not json_targets:
        logger.warning("No versions found to build")
        exit(0)

    filtered = list(filter(lambda version: should_build(version, args.output_dir, args.assets_dir), json_targets))
    if filtered != json_targets:
        logger.info(f"Filtered out {len(json_targets) - len(filtered)} versions: {', '.join(filtered)}")
        json_targets = filtered
    else:
        logger.info("Need to build all versions")
    
    results = []
    for ref in json_targets:
        assets_dir = args.assets_dir / ref
        json_path = build_json_for_ref(
            repo=repo,
            ref_name=ref,
            build_dir=args.build_dir,
            output_filename=f"docs_{ref}.json",
            output_dir=args.output_dir,
            assets_dir=assets_dir
        )
        results.append(json_path)
    
    logger.success(f"Completed {len(results)} JSON builds")
    return results
    

if __name__ == "__main__":
    main()
