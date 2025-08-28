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
Component Aggregation Script for USD Files

This module provides functionality to create a new USD stage that payloads all USD files
from a wheel_parts_folder and positions the components appropriately.

Features:
- Create a new USD stage with payloads to all component USD files
- Position components in their correct locations using predefined configurations
- Support for different component positioning strategies
- Batch processing of multiple USD files
- Special handling for bolt duplication (creates 4 additional bolt instances)

Arguments:
    --input_dir      Directory containing USD files to aggregate
    --output_file    Path to the output USD file

Example:
    /path/to/kit_executable --enable omni.usd --exec "aggregate_components.py --input_dir C:/path/to/wheel_parts_folder --output_file C:/path/to/output.usd" --/log/file=/path/to/log.log --no-window
"""

import argparse
import math
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from pxr import Gf, Kind, Sdf, Usd, UsdGeom

import omni.kit.app

# Component positioning configuration
# Format: {component_name: (x, y, z, rot_x, rot_y, rot_z)}
COMPONENT_POSITIONS: Dict[str, Tuple[float, float, float, float, float, float]] = {
    "Tire": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),  # Center position, no rotation
    "Rim": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),  # Same as tire (they overlap)
    "Caliper": (14.0, 0.0, 0.0, 0.0, 0.0, 0.0),  # Brake caliper position
    "Brake_Disk": (14.0, 0.0, 0.0, 0.0, 0.0, 0.0),  # Brake disk position
    "Bolt": (17.7, 5.6, 0.0, 0.0, 0.0, 0.0),  # Bolt positions (may need multiple)
    "Bolt_01": (17.7, 1.75, -5.33, 72.0, 0.0, 0.0),
    "Bolt_02": (17.7, -4.54, -3.28, 144.0, 0.0, 0.0),
    "Bolt_03": (17.7, -4.52, 3.28, 216.0, 0.0, 0.0),
    "Bolt_04": (17.7, 1.75, 5.33, 288.0, 0.0, 0.0),
    # Add more component positions as needed
}


def ensure_kind(
    prim: Usd.Prim,
    kind: Union[
        Kind.Tokens.assembly,
        Kind.Tokens.component,
        Kind.Tokens.group,
        Kind.Tokens.subcomponent,
    ],
) -> None:
    """Set the Kind metadata on a USD primitive."""
    Usd.ModelAPI(prim).SetKind(kind)


def create_transform_matrix(
    x: float, y: float, z: float, rot_x: float, rot_y: float, rot_z: float
) -> Gf.Matrix4d:
    """
    Create a 4x4 transformation matrix from translation and rotation parameters.

    Args:
        x, y, z: Translation values
        rot_x, rot_y, rot_z: Rotation values in degrees

    Returns:
        4x4 transformation matrix
    """
    # Create translation matrix
    translation = Gf.Matrix4d().SetTranslate(Gf.Vec3d(x, y, z))

    # Create rotation matrices (convert degrees to radians)
    rot_x_rad = math.radians(rot_x)
    rot_y_rad = math.radians(rot_y)
    rot_z_rad = math.radians(rot_z)

    # Create rotation matrices around each axis
    rot_x_matrix = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), rot_x_rad))
    rot_y_matrix = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 1, 0), rot_y_rad))
    rot_z_matrix = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 0, 1), rot_z_rad))

    # Combine transformations: translation * rotation_z * rotation_y * rotation_x
    transform_matrix = translation * rot_z_matrix * rot_y_matrix * rot_x_matrix

    return transform_matrix


def create_stage(
    stage_path: str,
    sub_layer_files: Optional[List[str]] = None,
    payload_files: Optional[List[Path]] = None,
) -> None:
    """
    Create a USD stage with sublayers and/or payloads.

    Args:
        stage_path: Path where the stage will be saved
        sub_layer_files: Optional list of sublayer file paths
        payload_files: Optional list of payload file paths
    """
    base_name = Path(stage_path).name
    stage = Usd.Stage.CreateInMemory(f"{base_name}")

    # Set up axis
    stage.SetMetadata("upAxis", "Y")
    print(f"Set stage up axis to: Y")

    # Set linear units
    stage.SetMetadata("metersPerUnit", 0.01)
    print(f"Set stage linear units to: cm")

    default_prim: Usd.Prim = UsdGeom.Xform.Define(stage, Sdf.Path("/World")).GetPrim()
    ensure_kind(default_prim, Kind.Tokens.component)
    stage.SetDefaultPrim(default_prim)

    if sub_layer_files:
        for sub_layer_file in sub_layer_files:
            stage.GetRootLayer().subLayerPaths.append(sub_layer_file)

    if payload_files:
        for payload_file in payload_files:
            name = Path(payload_file).stem
            payload_prim: Usd.Prim = UsdGeom.Xform.Define(
                stage, Sdf.Path(f"/World/{name}")
            ).GetPrim()
            relative_path = (
                f"./{payload_file.relative_to(Path(stage_path).parent).as_posix()}"
            )
            payload_prim.GetPayloads().AddPayload(assetPath=relative_path)

            # Set payload prim kind to subcomponent
            ensure_kind(payload_prim, Kind.Tokens.subcomponent)

            # Create Xformable for positioning
            xformable = UsdGeom.Xformable(payload_prim)

            # Apply positioning if component has configuration
            if name in COMPONENT_POSITIONS:
                x, y, z, rot_x, rot_y, rot_z = COMPONENT_POSITIONS[name]
                transform_matrix = create_transform_matrix(x, y, z, rot_x, rot_y, rot_z)
                xformable.AddTransformOp().Set(transform_matrix)
                print(
                    f"Positioned {name} at ({x}, {y}, {z}) with rotation ({rot_x}, {rot_y}, {rot_z})"
                )

            # Handle special case for Bolt - create 4 additional bolt instances
            if name == "Bolt":
                for i in range(4):
                    bolt_name = f"{name}_0{i+1}"
                    bolt_prim: Usd.Prim = UsdGeom.Xform.Define(
                        stage, Sdf.Path(f"/World/{bolt_name}")
                    ).GetPrim()
                    bolt_prim.GetPayloads().AddPayload(assetPath=relative_path)
                    ensure_kind(bolt_prim, Kind.Tokens.subcomponent)

                    bolt_xformable = UsdGeom.Xformable(bolt_prim)
                    if bolt_name in COMPONENT_POSITIONS:
                        x, y, z, rot_x, rot_y, rot_z = COMPONENT_POSITIONS[bolt_name]
                        transform_matrix = create_transform_matrix(
                            x, y, z, rot_x, rot_y, rot_z
                        )
                        bolt_xformable.AddTransformOp().Set(transform_matrix)
                        print(
                            f"Positioned {bolt_name} at ({x}, {y}, {z}) with rotation ({rot_x}, {rot_y}, {rot_z})"
                        )

    stage.GetRootLayer().Export(f"{stage_path}")


def aggregate_components(input_dir: str, output_file: str) -> bool:
    """
    Create a new stage with payloads to all USD files and position components.

    Args:
        input_dir: Directory containing USD files to aggregate
        output_file: Path to the output USD file

    Returns:
        True if successful, False otherwise
    """
    try:
        # Find all USD files in input directory
        input_glob = ["*.usdc", "*.usda", "*.usd"]
        usd_files: List[Path] = []
        for pattern in input_glob:
            files = list(Path(input_dir).rglob(pattern))
            usd_files.extend(files)

        if not usd_files:
            print(f"No USD files found in: {input_dir}")
            return False

        print(f"Found {len(usd_files)} USD files to aggregate")

        # Create new stage with payloads
        create_stage(stage_path=output_file, payload_files=usd_files)

        return True

    except Exception as e:
        print(f"Error during aggregation: {e}")
        return False


def main() -> None:
    """Main function to handle command line arguments and execute component aggregation."""
    parser = argparse.ArgumentParser(
        description="Create a new USD stage with payloads to all component USD files",
        epilog='Example: /path/to/kit_executable --enable omni.usd --exec "aggregate_components.py --input_dir /path/to/wheel_parts_folder --output_file /path/to/output.usd" --/log/file=/path/to/log.log --no-window',
    )
    parser.add_argument(
        "--input_dir", required=True, help="Directory containing USD files to aggregate"
    )
    parser.add_argument(
        "--output_file", required=True, help="Path to the output USD file"
    )

    args = parser.parse_args()

    # Validate input directory
    if not os.path.exists(args.input_dir):
        print(f"Error: Input directory does not exist: {args.input_dir}")
        return

    # Ensure output directory exists
    output_dir = os.path.dirname(args.output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    print(f"Input directory: {args.input_dir}")
    print(f"Output file: {args.output_file}")

    try:
        aggregate_components(args.input_dir, args.output_file)

    except Exception as e:
        print(f"Error during processing: {e}")


if __name__ == "__main__":
    main()

    # Properly shut down the Kit application
    omni.kit.app.get_app().post_quit(0)
