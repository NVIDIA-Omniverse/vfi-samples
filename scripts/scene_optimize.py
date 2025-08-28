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
Scene Optimizer Batch Processing Script

This module provides functionality to apply Scene Optimizer operations to USD files,
offering batch processing capabilities for directories containing USD files.

Features:
- Process multiple USD files in a directory recursively
- Apply Scene Optimizer presets from JSON configuration files
- Smart preset selection:
  * First looks for a file-specific JSON preset in the same directory as the USD file
    (with the same basename, e.g., model.usd → model.json)
  * Falls back to validation-based presets from so_validation_fixers/ directory
- Smart output path handling for both files and directories
- Preserves directory structure when processing directories recursively

Usage scenarios:
1. Optimize a single USD file with a specified preset
2. Batch process all USD files in a directory with a common preset
3. Apply different presets to different files automatically (by placing matching JSON files alongside USD files)
4. Recursively search directories for specific USD file patterns

Arguments:
    --input_dir         Directory containing USD files to optimize
    --output_dir        Directory to save optimized USD files
    --validation_dir    Directory to find validation results (optional)
    --recursive         Process directories recursively (optional)
    --csv_output        Generate CSV output for results (optional)

Example:
    /path/to/kit_executable --enable omni.scene.optimizer.core --enable omni.usd --exec "scene_optimize.py --input_dir C:/path/to/input --output_dir C:/path/to/output --recursive --csv_output" --/log/file=/path/to/log.log --no-window
"""

import argparse
import csv
import os
from pathlib import Path
from typing import List, Optional

from pxr import UsdUtils

import omni.kit.app
import omni.kit.commands
import omni.scene.optimizer.core
import omni.usd


def get_preset_files(input_file: str, validation_dir: str) -> List[str]:
    """
    Get the preset file for the input file.
    """
    preset_file_root = f"{Path(__file__).parent.as_posix()}/data"
    if not os.path.exists(preset_file_root):
        print(f"Preset file root not found ({preset_file_root})")
        return []

    # Simple data approach to get a preset file based on the validation result
    validation_so_data: dict[str, str] = {
        "WeldChecker": "so_weld.json",
        "ZeroAreaFaceChecker": "so_weld.json",
    }

    # Get validator result file path
    file_name = Path(input_file).stem
    validation_result_file = Path(validation_dir) / f"{file_name}.csv"
    if not validation_result_file.exists():
        print(
            f"Validation result file not found ({validation_result_file}) for {input_file}"
        )
        return []

    # Parse the validation result file
    preset_files: List[str] = []
    with open(validation_result_file, "r", newline="") as csv_file:
        csv_reader = csv.reader(csv_file)

        # Skip the header row
        next(csv_reader)

        for row in csv_reader:
            rule_name = row[1]
            if rule_name in validation_so_data:
                preset_file = f"{preset_file_root}/{validation_so_data[rule_name]}"
                if preset_file not in preset_files and os.path.exists(preset_file):
                    preset_files.append(preset_file)

    return preset_files


def apply_so_preset_to_stages(
    input_dir: str, output_dir: str, validation_dir: str
) -> None:
    input_glob: List[str] = ["*.usdc", "*.usda", "*.usd"]
    input_files: List[Path] = []
    output_files: List[str] = []

    for pattern in input_glob:
        files = list(Path(input_dir).rglob(pattern))
        input_files.extend(files)

    # Generate output paths
    for input_file in input_files:
        output_file = input_file.as_posix().replace(input_dir, output_dir)
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        output_files.append(output_file)

    print(f"Found {len(input_files)} files to process")
    print(f"Found {len(output_files)} output files to process")

    # Process each file
    for input_file, output_file in zip(input_files, output_files):
        input_file = input_file.as_posix()
        # Check for file-specific preset - this is a nice way to drop stage specific presets and automatically apply them.
        target_stage_preset: str = Path(
            Path(input_file).parent, Path(input_file).stem + ".json"
        ).as_posix()
        preset_files: List[str] = []

        if os.path.exists(target_stage_preset):
            preset_files.append(target_stage_preset)
        else:
            # Get preset based on validation data
            preset_files = get_preset_files(input_file, validation_dir)

        if not preset_files:
            print(
                f"No preset based on validation data found for {input_file} - skipping"
            )
            continue

        if not omni.usd.get_context().open_stage(input_file):
            raise ValueError(f"Could not open file {input_file}")

        context = omni.usd.get_context()
        stage = context.get_stage()

        optimizer_context = omni.scene.optimizer.core.ExecutionContext()
        optimizer_context.usdStageId = (
            UsdUtils.StageCache().Get().Insert(stage).ToLongInt()
        )
        optimizer_context.generateReport = 1
        optimizer_context.captureStats = 1

        for preset_file in preset_files:
            print(
                f"Applying preset - {preset_file} - to - {input_file} - Saving to - {output_file}"
            )
            myArgs = {"jsonFile": str(preset_file)}
            omni.kit.commands.execute(
                "SceneOptimizerJsonParser", context=optimizer_context, args=myArgs
            )

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Export stage to a new file
        stage.GetRootLayer().Export(output_file)

        # Close each stage to avoid kit crashes
        omni.usd.get_context().close_stage()


def get_scene_optimizer_id() -> Optional[str]:
    manager = omni.kit.app.get_app().get_extension_manager()
    return manager.get_enabled_extension_id("omni.scene.optimizer.core")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate USD files in a directory. Automatically skips geometry validation for files with no native geometry. This also skips files that have a log or csv file already.",
        epilog='Example: /path/to/kit_executable --enable omni.scene.optimizer.core --enable omni.usd --exec "scene_optimize.py --input_dir /path/to/input --output_dir /path/to/output --recursive --csv_output" --/log/file=/path/to/log.log --no-window',
    )
    parser.add_argument("--input_dir", help="Directory containing files to optimize")
    parser.add_argument("--output_dir", help="Directory to save scene optimized files")
    parser.add_argument("--validation_dir", help="Directory to find validation results")

    args = parser.parse_args()

    scene_optimizer_id = get_scene_optimizer_id()
    print(f"Scene Optimizer ID: {scene_optimizer_id}")
    apply_so_preset_to_stages(args.input_dir, args.output_dir, args.validation_dir)

    # Properly shut down the Kit application
    omni.kit.app.get_app().post_quit(0)
