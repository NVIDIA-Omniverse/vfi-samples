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
Simple Clip Sequencer - Add animation clips to payloads in sequence order

Workflow:
1. User creates a stage and adds model payloads
2. User selects the prim with the payload
3. User adds clips in sequence order with start times
4. Script writes Value Clips metadata to the current stage

Author: USD Animation Pipeline
"""

import omni.usd
import omni.kit.commands
import omni.ui as ui
import carb
from typing import List, Dict, Optional, Tuple
import os

# Try to import file picker - different Omniverse versions have different modules
try:
    from omni.kit.window.filepicker import FilePickerDialog

    HAS_FILEPICKER = True
except ImportError:
    HAS_FILEPICKER = False
    carb.log_warn("FilePickerDialog not available, using manual path entry")

try:
    from pxr import Usd, Sdf, UsdGeom
except ImportError:
    carb.log_error("USD Python libraries not found.")
    raise


class ClipEntry:
    """Represents a single clip in the sequence."""

    def __init__(
        self,
        clip_path: str,
        start_time: float,
        clip_start: float = 0,
        clip_end: float = None,
    ):
        """
        Args:
            clip_path: Path to the animation clip file
            start_time: Stage time when this clip should start playing
            clip_start: Start frame within the clip file (default: 0)
            clip_end: End frame within the clip file (auto-detected if None)
        """
        self.clip_path = clip_path
        self.start_time = start_time
        self.clip_start = clip_start
        self.clip_end = clip_end  # Will be set when clip is analyzed
        self.duration = 0

    def __repr__(self):
        return f"ClipEntry('{os.path.basename(self.clip_path)}', start={self.start_time}, range={self.clip_start}-{self.clip_end})"


class SimpleClipSequencer:
    """
    Simple UI for sequencing animation clips on a payload prim.
    """

    def __init__(self):
        self._window = None
        self._clip_entries: List[ClipEntry] = []
        self._target_prim_path = ""
        self._clip_prim_path = "/root"  # Default primPath in clips
        self._clip_set_name = "default"

        # UI elements
        self._prim_path_field = None
        self._clip_prim_path_field = None
        self._clips_list_frame = None
        self._status_label = None
        self._file_picker = None
        self._manual_dialog = None
        self._manual_path_field = None

        self._build_ui()

    def _build_ui(self):
        """Build the sequencer UI."""
        self._window = ui.Window("Value Clip Sequencer", width=680, height=680)

        with self._window.frame:
            # Outer margin container
            with ui.HStack():
                ui.Spacer(width=12)
                with ui.VStack(spacing=10):
                    ui.Spacer(height=12)

                    # === Target Prim Section ===
                    ui.Label(
                        "TARGET PRIM",
                        style={
                            "color": 0xFFFFFFFF,
                            "font_size": 14,
                            "font_weight": "bold",
                        },
                        alignment=ui.Alignment.CENTER,
                    )
                    ui.Spacer(height=4)

                    with ui.HStack(height=26, spacing=4):
                        ui.Label("Prim Path:", width=80)
                        self._prim_path_field = ui.StringField(height=24)
                        self._prim_path_field.model.set_value("")
                        ui.Button(
                            "Get Selected",
                            width=100,
                            height=24,
                            clicked_fn=self._get_selected_prim,
                        )
                        ui.Button(
                            "Load Existing",
                            width=100,
                            height=24,
                            clicked_fn=self._load_existing_clips,
                        )

                    # Clip Prim Path is hidden but stored (defaults to /root for our extracted clips)
                    self._clip_prim_path_field = None  # Will use default "/root"

                    ui.Spacer(height=10)
                    ui.Line(style={"color": 0xFF444444}, height=2)
                    ui.Spacer(height=10)

                    # === Clips Section ===
                    ui.Label(
                        "ANIMATION CLIPS",
                        style={
                            "color": 0xFFFFFFFF,
                            "font_size": 14,
                            "font_weight": "bold",
                        },
                        alignment=ui.Alignment.CENTER,
                    )
                    ui.Spacer(height=4)

                    # Add clip buttons (centered, matching Apply button width)
                    with ui.HStack(height=30, spacing=8):
                        ui.Spacer(width=8)
                        ui.Button(
                            "+ ADD CLIP", height=28, clicked_fn=self._add_clip_dialog
                        )
                        ui.Button("Clear All", height=28, clicked_fn=self._clear_clips)
                        ui.Spacer(width=8)

                    ui.Spacer(height=4)

                    # Scrollable clips list
                    with ui.ScrollingFrame(
                        height=240, style={"background_color": 0xFF222222}
                    ):
                        self._clips_list_frame = ui.VStack(spacing=6)
                        self._rebuild_clips_list()

                    ui.Spacer(height=10)
                    ui.Line(style={"color": 0xFF444444}, height=2)
                    ui.Spacer(height=10)

                    # === Apply Button (full width, centered) ===
                    with ui.HStack(height=40):
                        ui.Spacer(width=8)
                        ui.Button(
                            "APPLY TO STAGE", height=36, clicked_fn=self._apply_to_stage
                        )
                        ui.Spacer(width=8)

                    ui.Spacer(height=8)

                    # === Status ===
                    with ui.HStack(height=26):
                        ui.Label("Status:", width=50)
                        self._status_label = ui.Label(
                            "Ready - Select a prim and add clips",
                            style={"color": 0xFF88FF88},
                        )

                    ui.Spacer(height=12)
                ui.Spacer(width=12)

    def _get_selected_prim(self):
        """Get the currently selected prim path."""
        ctx = omni.usd.get_context()
        selection = ctx.get_selection()
        paths = selection.get_selected_prim_paths()

        if paths:
            self._prim_path_field.model.set_value(paths[0])
            self._target_prim_path = paths[0]
            self._update_status(f"Selected: {paths[0]}", "info")

            # Try to find the animated prim inside the payload
            self._find_animated_prim(paths[0])
        else:
            self._update_status("No prim selected", "warning")

    def _find_animated_prim(self, payload_path: str):
        """Find the prim inside the payload that should receive the clips."""
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()

        if not stage:
            return

        prim = stage.GetPrimAtPath(payload_path)
        if not prim:
            return

        # Look for child prims that might be the animation target
        # Usually it's a direct child with a specific naming convention
        for child in prim.GetChildren():
            child_name = child.GetName()
            carb.log_info(f"Found child prim: {child_name}")

    def _load_existing_clips(self):
        """Load existing Value Clips from the selected prim into the editor."""
        target_path = self._prim_path_field.model.get_value_as_string()

        if not target_path:
            self._update_status("Please select a prim first (Get Selected)", "warning")
            return

        ctx = omni.usd.get_context()
        stage = ctx.get_stage()

        if not stage:
            self._update_status("No stage open", "error")
            return

        # Find the prim with clips metadata (might be the prim itself or a child)
        clips_prim = None
        clips_metadata = None

        # First check the target prim
        target_prim = stage.GetPrimAtPath(target_path)
        if target_prim:
            clips_metadata = target_prim.GetMetadata("clips")
            if clips_metadata:
                clips_prim = target_prim

        # If not found, check children
        if not clips_metadata and target_prim:
            for child in target_prim.GetChildren():
                clips_metadata = child.GetMetadata("clips")
                if clips_metadata:
                    clips_prim = child
                    break

        if not clips_metadata:
            self._update_status("No Value Clips found on this prim", "warning")
            return

        carb.log_info(f"Found clips metadata on: {clips_prim.GetPath()}")
        carb.log_info(f"Clips metadata: {clips_metadata}")

        # Parse the clips metadata
        try:
            self._parse_and_load_clips(clips_metadata, clips_prim)
            self._update_status(
                f"Loaded {len(self._clip_entries)} clips from {clips_prim.GetPath()}",
                "success",
            )
        except Exception as e:
            carb.log_error(f"Error parsing clips: {e}")
            self._update_status(f"Error loading clips: {str(e)}", "error")

    def _parse_and_load_clips(self, clips_metadata: dict, clips_prim):
        """Parse clips metadata and populate the clip entries."""
        # Clear existing entries
        self._clip_entries.clear()

        # Get the default clip set (or first available)
        clip_set_name = "default"
        if clip_set_name not in clips_metadata:
            # Try to get the first clip set
            if clips_metadata:
                clip_set_name = list(clips_metadata.keys())[0]
            else:
                carb.log_error("No clip sets found in metadata")
                return

        clip_set = clips_metadata.get(clip_set_name, {})

        # Extract arrays
        asset_paths = clip_set.get("assetPaths", [])
        active_array = clip_set.get("active", [])
        times_array = clip_set.get("times", [])

        carb.log_info(f"=== Loading Clips ===")
        carb.log_info(f"Asset paths ({len(asset_paths)}): {asset_paths}")
        carb.log_info(
            f"Active array type: {type(active_array)}, len: {len(active_array) if active_array else 0}"
        )
        carb.log_info(
            f"Times array type: {type(times_array)}, len: {len(times_array) if times_array else 0}"
        )

        if not asset_paths:
            carb.log_warn("No asset paths found in clips metadata")
            return

        # Get the stage directory for resolving relative paths
        stage = omni.usd.get_context().get_stage()
        stage_dir = ""
        if stage:
            root_layer = stage.GetRootLayer()
            if root_layer and root_layer.realPath:
                stage_dir = os.path.dirname(root_layer.realPath)

        # Build clip entries from the metadata
        num_clips = len(asset_paths)

        # Convert active array to list of (stage_time, clip_index)
        # Handle various USD types (Gf.Vec2d, tuples, lists)
        active_list = []
        for i, item in enumerate(active_array):
            try:
                # Try accessing as array/tuple
                if hasattr(item, "__getitem__"):
                    stage_time = float(item[0])
                    clip_idx = int(item[1])
                    active_list.append((stage_time, clip_idx))
                    carb.log_info(
                        f"  Active[{i}]: stage={stage_time}, clip_idx={clip_idx}"
                    )
            except Exception as e:
                carb.log_warn(f"  Could not parse active[{i}]: {item} - {e}")

        # Convert times array to list of (stage_time, clip_time)
        times_list = []
        for i, item in enumerate(times_array):
            try:
                if hasattr(item, "__getitem__"):
                    stage_time = float(item[0])
                    clip_time = float(item[1])
                    times_list.append((stage_time, clip_time))
                    if i < 10:  # Only log first 10
                        carb.log_info(
                            f"  Times[{i}]: stage={stage_time}, clip={clip_time}"
                        )
            except Exception as e:
                carb.log_warn(f"  Could not parse times[{i}]: {item} - {e}")

        if len(times_list) > 10:
            carb.log_info(f"  ... and {len(times_list) - 10} more time entries")

        carb.log_info(
            f"Parsed {len(active_list)} active entries, {len(times_list)} time entries"
        )

        # For each clip, determine start time and clip range
        for clip_idx in range(num_clips):
            # Get asset path
            asset_path = str(asset_paths[clip_idx])
            # Remove @ symbols if present
            asset_path = asset_path.strip("@")

            # Resolve to absolute path if needed
            if not os.path.isabs(asset_path) and stage_dir:
                asset_path = os.path.normpath(os.path.join(stage_dir, asset_path))

            # Find start time from active array
            start_time = 0.0
            for stage_time, active_idx in active_list:
                if active_idx == clip_idx:
                    start_time = stage_time
                    break

            # Find clip range from times array
            # Look for the time entry at this clip's start time
            clip_start = None
            clip_end = None

            # Find entries at the clip's start time
            for stage_time, clip_time in times_list:
                if abs(stage_time - start_time) < 0.01:  # Match within small epsilon
                    if clip_start is None:
                        clip_start = clip_time
                    else:
                        # Second entry at same time - this is the clip start
                        clip_start = clip_time
                elif stage_time > start_time and clip_start is not None:
                    # First entry after start - this gives us the end
                    clip_end = clip_time
                    break

            # If we didn't find proper values, try reading from the clip file
            if clip_start is None or clip_end is None:
                try:
                    clip_layer = Sdf.Layer.FindOrOpen(asset_path)
                    if clip_layer:
                        file_start = clip_layer.startTimeCode
                        file_end = clip_layer.endTimeCode
                        if file_start is not None and file_end is not None:
                            if clip_start is None:
                                clip_start = file_start
                            if clip_end is None:
                                clip_end = file_end
                            carb.log_info(
                                f"  Got range from file: {file_start} - {file_end}"
                            )
                except Exception as e:
                    carb.log_warn(f"  Could not read clip file {asset_path}: {e}")

            # Final fallback
            if clip_start is None:
                clip_start = 0.0
            if clip_end is None:
                clip_end = clip_start + 100.0

            # Create clip entry
            entry = ClipEntry(
                clip_path=asset_path,
                start_time=start_time,
                clip_start=clip_start,
                clip_end=clip_end,
            )
            entry.duration = clip_end - clip_start

            self._clip_entries.append(entry)
            carb.log_info(f"Loaded clip {clip_idx}: {os.path.basename(asset_path)}")
            carb.log_info(
                f"  Stage Start: {start_time}, Clip Range: {clip_start} - {clip_end}"
            )

        # Rebuild the UI
        self._rebuild_clips_list()

    def _add_clip_dialog(self):
        """Open file dialog to add a clip."""
        if HAS_FILEPICKER:
            self._open_file_picker()
        else:
            self._open_manual_path_dialog()

    def _open_file_picker(self):
        """Open the Omniverse file picker dialog."""

        def on_click_open(filename: str, dirname: str):
            """Called when user clicks Open in the file picker."""
            if filename:
                full_path = os.path.join(dirname, filename)
                carb.log_info(f"File selected: {full_path}")
                self._add_clip_entry(full_path)

        def on_click_cancel(filename: str, dirname: str):
            """Called when user clicks Cancel."""
            carb.log_info("File picker cancelled")

        # Get the current stage directory as starting point
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        start_dir = ""
        if stage:
            root_layer = stage.GetRootLayer()
            if root_layer and root_layer.realPath:
                start_dir = os.path.dirname(root_layer.realPath)

        # Create the file picker dialog
        self._file_picker = FilePickerDialog(
            "Select Animation Clip",
            apply_button_label="Add Clip",
            click_apply_handler=on_click_open,
            click_cancel_handler=on_click_cancel,
            file_extension_options=[
                ("*.usda", "USD ASCII Files"),
                ("*.usd", "USD Files"),
                ("*.usdc", "USD Crate Files"),
            ],
            enable_file_bar=True,
        )
        self._file_picker.show(start_dir if start_dir else None)

    def _open_manual_path_dialog(self):
        """Open a manual path entry dialog as fallback."""
        self._manual_dialog = ui.Window("Add Clip - Enter Path", width=500, height=120)

        with self._manual_dialog.frame:
            with ui.VStack(spacing=8):
                ui.Spacer(height=8)
                ui.Label("Enter the full path to the animation clip file:")

                self._manual_path_field = ui.StringField(height=24)
                self._manual_path_field.model.set_value("")

                with ui.HStack(height=28):
                    ui.Spacer()
                    ui.Button(
                        "Add Clip", width=100, clicked_fn=self._on_manual_path_confirm
                    )
                    ui.Button(
                        "Cancel", width=80, clicked_fn=self._on_manual_path_cancel
                    )
                    ui.Spacer()
                ui.Spacer(height=8)

    def _on_manual_path_confirm(self):
        """Handle manual path entry confirmation."""
        if self._manual_path_field:
            path = self._manual_path_field.model.get_value_as_string().strip()
            if path:
                self._add_clip_entry(path)
        if hasattr(self, "_manual_dialog") and self._manual_dialog:
            self._manual_dialog.visible = False

    def _on_manual_path_cancel(self):
        """Handle manual path entry cancellation."""
        if hasattr(self, "_manual_dialog") and self._manual_dialog:
            self._manual_dialog.visible = False

    def _add_clip_entry(self, clip_path: str):
        """Add a new clip entry to the sequence."""
        # Calculate default start time (after the last clip)
        if self._clip_entries:
            last_entry = self._clip_entries[-1]
            # Default: start after estimated duration of last clip
            default_start = last_entry.start_time + 500  # Default 500 frame gap
        else:
            default_start = 0

        # Analyze the clip to get its time range
        clip_start, clip_end = self._analyze_clip(clip_path)

        entry = ClipEntry(
            clip_path=clip_path,
            start_time=default_start,
            clip_start=clip_start,
            clip_end=clip_end,
        )
        entry.duration = clip_end - clip_start if clip_end else 0

        self._clip_entries.append(entry)
        self._rebuild_clips_list()
        self._update_status(f"Added clip: {os.path.basename(clip_path)}", "info")

    def _analyze_clip(self, clip_path: str) -> Tuple[float, float]:
        """Analyze a clip file to get its time range."""
        try:
            # Try to open the clip and get its time range
            carb.log_info(f"Analyzing clip: {clip_path}")
            clip_layer = Sdf.Layer.FindOrOpen(clip_path)
            if clip_layer:
                start = clip_layer.startTimeCode
                end = clip_layer.endTimeCode
                carb.log_info(
                    f"  ✓ Clip time range: {start} - {end} (duration: {end - start})"
                )

                # Validate - some clips might have 0,0 if not set
                if start == 0 and end == 0:
                    carb.log_warn(f"  ⚠ Clip has no time codes set, using fallback")
                    return (0, 100)

                return (start, end)
            else:
                carb.log_warn(f"  ✗ Could not open clip layer")
        except Exception as e:
            carb.log_warn(f"  ✗ Error analyzing clip: {e}")

        # Default fallback - user should check this!
        carb.log_warn(
            f"  Using fallback time range 0-100 - you may need to edit this in the UI"
        )
        return (0, 100)

    def _rebuild_clips_list(self):
        """Rebuild the clips list UI."""
        if not self._clips_list_frame:
            return

        # Clear existing content using clear() method
        try:
            self._clips_list_frame.clear()
        except Exception as e:
            carb.log_warn(f"Could not clear clips list: {e}")

        if not self._clip_entries:
            with self._clips_list_frame:
                ui.Label(
                    "No clips added yet. Click '+ ADD CLIP' to add animation clips.",
                    style={"color": 0xFF888888},
                    height=30,
                )
            return

        with self._clips_list_frame:
            for idx, entry in enumerate(self._clip_entries):
                self._build_clip_row(idx, entry)

    def _build_clip_row(self, idx: int, entry: ClipEntry):
        """Build a single clip row in the list."""
        with ui.VStack(spacing=2):
            with ui.HStack(height=26, spacing=4):
                # Index label
                ui.Label(f"{idx + 1}.", width=20, style={"color": 0xFF88AAFF})

                # Clip filename
                filename = os.path.basename(entry.clip_path)
                ui.Label(filename, width=180, elided_text=True)

                # Stage Start time field
                ui.Label("Stage Start:", width=70)
                start_field = ui.FloatField(width=60, height=22)
                start_field.model.set_value(entry.start_time)

                def on_start_changed(model, i=idx):
                    if i < len(self._clip_entries):
                        self._clip_entries[i].start_time = model.get_value_as_float()

                start_field.model.add_value_changed_fn(on_start_changed)

                # Move up/down buttons
                ui.Button(
                    "Up",
                    width=28,
                    height=22,
                    clicked_fn=lambda i=idx: self._move_clip(i, -1),
                )
                ui.Button(
                    "Dn",
                    width=28,
                    height=22,
                    clicked_fn=lambda i=idx: self._move_clip(i, 1),
                )

                # Remove button
                ui.Button(
                    "X",
                    width=22,
                    height=22,
                    clicked_fn=lambda i=idx: self._remove_clip(i),
                )

            # Second row: Clip internal time range (editable)
            with ui.HStack(height=22, spacing=4):
                ui.Spacer(width=24)
                ui.Label("Clip Range:", width=70, style={"color": 0xFF888888})

                clip_start_field = ui.FloatField(width=60, height=20)
                clip_start_field.model.set_value(entry.clip_start)

                ui.Label("-", width=10)

                clip_end_field = ui.FloatField(width=60, height=20)
                clip_end_field.model.set_value(entry.clip_end)

                # Duration label - updates dynamically when clip range changes
                duration = entry.clip_end - entry.clip_start
                duration_label = ui.Label(
                    f"(duration: {duration:.0f})",
                    width=100,
                    style={"color": 0xFF666666},
                )

                def update_duration_label(label, start_field, end_field):
                    """Helper to update the duration label from current field values."""
                    start_val = start_field.model.get_value_as_float()
                    end_val = end_field.model.get_value_as_float()
                    new_duration = end_val - start_val
                    label.text = f"(duration: {new_duration:.0f})"

                def on_clip_start_changed(model, i=idx, lbl=duration_label, sf=clip_start_field, ef=clip_end_field):
                    if i < len(self._clip_entries):
                        self._clip_entries[i].clip_start = model.get_value_as_float()
                        update_duration_label(lbl, sf, ef)

                def on_clip_end_changed(model, i=idx, lbl=duration_label, sf=clip_start_field, ef=clip_end_field):
                    if i < len(self._clip_entries):
                        self._clip_entries[i].clip_end = model.get_value_as_float()
                        update_duration_label(lbl, sf, ef)

                clip_start_field.model.add_value_changed_fn(on_clip_start_changed)
                clip_end_field.model.add_value_changed_fn(on_clip_end_changed)

            # Separator
            ui.Line(style={"color": 0xFF333333}, height=1)

    def _move_clip(self, idx: int, direction: int):
        """Move a clip up or down in the sequence."""
        new_idx = idx + direction
        if 0 <= new_idx < len(self._clip_entries):
            self._clip_entries[idx], self._clip_entries[new_idx] = (
                self._clip_entries[new_idx],
                self._clip_entries[idx],
            )
            self._rebuild_clips_list()

    def _remove_clip(self, idx: int):
        """Remove a clip from the sequence."""
        if 0 <= idx < len(self._clip_entries):
            removed = self._clip_entries.pop(idx)
            self._rebuild_clips_list()
            self._update_status(
                f"Removed: {os.path.basename(removed.clip_path)}", "info"
            )

    def _clear_clips(self):
        """Clear all clips from the sequence."""
        self._clip_entries.clear()
        self._rebuild_clips_list()
        self._update_status("Cleared all clips", "info")

    def _preview_sequence(self):
        """Preview what the Value Clips metadata will look like."""
        if not self._clip_entries:
            self._update_status("No clips to preview", "warning")
            return

        target_path = self._prim_path_field.model.get_value_as_string()
        clip_prim_path = "/root"  # Default for clips extracted by our tool

        # Build the clips data
        asset_paths, active, times = self._build_clips_data()

        carb.log_info("=" * 60)
        carb.log_info("CLIP SEQUENCE PREVIEW")
        carb.log_info("=" * 60)
        carb.log_info(f"Target Prim: {target_path}")
        carb.log_info(f"Clip Prim Path: {clip_prim_path}")
        carb.log_info(f"")
        carb.log_info(f"Asset Paths: {asset_paths}")
        carb.log_info(f"Active: {active}")
        carb.log_info(f"Times: {times}")
        carb.log_info("=" * 60)

        self._update_status(f"Preview logged - {len(self._clip_entries)} clips", "info")

    def _build_clips_data(self) -> Tuple[List[str], List[Tuple], List[Tuple]]:
        """
        Build the clips metadata arrays matching USD Value Clips spec.

        Sample format from working file:
            active = [(0, 0), (1000, 1)]
            times = [
                (0, 2052),      # Clip 0 start
                (726, 2778),    # Clip 0 end
                (1000, 2778),   # Hold at clip 0 end until switch
                (1000, 2052),   # Clip 1 start (duplicate stage time!)
                (1726, 2778),   # Clip 1 end
                (2000, 2778)    # Hold at clip 1 end
            ]

        Returns:
            (assetPaths, active, times) tuples
        """
        asset_paths = []
        active = []
        times = []

        # Sort clips by start time
        sorted_clips = sorted(self._clip_entries, key=lambda c: c.start_time)

        if not sorted_clips:
            return asset_paths, active, times

        # Get stage time range for clamping
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        stage_end = 10000
        if stage:
            stage_end = stage.GetEndTimeCode()

        for idx, clip in enumerate(sorted_clips):
            asset_paths.append(clip.clip_path)

            # Active array: (stage_time, clip_index)
            active.append((float(clip.start_time), float(idx)))

            # Calculate clip duration
            clip_duration = float(clip.clip_end) - float(clip.clip_start)
            clip_end_stage_time = float(clip.start_time) + clip_duration

            # Get next clip start time (if any)
            next_clip_start = None
            if idx + 1 < len(sorted_clips):
                next_clip_start = float(sorted_clips[idx + 1].start_time)

            # === Build times array entries ===

            # 1. Start of this clip: (stage_start, clip_start)
            times.append((float(clip.start_time), float(clip.clip_start)))

            # 2. Natural end of this clip: (stage_end, clip_end)
            times.append((float(clip_end_stage_time), float(clip.clip_end)))

            # 3. Handle gap/transition to next clip
            if next_clip_start is not None:
                # Hold at this clip's end until the next clip starts
                # This creates the "hold at end" behavior
                if next_clip_start > clip_end_stage_time:
                    times.append((float(next_clip_start), float(clip.clip_end)))

                # The next clip will add its own (next_clip_start, next_clip_start_time)
                # This creates the duplicate stage time at the transition point

        # === Add END clamp to prevent forward extrapolation ===
        last_clip = sorted_clips[-1]
        last_clip_duration = float(last_clip.clip_end) - float(last_clip.clip_start)
        last_clip_stage_end = float(last_clip.start_time) + last_clip_duration

        # Extend to stage end (or beyond) to hold the last frame
        final_stage_time = float(max(stage_end, last_clip_stage_end + 1000))
        times.append((final_stage_time, float(last_clip.clip_end)))
        carb.log_info(f"  Added end clamp: ({final_stage_time}, {last_clip.clip_end})")

        # Log for debugging
        carb.log_info("=" * 50)
        carb.log_info("CLIPS DATA BUILT:")
        carb.log_info(f"  Clips: {len(sorted_clips)}")
        for i, c in enumerate(sorted_clips):
            carb.log_info(
                f"    [{i}] {os.path.basename(c.clip_path)}: stage_start={c.start_time}, clip_range={c.clip_start}-{c.clip_end}"
            )
        carb.log_info(f"  active: {active}")
        carb.log_info(f"  times: {times}")
        carb.log_info("=" * 50)

        return asset_paths, active, times

    def _apply_to_stage(self):
        """Apply the Value Clips metadata to the current stage."""
        target_path = self._prim_path_field.model.get_value_as_string()
        clip_prim_path = "/root"  # Default for clips extracted by our tool

        if not target_path:
            self._update_status("Please select a target prim", "error")
            return

        if not self._clip_entries:
            self._update_status("No clips to apply", "error")
            return

        ctx = omni.usd.get_context()
        stage = ctx.get_stage()

        if not stage:
            self._update_status("No stage open", "error")
            return

        try:
            # Get the root layer (current stage file)
            root_layer = stage.GetRootLayer()

            # Check if stage is saved (required for relative path calculation)
            if not root_layer.realPath:
                self._update_status(
                    "Please save your stage first before applying clips", "error"
                )
                carb.log_warn(
                    "Stage must be saved before applying clips - relative paths require a stage location"
                )
                return

            # Find or create the target prim spec
            target_prim = stage.GetPrimAtPath(target_path)
            if not target_prim:
                self._update_status(f"Prim not found: {target_path}", "error")
                return

            # Find the child prim that should receive the clips
            # This is usually the root prim inside the payload
            clips_target_path = self._find_clips_target(target_prim)

            if not clips_target_path:
                self._update_status(
                    "Could not find target for clips inside payload", "error"
                )
                return

            # Build clips data
            asset_paths, active, times = self._build_clips_data()

            # Make paths relative to the stage file
            stage_dir = os.path.dirname(root_layer.realPath)
            relative_paths = []
            for path in asset_paths:
                try:
                    rel_path = os.path.relpath(path, stage_dir)
                    relative_paths.append(rel_path.replace("\\", "/"))
                except ValueError:
                    # Different drives on Windows
                    relative_paths.append(path.replace("\\", "/"))

            # Apply the clips metadata
            self._write_clips_metadata(
                root_layer,
                clips_target_path,
                clip_prim_path,
                relative_paths,
                active,
                times,
            )

            # Save the stage
            root_layer.Save()

            self._update_status(
                f"Applied {len(self._clip_entries)} clips to {clips_target_path}",
                "success",
            )
            carb.log_info(f"✅ Successfully applied clips to {clips_target_path}")

        except Exception as e:
            carb.log_error(f"Error applying clips: {e}")
            self._update_status(f"Error: {str(e)}", "error")

    def _find_clips_target(self, payload_prim: Usd.Prim) -> Optional[str]:
        """
        Find the prim path that should receive the clips metadata.
        This is typically a child prim inside the payload.
        """
        # First, check if there are direct children
        children = list(payload_prim.GetChildren())

        if len(children) == 1:
            # Single child - this is likely the animation root
            return str(children[0].GetPath())

        if len(children) > 1:
            # Multiple children - log them and let user know
            carb.log_info(
                f"Found {len(children)} children under {payload_prim.GetPath()}:"
            )
            for child in children:
                carb.log_info(f"  - {child.GetName()}")

            # Return the first child as default (user can adjust)
            return str(children[0].GetPath())

        # No children - apply directly to the prim
        return str(payload_prim.GetPath())

    def _write_clips_metadata(
        self,
        layer: Sdf.Layer,
        target_path: str,
        clip_prim_path: str,
        asset_paths: List[str],
        active: List[Tuple],
        times: List[Tuple],
    ):
        """
        Write Value Clips metadata to the layer.

        Note: SetInfo may throw "Invalid type for key" but the data is still written correctly.
        This appears to be a USD Python binding quirk.
        """
        prim_spec = Sdf.CreatePrimInLayer(layer, target_path)
        if not prim_spec:
            carb.log_error(f"Failed to create prim spec at {target_path}")
            return

        prim_spec.specifier = Sdf.SpecifierOver

        # Build clips dictionary with explicit types
        clips_dict = {
            self._clip_set_name: {
                "assetPaths": Sdf.AssetPathArray(
                    [Sdf.AssetPath(p) for p in asset_paths]
                ),
                "primPath": clip_prim_path,
                "active": Vt.Vec2dArray(
                    [Gf.Vec2d(float(a[0]), float(a[1])) for a in active]
                ),
                "times": Vt.Vec2dArray(
                    [Gf.Vec2d(float(t[0]), float(t[1])) for t in times]
                ),
            }
        }

        # SetInfo may throw but still write the data - this is a known quirk
        try:
            prim_spec.SetInfo("clips", clips_dict)
        except Exception:
            pass  # Data is written despite the exception

        try:
            prim_spec.SetInfo("clipSets", [self._clip_set_name])
        except Exception:
            pass  # Data is written despite the exception

        carb.log_info(f"Written clips metadata to {target_path}")
        carb.log_info(f"  assetPaths: {[os.path.basename(p) for p in asset_paths]}")
        carb.log_info(f"  primPath: {clip_prim_path}")
        carb.log_info(f"  active: {active}")
        carb.log_info(f"  times: {len(times)} entries")

    def _update_status(self, message: str, level: str = "info"):
        """Update the status label."""
        colors = {
            "info": 0xFF88FF88,
            "warning": 0xFFFFAA44,
            "error": 0xFFFF4444,
            "success": 0xFF44FF88,
        }

        # Truncate long messages to prevent UI expansion
        max_length = 60
        display_message = (
            message if len(message) <= max_length else message[:max_length] + "..."
        )

        if self._status_label:
            self._status_label.text = display_message
            self._status_label.style = {"color": colors.get(level, 0xFFFFFFFF)}

        # Always log full message to console
        if level == "error":
            carb.log_error(message)
        elif level == "warning":
            carb.log_warn(message)
        else:
            carb.log_info(message)

    def destroy(self):
        """Clean up the UI."""
        if self._window:
            self._window.destroy()
            self._window = None


# Import additional USD types needed for clips
try:
    from pxr import Vt, Gf
except ImportError:
    carb.log_error("Could not import Vt/Gf from pxr")


# Global instance
_sequencer_instance = None


def show_window():
    """Show the Simple Clip Sequencer window."""
    global _sequencer_instance
    if _sequencer_instance:
        _sequencer_instance.destroy()
    _sequencer_instance = SimpleClipSequencer()
    return _sequencer_instance


def hide_window():
    """Hide the Simple Clip Sequencer window."""
    global _sequencer_instance
    if _sequencer_instance:
        _sequencer_instance.destroy()
        _sequencer_instance = None


# Auto-show when script is run
if __name__ == "__main__" or True:
    show_window()
