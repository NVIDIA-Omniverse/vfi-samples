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
Material Assignment Script for USD Files

This module provides functionality to assign materials to meshes in USD files
using Kit commands, which is the recommended approach for Omniverse.

Features:
- Process USD files in a directory and assign materials to meshes
- Use configurable dictionary mapping stage names to MDL material file paths
- Apply materials using Kit commands for proper Omniverse integration
- Skip files that don't have a material mapping
- Batch processing of multiple USD files with proper cleanup
- Retry logic for handling transient failures

Arguments:
    --input_dir         Directory containing USD files to process
    --material_folder   Directory containing MDL material files

Example:
    /path/to/kit_executable --enable omni.usd --enable omni.mdl.usd_converter --exec "assign_materials.py --input_dir C:/path/to/wheel_parts_folder --material_folder C:/path/to/materials" --/log/file=/path/to/log.log --no-window
"""

import argparse
import os
import time
from pathlib import Path
from typing import Dict, List

from pxr import Sdf, Usd, UsdGeom, UsdShade

import omni
import omni.kit.app
import omni.kit.commands
import omni.mdl.usd_converter
import omni.usd

# Material mapping dictionary - customize this based on your needs
# Format: {stage_name: mdl_filename} - paths will be constructed using material_folder argument
MATERIAL_MAPPING: Dict[str, str] = {
    # Wheel component mappings - just the MDL filenames, folder will be passed as argument
    "Tire": "Tire.mdl",
    "Rim": "Steel_Carbon.mdl",
    "Caliper": "Caliper.mdl",
    "Brake_Disk": "Disk_Brake.mdl",
    "Bolt": "Chromium.mdl",
    # Add more mappings as needed
}


def get_mesh_prims(stage: Usd.Stage) -> List[Usd.Prim]:
    """
    Get all mesh primitives from a USD stage that are suitable for material assignment.

    Args:
        stage: USD stage to search for mesh primitives

    Returns:
        List of mesh primitives that can have materials assigned
    """
    # Filter mesh prims: exclude instances, references, and payloads to avoid conflicts
    mesh_prims = []
    for prim in stage.Traverse():
        if (
            prim.IsA(UsdGeom.Mesh)
            and not prim.IsInstance()
            and not prim.HasAuthoredReferences()
            and not prim.HasAuthoredPayloads()
        ):
            mesh_prims.append(prim)

    return mesh_prims


def create_material_if_needed(mdl_path: str, material_path: str) -> None:
    """
    Create a material primitive if it doesn't already exist.

    Args:
        mdl_path: Path to the MDL material file
        material_path: USD path where the material should be created
    """
    target_material_prim = omni.usd.get_prim_at_path(Sdf.Path(material_path))
    if not target_material_prim.IsValid():
        material_name = Path(mdl_path).stem
        omni.kit.commands.execute(
            "CreateMdlMaterialPrim",
            mtl_url=mdl_path,
            mtl_name=material_name,
            mtl_path=material_path,
        )


def assign_material_to_meshes(mesh_prims: List[Usd.Prim], material_path: str) -> None:
    """
    Assign a material to all provided mesh primitives.

    Args:
        mesh_prims: List of mesh primitives to assign material to
        material_path: USD path to the material to assign
    """
    target_material_prim = omni.usd.get_prim_at_path(Sdf.Path(material_path))
    if not target_material_prim.IsValid():
        print(f"Warning: Material prim not found at {material_path}")
        return

    target_material = UsdShade.Material(target_material_prim)

    # Bind material to each mesh primitive
    for mesh_prim in mesh_prims:
        UsdShade.MaterialBindingAPI(mesh_prim).Bind(target_material)


def cleanup_unused_materials(stage: Usd.Stage) -> None:
    """
    Remove unused materials from the stage to keep it clean.

    Args:
        stage: USD stage to clean up
    """
    # Collect all material primitives in the stage
    all_materials = [prim for prim in stage.Traverse() if UsdShade.Material(prim)]

    # Remove materials that are not bound to any primitive
    for material_prim in all_materials:
        if not omni.mdl.usd_converter.is_material_bound_to_prim(stage, material_prim):
            stage.RemovePrim(Sdf.Path(material_prim.GetPath().pathString))


def process_usd_file(usd_file: Path, input_dir: Path, material_folder: Path) -> bool:
    """
    Process a single USD file and assign materials to its meshes.

    Args:
        usd_file: Path to the USD file to process
        input_dir: Base input directory (not used for material paths anymore)
        material_folder: Directory containing MDL material files

    Returns:
        True if processing was successful, False otherwise
    """
    print(f"\nProcessing: {usd_file}")

    try:
        # Close any existing stage to avoid conflicts
        current_stage = omni.usd.get_context().get_stage()
        if current_stage:
            omni.usd.get_context().close_stage()
            time.sleep(1.0)  # Give more time for cleanup

        # Open the stage with retry logic
        max_retries = 3
        stage_opened = False
        for attempt in range(max_retries):
            try:
                if omni.usd.get_context().open_stage(str(usd_file)):
                    stage_opened = True
                    break
                else:
                    if attempt < max_retries - 1:
                        time.sleep(1.0)  # Wait before retry
                    else:
                        print(
                            f"Failed to open stage after {max_retries} attempts: {usd_file}"
                        )
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1.0)  # Wait before retry
                else:
                    print(f"Error opening stage: {e}")

        if not stage_opened:
            return False

        stage = omni.usd.get_context().get_stage()
        if not stage:
            print(f"Failed to get stage for: {usd_file}")
            omni.usd.get_context().close_stage()
            time.sleep(0.5)
            return False

        # Check if stage has a material mapping configured
        stage_name = usd_file.stem
        if stage_name not in MATERIAL_MAPPING:
            print(f"No material mapping found for stage '{stage_name}' - skipping")
            return False

        # Find all mesh primitives that can receive materials
        mesh_prims = get_mesh_prims(stage)
        if not mesh_prims:
            print(f"No mesh primitives found in {usd_file}")
            return False

        # Build paths for material creation and assignment
        material_filename = MATERIAL_MAPPING[stage_name]
        mdl_path = str(material_folder / material_filename)
        material_name = Path(mdl_path).stem
        material_path = f"/{stage.GetRootLayer().defaultPrim}/Looks/{material_name}"

        print(f"Stage '{stage_name}' will use material: {material_name}")

        # Create material if it doesn't exist
        create_material_if_needed(mdl_path, material_path)

        # Assign material to all mesh primitives
        assign_material_to_meshes(mesh_prims, material_path)

        # Clean up unused materials
        cleanup_unused_materials(stage)

        # Save the modified stage
        stage.GetRootLayer().Save()

        # Close the stage with retry logic
        max_close_retries = 3
        for close_attempt in range(max_close_retries):
            try:
                omni.usd.get_context().close_stage()
                time.sleep(0.5)  # Give time for the stage to close
                break
            except Exception as e:
                if close_attempt < max_close_retries - 1:
                    time.sleep(1.0)  # Wait before retry

        # Give extra time for the stage to close before processing next file
        time.sleep(1.0)

        return True

    except Exception as e:
        print(f"Error processing {usd_file}: {e}")
        # Make sure to close the stage even if there's an error
        try:
            current_stage = omni.usd.get_context().get_stage()
            if current_stage:
                omni.usd.get_context().close_stage()
                time.sleep(1.0)  # Give time for cleanup
        except Exception:
            pass
        return False


def process_directory(input_dir: str, material_folder: str) -> None:
    """
    Process all USD files in a directory and assign materials to their meshes.

    Args:
        input_dir: Directory containing USD files to process
        material_folder: Directory containing MDL material files
    """
    input_path = Path(input_dir)

    # Validate that input directory exists
    if not input_path.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    # Recursively find all USD files in the directory
    usd_extensions = ["*.usd", "*.usda", "*.usdc"]
    usd_files = []

    for ext in usd_extensions:
        usd_files.extend(input_path.rglob(ext))

    if not usd_files:
        print(f"No USD files found in: {input_dir}")
        return

    print(f"Found {len(usd_files)} USD files to process")

    # Process each USD file and track successful assignments
    success_count = 0
    material_path = Path(material_folder)
    for usd_file in usd_files:
        if process_usd_file(usd_file, input_path, material_path):
            success_count += 1

    print(f"\nCompleted: {success_count}/{len(usd_files)} files processed successfully")


def main() -> None:
    """Main function to handle command line arguments and execute material assignment."""
    parser = argparse.ArgumentParser(
        description="Assign materials to meshes in USD files using Kit commands",
        epilog='Example: /path/to/kit_executable --enable omni.usd --enable omni.mdl.usd_converter --exec "assign_materials.py --input_dir /path/to/wheel_parts_folder --material_folder /path/to/materials" --/log/file=/path/to/log.log --no-window',
    )
    parser.add_argument(
        "--input_dir",
        required=True,
        help="Directory containing USD files to assign materials to",
    )
    parser.add_argument(
        "--material_folder",
        required=True,
        help="Directory containing MDL material files",
    )

    args = parser.parse_args()

    # Validate input directory
    if not os.path.exists(args.input_dir):
        print(f"Error: Input directory does not exist: {args.input_dir}")
        return

    # Validate material folder
    if not os.path.exists(args.material_folder):
        print(f"Error: Material folder does not exist: {args.material_folder}")
        return

    print(f"Processing directory: {args.input_dir}")
    print(f"Material folder: {args.material_folder}")

    try:
        process_directory(args.input_dir, args.material_folder)
    except Exception as e:
        print(f"Error during processing: {e}")
    finally:
        # Cleanup: ensure any open stages are closed
        try:
            current_stage = omni.usd.get_context().get_stage()
            if current_stage:
                omni.usd.get_context().close_stage()
                time.sleep(2.0)  # Give extra time for final cleanup
        except Exception:
            pass


if __name__ == "__main__":
    main()

    # Properly shut down the Kit application
    omni.kit.app.get_app().post_quit(0)
