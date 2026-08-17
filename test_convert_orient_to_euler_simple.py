# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

import unittest

from scripts.animation.convert_orient_to_euler_simple import detect_gimbal_lock


class TestGimbalLockThreshold(unittest.TestCase):
    def test_threshold_out_of_range_raises(self):
        valid_angles = (0.0, 0.0, 0.0)
        for bad in (-1.0, 0.0, 90.1, 100.0, float("inf")):
            with self.subTest(threshold=bad):
                with self.assertRaises(ValueError):
                    detect_gimbal_lock(valid_angles, "XYZ", bad)

    def test_threshold_in_range_accepted(self):
        valid_angles = (0.0, 0.0, 0.0)
        for good in (0.1, 1.0, 85.0, 90.0):
            with self.subTest(threshold=good):
                self.assertFalse(detect_gimbal_lock(valid_angles, "XYZ", good))


if __name__ == "__main__":
    unittest.main()
