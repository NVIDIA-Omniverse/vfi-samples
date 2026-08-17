# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

import os
import sys
import unittest

# Allow importing the script under test from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "animation"))

from convert_orient_to_euler_simple import detect_gimbal_lock


class TestDetectGimbalLock(unittest.TestCase):
    def test_standard_gimbal_lock_angles(self):
        """±90° and 270° middle rotations are gimbal lock."""
        self.assertTrue(detect_gimbal_lock((0.0, 90.0, 0.0), "XYZ"))
        self.assertTrue(detect_gimbal_lock((0.0, -90.0, 0.0), "XYZ"))
        self.assertTrue(detect_gimbal_lock((0.0, 270.0, 0.0), "XYZ"))

    def test_wrapped_gimbal_lock_angles(self):
        """Angles coterminal with ±90° (e.g. 450°, -270°) must be detected."""
        self.assertTrue(detect_gimbal_lock((0.0, 450.0, 0.0), "XYZ"))
        self.assertTrue(detect_gimbal_lock((0.0, -270.0, 0.0), "XYZ"))
        self.assertTrue(detect_gimbal_lock((0.0, 630.0, 0.0), "XYZ"))
        self.assertTrue(detect_gimbal_lock((0.0, -450.0, 0.0), "XYZ"))

    def test_non_gimbal_lock_angles(self):
        """Angles far from ±90° are not gimbal lock."""
        self.assertFalse(detect_gimbal_lock((0.0, 0.0, 0.0), "XYZ"))
        self.assertFalse(detect_gimbal_lock((0.0, 180.0, 0.0), "XYZ"))
        self.assertFalse(detect_gimbal_lock((0.0, 360.0, 0.0), "XYZ"))

    def test_other_orders(self):
        """Wrapped-angle detection works for non-XYZ middle axes too."""
        self.assertTrue(detect_gimbal_lock((90.0, 0.0, 0.0), "YXZ"))
        self.assertTrue(detect_gimbal_lock((450.0, 0.0, 0.0), "YXZ"))
        self.assertTrue(detect_gimbal_lock((0.0, 0.0, 450.0), "XZY"))
        self.assertTrue(detect_gimbal_lock((450.0, 0.0, 0.0), "ZXY"))


if __name__ == "__main__":
    unittest.main()
