# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.


"""
USD Asset Validation Script

This script validates USD files in a specified directory using the Omni Asset Validator.

Features:
- Batch validation of USD files in directories
- Comprehensive error and warning reporting
- CSV output format for validation results
- Automatic output directory creation
- Detailed logging for troubleshooting

Arguments:
    --input_dir      Directory containing input USD files to validate
    --output_dir     Directory to save log files and CSV files

Example:
    /path/to/kit_executable  --enable omni.asset_validator.core --exec "asset_validate.py --input_dir C:/path/to/input --output_dir C:/path/to/output" --/log/file=/path/to/log.log --no-window
"""

import asyncio
import argparse
from pathlib import Path
import os
import sys
from typing import List, Optional, Tuple

import omni.kit.app


async def validate_file(file_name: Path, output_dir: Path) -> bool:
    """Run the validation script for a single file asynchronously.

    Args:
        file_name: Path to the USD file to validate
        output_dir: Directory to save validation results

    Returns:
        bool: True if validation succeeded, False otherwise
    """
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    log_file = output_dir / f"{file_name.stem}.log"
    csv_path = output_dir / f"{file_name.stem}.csv"
    kit_path: str = Path(sys.executable).as_posix()

    asset_validator_id, asset_validator_script = get_asset_validator_id_script()

    # Check if validator is available
    if not asset_validator_id or not asset_validator_script:
        print(f"Error: Asset validator not found")
        return False

    # Build validation command
    command = (
        f"{kit_path} "
        f'--enable "{asset_validator_id}" '
        '--enable "omni.usd_resolver" '
        "--enable omni.kit.pip_archive "
        f"--/log/file={log_file} "
        "--/log/fileLogLevel=verbose "
        "--exec "
        f'"{asset_validator_script} '
        "--no-variants "
        "-f "
        "-c Basic "
        "-c Usd:Performance "
        "-c Usd:Schema "
        "-c Omni:Material "
        "-c Omni:Layout "
        "-c Omni:Basic "
        "-c Omni:Geometry "
        f"--csv-output {csv_path} "
        f'{str(file_name)}"'
    )

    # Execute the validation command
    process = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    # Check validation result
    if process.returncode != 0:
        print(f"Error validating {file_name}: {stderr.decode()}")
        return False
    else:
        print(f"Validated {file_name} result written to {csv_path}")
        return True


def get_asset_validator_id_script() -> Tuple[Optional[str], Optional[str]]:
    """Get the asset validator extension ID and script path.

    Returns:
        Tuple[Optional[str], Optional[str]]: Asset validator ID and script path, or (None, None) if not found
    """
    manager = omni.kit.app.get_app().get_extension_manager()

    # Check if validator is already enabled
    exts = manager.get_extensions()
    validation_core_enabled = False
    for ext in exts:
        if ext["name"] == "omni.asset_validator.core":
            validation_core_enabled = True
            break

    # If not enabled, try to enable it
    if not validation_core_enabled:
        manager.sync_registry()
        exts = manager.get_registry_extensions()
        for ext in exts:
            if ext["name"] == "omni.asset_validator.core":
                manager.set_extension_enabled(ext["id"], True)
                break

    # Get extension versions
    versions = manager.fetch_extension_versions("omni.asset_validator.core")
    if not versions:
        return None, None

    # Get the first available version
    asset_validator_core_ext_path: str = versions[0]["path"]
    asset_validator_id: str = versions[0]["id"]

    # Check if path is empty
    if not asset_validator_core_ext_path:
        print("Unable to find omni.asset_validator.core extension path.")
        return None, None
    else:
        print(
            f"Retrieved omni.asset_validator.core extension path: {asset_validator_core_ext_path}"
        )

    # Build path to validator script
    batch_script = f"{asset_validator_core_ext_path}/scripts/omni_asset_validator.py"
    if not os.path.exists(batch_script):
        return None, None

    return asset_validator_id, batch_script


async def validate_files_in_dir(input_dir: str, output_dir: str) -> None:
    """Validate USD files in a directory recursively.

    Args:
        input_dir: Directory containing input USD files
        output_dir: Directory to save validation results
    """
    # Standard USD file patterns to search for
    input_glob: List[str] = ["*.usdc", "*.usda", "*.usd"]
    input_files: List[Path] = []

    # Collect all USD files matching the patterns
    for pattern in input_glob:
        files = list(Path(input_dir).rglob(pattern))
        input_files.extend(files)

    total_files: int = len(input_files)
    if total_files == 0:
        print(f"No USD files to process in input_dir - {input_dir}")
        return

    # Get asset validator components
    asset_validator_id, asset_validator_script = get_asset_validator_id_script()

    # Validate that validator is available
    if not asset_validator_script or not os.path.exists(asset_validator_script):
        print(f"Validation script does not exist: {asset_validator_script}")
        return

    if asset_validator_id is None:
        print(f"omni.asset_validator.core id cannot be found")
        return

    print(f"Found {total_files} USD files to validate")

    # Create validation tasks for all files
    tasks = []
    for input_file in input_files:
        task = asyncio.create_task(validate_file(input_file, Path(output_dir)))
        tasks.append(task)

    # Run all validation tasks concurrently
    await asyncio.gather(*tasks)

    print("Validation complete")


def main() -> None:
    """Main function to parse arguments and execute USD validation."""
    parser = argparse.ArgumentParser(
        description="Validate USD files in a directory using Omni Asset Validator",
        epilog='Example: /path/to/kit_executable --exec "asset_validate.py --input_dir /path/to/input --output_dir /path/to/output" --/log/file=/path/to/log.log --no-window',
    )
    parser.add_argument(
        "--input_dir", required=True, help="Directory containing input USD files"
    )
    parser.add_argument(
        "--output_dir", required=True, help="Directory to save log files and CSV files"
    )

    args = parser.parse_args()

    # Ensure the output directory exists
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    # Run the validation process
    asyncio.run(validate_files_in_dir(args.input_dir, args.output_dir))

    # Properly shut down the Kit application
    omni.kit.app.get_app().post_quit(0)


if __name__ == "__main__":
    main()
