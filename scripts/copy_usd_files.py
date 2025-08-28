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
Copy USD Files Utility Script

This utility copies USD files from a source directory to a target directory.
It's a simple file system operation script that doesn't require Kit or Omniverse.

Features:
- Copy USD files between directories
- Automatic target directory creation
- Simple command-line interface

Arguments:
    --source_directory    Source directory containing USD files
    --target_directory    Target directory to copy files to

Example:
    /path/to/kit_executable --exec "copy_usd_files.py --source_directory C:/input --target_directory C:/output" --no-window
"""

import argparse
from pathlib import Path
import shutil
from typing import List

import omni.kit.app


def copy_source_to_target(source_directory: str, target_directory: str) -> None:
    """Copies the USD files in the source directory to the target directory.

    Args:
        source_directory: Source directory to copy USD files from
        target_directory: Directory to copy USD files to
    """
    # Find all USD files in the source directory recursively
    usd_files: List[Path] = list(Path(source_directory).rglob("*.usd"))

    # Copy each USD file to the target directory
    for usd_file in usd_files:
        # Replace source directory path with target directory path
        output_file: str = usd_file.as_posix().replace(
            source_directory, target_directory
        )
        input_file: str = usd_file.as_posix()

        # Copy the file
        shutil.copy(input_file, output_file)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy USD files from source directory to target directory",
        epilog='Example: /path/to/kit_executable --exec "copy_usd_files.py --source_directory C:/input --target_directory C:/output" --no-window',
    )
    parser.add_argument(
        "--source_directory", required=True, help="Source directory to copy from"
    )
    parser.add_argument(
        "--target_directory", required=True, help="Target directory to copy to"
    )
    args = parser.parse_args()
    copy_source_to_target(args.source_directory, args.target_directory)


if __name__ == "__main__":
    main()

    # Properly shut down the Kit application
    omni.kit.app.get_app().post_quit(0)
