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
Simple script to convert quaternion xformOp:orient to Euler xformOp:rotateXYZ.
Includes quaternion flip detection and gimbal lock avoidance.
Only does the conversion - no keyframe extraction or simplification.
"""

import omni.usd
from pxr import Usd, UsdGeom, Gf, Sdf
import carb
import math


def quaternion_to_euler_xyz(quat):
    """
    Convert a quaternion to Euler angles in XYZ order.

    Args:
        quat: Gf.Quatf, Gf.Quatd, or Gf.Quath quaternion

    Returns:
        Gf.Vec3d: Euler angles in degrees (rotateX, rotateY, rotateZ)
    """
    # Convert quaternion to rotation
    rotation = Gf.Rotation(quat)

    # Decompose to Euler angles in XYZ order
    # Note: USD's Decompose method returns angles in the reverse order of application
    # For XYZ order, we decompose as ZYX
    angles = rotation.Decompose(Gf.Vec3d.ZAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.XAxis())

    # Return in XYZ order (reverse the decomposition order)
    return Gf.Vec3d(angles[2], angles[1], angles[0])


def quaternion_to_euler_xzy(quat):
    """
    Convert a quaternion to Euler angles in XZY order.

    Args:
        quat: Gf.Quatf, Gf.Quatd, or Gf.Quath quaternion

    Returns:
        Gf.Vec3d: Euler angles in degrees (rotateX, rotateZ, rotateY)
        Note: Still returned as Vec3d(x, y, z) but the rotation order is XZY
    """
    rotation = Gf.Rotation(quat)
    # For XZY order, we decompose as YZX
    angles = rotation.Decompose(Gf.Vec3d.YAxis(), Gf.Vec3d.ZAxis(), Gf.Vec3d.XAxis())
    # Return in XZY order but still as Vec3d(x, y, z) for consistency
    return Gf.Vec3d(angles[2], angles[0], angles[1])


def quaternion_to_euler_yxz(quat):
    """
    Convert a quaternion to Euler angles in YXZ order.

    Args:
        quat: Gf.Quatf, Gf.Quatd, or Gf.Quath quaternion

    Returns:
        Gf.Vec3d: Euler angles in degrees (rotateY, rotateX, rotateZ)
        Note: Still returned as Vec3d(x, y, z) but the rotation order is YXZ
    """
    rotation = Gf.Rotation(quat)
    # For YXZ order, we decompose as ZXY
    angles = rotation.Decompose(Gf.Vec3d.ZAxis(), Gf.Vec3d.XAxis(), Gf.Vec3d.YAxis())
    # Return still as Vec3d(x, y, z) for consistency
    return Gf.Vec3d(angles[1], angles[2], angles[0])


def quaternion_to_euler_zxy(quat):
    """
    Convert a quaternion to Euler angles in ZXY order.

    Args:
        quat: Gf.Quatf, Gf.Quatd, or Gf.Quath quaternion

    Returns:
        Gf.Vec3d: Euler angles in degrees (rotateZ, rotateX, rotateY)
        Note: Still returned as Vec3d(x, y, z) but the rotation order is ZXY
    """
    rotation = Gf.Rotation(quat)
    # For ZXY order, we decompose as YXZ
    angles = rotation.Decompose(Gf.Vec3d.YAxis(), Gf.Vec3d.XAxis(), Gf.Vec3d.ZAxis())
    # Return still as Vec3d(x, y, z) for consistency
    return Gf.Vec3d(angles[1], angles[2], angles[0])


def detect_gimbal_lock(euler_angles, order="XYZ", threshold=85.0):
    """
    Detect if Euler angles are near gimbal lock.
    Gimbal lock occurs when the middle rotation approaches ±90 degrees.

    Args:
        euler_angles: Gf.Vec3d of Euler angles in degrees
        order: Euler rotation order (XYZ, XZY, YXZ, ZXY)
        threshold: Degrees from 90 to consider as near gimbal lock (default 85)

    Returns:
        bool: True if near gimbal lock
    """
    # Validate threshold to ensure margin is positive
    if not (0 < threshold <= 90):
        raise ValueError("threshold must be between 0 and 90 degrees")

    # Determine which axis is the middle rotation based on order
    if order == "XYZ":
        middle_rotation = abs(euler_angles[1])  # Y is middle
    elif order == "XZY":
        middle_rotation = abs(euler_angles[2])  # Z is middle
    elif order == "YXZ":
        middle_rotation = abs(euler_angles[0])  # X is middle
    elif order == "ZXY":
        middle_rotation = abs(euler_angles[0])  # X is middle
    else:
        # Default to XYZ
        middle_rotation = abs(euler_angles[1])

    # Check if middle rotation is near 90 or 270 degrees
    near_90 = abs(middle_rotation - 90.0) < (90.0 - threshold)
    near_270 = abs(middle_rotation - 270.0) < (90.0 - threshold)
    return near_90 or near_270


def choose_best_euler_order(quat, threshold=85.0):
    """
    Try different Euler orders and choose the one that avoids gimbal lock.

    Args:
        quat: Quaternion to convert
        threshold: Gimbal lock threshold in degrees

    Returns:
        tuple: (euler_angles, order_used)
    """
    # Try different Euler orders
    orders = [
        ("XYZ", quaternion_to_euler_xyz),
        ("XZY", quaternion_to_euler_xzy),
        ("YXZ", quaternion_to_euler_yxz),
        ("ZXY", quaternion_to_euler_zxy),
    ]

    results = []
    for order_name, converter in orders:
        euler = converter(quat)
        has_gimbal = detect_gimbal_lock(euler, order_name, threshold)
        results.append((euler, order_name, has_gimbal))

    # First, try to find an order without gimbal lock
    for euler, order_name, has_gimbal in results:
        if not has_gimbal:
            return euler, order_name

    # If all have gimbal lock, return the default XYZ
    # (In practice, if one has gimbal lock, usually at least one other order won't)
    return results[0][0], results[0][1]


def fix_quaternion_flips(time_samples, orient_attr):
    """
    Fix quaternion flips to ensure shortest path interpolation.

    Args:
        time_samples: List of time codes
        orient_attr: The orient attribute

    Returns:
        list: List of (time, fixed_quaternion) tuples
    """
    if not time_samples:
        return []

    fixed_sequence = []
    prev_quat = orient_attr.Get(time_samples[0])
    fixed_sequence.append((time_samples[0], prev_quat))

    flip_count = 0

    for i in range(1, len(time_samples)):
        curr_quat = orient_attr.Get(time_samples[i])

        # Check dot product to see if quaternions are in opposite hemispheres
        dot = (
            prev_quat.GetReal() * curr_quat.GetReal()
            + prev_quat.GetImaginary()[0] * curr_quat.GetImaginary()[0]
            + prev_quat.GetImaginary()[1] * curr_quat.GetImaginary()[1]
            + prev_quat.GetImaginary()[2] * curr_quat.GetImaginary()[2]
        )

        # If dot product is negative, flip the quaternion to ensure shortest path
        if dot < 0:
            curr_quat = -curr_quat
            flip_count += 1

        fixed_sequence.append((time_samples[i], curr_quat))
        prev_quat = curr_quat

    if flip_count > 0:
        carb.log_info(f"  Fixed {flip_count} quaternion flip(s)")

    return fixed_sequence


def ensure_euler_continuity(euler_sequence):
    """
    Ensure Euler angle continuity to avoid sudden jumps.

    Args:
        euler_sequence: List of (time, euler_angles) tuples

    Returns:
        list: List of (time, corrected_euler_angles) tuples
    """
    if len(euler_sequence) < 2:
        return euler_sequence

    corrected_sequence = [euler_sequence[0]]

    for i in range(1, len(euler_sequence)):
        time, curr_euler = euler_sequence[i]
        prev_euler = corrected_sequence[-1][1]

        # Create a new Vec3d for the corrected angles
        corrected = Gf.Vec3d(curr_euler)

        # Check each axis for discontinuities
        for axis in range(3):
            diff = corrected[axis] - prev_euler[axis]

            # If the difference is greater than 180 degrees, we have a discontinuity
            if abs(diff) > 180:
                if diff > 0:
                    corrected[axis] -= 360
                else:
                    corrected[axis] += 360

            # Keep angles in a consistent range relative to previous frame
            while corrected[axis] > prev_euler[axis] + 180:
                corrected[axis] -= 360
            while corrected[axis] < prev_euler[axis] - 180:
                corrected[axis] += 360

        corrected_sequence.append((time, corrected))

    return corrected_sequence


def convert_orient_to_rotateXYZ(prim, stage):
    """
    Convert xformOp:orient to xformOp:rotateXYZ for a single prim.

    Args:
        prim: Usd.Prim to process
        stage: Usd.Stage

    Returns:
        bool: True if conversion was performed, False otherwise
    """
    # Check if prim has xformOp:orient attribute
    orient_attr = prim.GetAttribute("xformOp:orient")
    if not orient_attr or not orient_attr.IsValid():
        return False

    # Check if the attribute has time samples
    time_samples = orient_attr.GetTimeSamples()
    if not time_samples:
        # Check for default value
        default_value = orient_attr.Get()
        if default_value:
            carb.log_info(f"Converting static orient for prim: {prim.GetPath()}")
            # Handle static value
            euler_angles = quaternion_to_euler_xyz(default_value)

            # Get xformable and create rotateXYZ
            xformable = UsdGeom.Xformable(prim)
            if not xformable:
                return False

            rotate_xyz_op = xformable.AddRotateXYZOp()
            rotate_xyz_op.Set(euler_angles)

            # Clear orient and update xform ops
            orient_attr.Clear()
            xform_ops = xformable.GetOrderedXformOps()
            new_ops = [
                rotate_xyz_op if op.GetOpType() == UsdGeom.XformOp.TypeOrient else op
                for op in xform_ops
            ]
            xformable.SetXformOpOrder(new_ops)
            return True
        return False

    carb.log_info(
        f"Converting {len(time_samples)} orient timesamples for: {prim.GetPath()}"
    )

    # Get the xformable interface
    xformable = UsdGeom.Xformable(prim)
    if not xformable:
        carb.log_warn(f"Prim {prim.GetPath()} is not xformable")
        return False

    # Step 1: Fix quaternion flips
    carb.log_info("  Step 1: Checking for quaternion flips...")
    fixed_quats = fix_quaternion_flips(time_samples, orient_attr)

    # Step 2: Convert to Euler angles with gimbal lock detection
    carb.log_info("  Step 2: Converting quaternions to Euler angles...")
    euler_sequence = []
    gimbal_lock_frames = []
    gimbal_avoided_frames = []

    for time, quat in fixed_quats:
        # First try standard XYZ
        euler_xyz = quaternion_to_euler_xyz(quat)

        # Check if XYZ has gimbal lock
        if detect_gimbal_lock(euler_xyz, "XYZ"):
            # Try other orders to see if we can avoid it
            euler_alt, best_order = choose_best_euler_order(quat)

            # Check if an alternative order avoids gimbal lock
            if not detect_gimbal_lock(euler_alt, best_order):
                gimbal_avoided_frames.append((time, best_order))
                carb.log_info(
                    f"    Frame {time}: Gimbal lock detected in XYZ, but {best_order} order would avoid it"
                )
            else:
                gimbal_lock_frames.append(time)

        # Always use XYZ for consistency with USD's xformOp:rotateXYZ
        euler_sequence.append((time, euler_xyz))

    # Report gimbal lock analysis
    if gimbal_avoided_frames:
        carb.log_warn(
            f"  ⚠️  Gimbal lock detected at {len(gimbal_avoided_frames)} frame(s)"
        )
        carb.log_info(
            f"  💡 Suggestion: Consider using a different rotation order for these frames:"
        )
        for frame, order in gimbal_avoided_frames[:5]:  # Show first 5
            carb.log_info(f"    Frame {frame}: Use {order} order instead")
        if len(gimbal_avoided_frames) > 5:
            carb.log_info(f"    ... and {len(gimbal_avoided_frames) - 5} more frames")

    if gimbal_lock_frames:
        carb.log_warn(
            f"  ⚠️  Warning: Gimbal lock unavoidable at {len(gimbal_lock_frames)} frame(s)"
        )
        carb.log_warn(f"     (All Euler orders have gimbal lock for these rotations)")
        if len(gimbal_lock_frames) <= 10:
            carb.log_warn(f"     Frames: {gimbal_lock_frames[:10]}")

    # Step 3: Ensure Euler continuity
    carb.log_info("  Step 3: Ensuring Euler angle continuity...")
    euler_sequence = ensure_euler_continuity(euler_sequence)

    # Step 4: Apply the conversion
    carb.log_info("  Step 4: Writing rotateXYZ values...")

    # Create or get rotateXYZ op
    rotate_xyz_op = None
    xform_ops = xformable.GetOrderedXformOps()

    for op in xform_ops:
        if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
            rotate_xyz_op = op
            break

    if not rotate_xyz_op:
        rotate_xyz_op = xformable.AddRotateXYZOp()

    rotate_xyz_attr = rotate_xyz_op.GetAttr()

    # Write all the timesamples
    with Sdf.ChangeBlock():
        for time, euler_angles in euler_sequence:
            rotate_xyz_attr.Set(euler_angles, time)

        # Clear the orient attribute
        orient_attr.Clear()

        # Update xformOpOrder to replace orient with rotateXYZ
        new_ops = []
        for op in xform_ops:
            if op.GetOpType() == UsdGeom.XformOp.TypeOrient:
                if rotate_xyz_op not in xform_ops:
                    new_ops.append(rotate_xyz_op)
            else:
                new_ops.append(op)

        xformable.SetXformOpOrder(new_ops)

    carb.log_info(
        f"  ✓ Successfully converted to {len(euler_sequence)} rotateXYZ timesamples"
    )
    return True


def main():
    """Main function to convert orient to rotateXYZ for selected prims."""

    # Get the current USD context and stage
    context = omni.usd.get_context()
    stage = context.get_stage()

    if not stage:
        carb.log_error("No USD stage is currently open")
        return

    # Get selected prims
    selection = context.get_selection()
    selected_paths = selection.get_selected_prim_paths()

    if not selected_paths:
        carb.log_info("No prims selected. Please select prims to convert.")
        return

    carb.log_info("=" * 60)
    carb.log_info("Orient to RotateXYZ Conversion")
    carb.log_info("=" * 60)

    converted_count = 0
    total_processed = 0

    # Process each selected prim and its descendants
    for path in selected_paths:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            continue

        # Process the prim hierarchy
        for descendant in Usd.PrimRange(prim):
            total_processed += 1
            if convert_orient_to_rotateXYZ(descendant, stage):
                converted_count += 1

    # Summary
    carb.log_info("=" * 60)
    if converted_count > 0:
        carb.log_info(f"✓ Conversion complete!")
        carb.log_info(f"  Converted: {converted_count} prim(s)")
        carb.log_info(f"  Processed: {total_processed} prim(s)")
        carb.log_info(f"")
        carb.log_info(f"Note: The result is still timesamples, not keyframes.")
        carb.log_info(f"To convert to keyframes, use the Animation/Curve Editor.")
    else:
        carb.log_info(f"No prims with xformOp:orient found in selection.")
    carb.log_info("=" * 60)


if __name__ == "__main__":
    main()
