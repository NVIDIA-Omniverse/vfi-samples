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
Utility for discovering reference/payload prims, editing their
layer offsets, and resetting animations while preserving original asset paths.
"""

import os
import omni.client
import omni.usd
import omni.ui as ui
import carb
from pxr import Usd, Sdf
from typing import Dict, List, Any, Optional, Tuple


class ReferenceTimeOffsetEditor:
    def __init__(self):
        self.stage = omni.usd.get_context().get_stage()
        self.selection = omni.usd.get_context().get_selection()
        self.reference_prims = {}
        self.window = None
        self.offset_field = None
        self.references_summary_label = None

        carb.log_info(
            "Reference Time Offset Editor initialized with relative path preservation"
        )

    def _is_relative_path(self, path_or_url: str) -> bool:
        # an empty string is the current folder
        if not path_or_url:
            return False
            
        url = omni.client.break_url(path_or_url)
        
        # raw path e.g. no prefix like file:// or omniverse://
        # url like ../test.usd is considered URL but no scheme.Process it as a local path
        # os library will take care of it
        if url.is_raw or not url.scheme:
            return not os.path.isabs(path_or_url)
        
        #Proces file:// protocal
        if url.scheme == "file":
            path_part = url.path
            # Windows fix:  /C:/Users --> C:/Users
            if os.name == "nt" and len(path_part) >= 3 and path_part[0] == "/" and path_part[2] == ":":
                path_part = path_part[1:]
            return not os.path.isabs(path_part)
            
        # other URL with prefix omniverse://, https:// etc are not relative path
        return False

    def _find_original_asset_path(self, prim, prim_type="payload"):
        try:
            prim_path = str(prim.GetPath())
            carb.log_info(f"Finding original {prim_type} path for: {prim_path}")

            prim_stack = prim.GetPrimStack()
            relative_paths = []
            absolute_paths = []

            for i, prim_spec in enumerate(prim_stack):
                layer_id = (
                    prim_spec.layer.identifier if prim_spec.layer else f"Layer_{i}"
                )

                if prim_type == "payload":
                    list_attr = "payloadList"
                else:
                    list_attr = "referenceList"

                if not hasattr(prim_spec, list_attr):
                    continue

                item_list = getattr(prim_spec, list_attr)
                if not item_list:
                    continue

                if hasattr(item_list, "explicitItems") and item_list.explicitItems:
                    for item in item_list.explicitItems:
                        if hasattr(item, "assetPath") and item.assetPath:
                            path_info = {
                                "asset_path": str(item.assetPath),
                                "prim_path": (
                                    str(item.primPath) if item.primPath else ""
                                ),
                                "layer_offset": item.layerOffset,
                                "layer_index": i,
                                "layer_id": layer_id,
                            }

                            if self._is_relative_path(path_info["asset_path"]):
                                relative_paths.append(path_info)
                                carb.log_info(
                                    f"Found relative path: '{path_info['asset_path']}'"
                                )
                            else:
                                absolute_paths.append(path_info)

            if relative_paths:
                original_path = max(relative_paths, key=lambda x: x["layer_index"])
                carb.log_info(
                    f"Using original relative path: '{original_path['asset_path']}'"
                )
                return original_path
            elif absolute_paths:
                original_path = max(absolute_paths, key=lambda x: x["layer_index"])
                carb.log_info(
                    f"Using deepest absolute path: '{original_path['asset_path']}'"
                )
                return original_path
            else:
                carb.log_warn(f"No {prim_type} paths found")
                return None

        except Exception as e:
            carb.log_error(f"Error finding original asset path: {str(e)}")
            return None

    def discover_reference_prims(self):
        try:
            carb.log_info(
                "Discovering references/payloads with original path preservation..."
            )

            # Get fresh stage reference (important after save/reload)
            current_stage = omni.usd.get_context().get_stage()
            if not current_stage:
                carb.log_error("No stage available")
                return {}

            selected_paths = self.selection.get_selected_prim_paths()
            if not selected_paths:
                carb.log_warn("No prims selected")
                return {}

            reference_prims = {}

            for prim_path_str in selected_paths:
                # Validate path string before creating SdfPath
                if (
                    not prim_path_str
                    or not isinstance(prim_path_str, str)
                    or prim_path_str.strip() == ""
                ):
                    carb.log_warn(f"Skipping invalid path: '{prim_path_str}'")
                    continue

                try:
                    # Import Sdf locally and create SdfPath properly
                    from pxr import Sdf

                    # Additional validation to prevent SdfPath warnings
                    clean_path = prim_path_str.strip()
                    if not clean_path or clean_path == "":
                        carb.log_warn(
                            f"Skipping empty path after cleaning: '{prim_path_str}'"
                        )
                        continue

                    # Create SdfPath object explicitly
                    sdf_path = Sdf.Path(clean_path)

                    # Validate the SdfPath was created successfully
                    if not sdf_path or sdf_path.isEmpty:
                        carb.log_warn(
                            f"Failed to create valid SdfPath from: '{clean_path}'"
                        )
                        continue

                    prim = current_stage.GetPrimAtPath(sdf_path)

                    if not prim.IsValid():
                        continue

                    has_references = prim.HasAuthoredReferences()
                    has_payloads = prim.HasPayload()

                    if not has_references and not has_payloads:
                        continue

                    ref_info = {
                        "has_references": has_references,
                        "has_payloads": has_payloads,
                        "current_offset": 0.0,
                        "asset_paths": [],
                        "prim_paths": [],
                        "original_asset_paths": [],
                        "path_types": [],
                    }

                    if has_payloads:
                        original_payload = self._find_original_asset_path(
                            prim, "payload"
                        )
                        if original_payload:
                            ref_info["asset_paths"].append(
                                original_payload["asset_path"]
                            )
                            ref_info["prim_paths"].append(original_payload["prim_path"])
                            ref_info["original_asset_paths"].append(
                                original_payload["asset_path"]
                            )
                            ref_info["path_types"].append(
                                "relative"
                                if self._is_relative_path(
                                    original_payload["asset_path"]
                                )
                                else "absolute"
                            )

                            if original_payload["layer_offset"]:
                                ref_info["current_offset"] = original_payload[
                                    "layer_offset"
                                ].offset

                    if has_references:
                        original_reference = self._find_original_asset_path(
                            prim, "reference"
                        )
                        if original_reference:
                            ref_info["asset_paths"].append(
                                original_reference["asset_path"]
                            )
                            ref_info["prim_paths"].append(
                                original_reference["prim_path"]
                            )
                            ref_info["original_asset_paths"].append(
                                original_reference["asset_path"]
                            )
                            ref_info["path_types"].append(
                                "relative"
                                if self._is_relative_path(
                                    original_reference["asset_path"]
                                )
                                else "absolute"
                            )

                            if original_reference["layer_offset"]:
                                ref_info["current_offset"] = original_reference[
                                    "layer_offset"
                                ].offset

                    if ref_info["asset_paths"]:
                        reference_prims[prim_path_str] = ref_info
                        path_type = (
                            ref_info["path_types"][0]
                            if ref_info["path_types"]
                            else "unknown"
                        )
                        carb.log_info(
                            f"Found {prim_path_str}: {ref_info['original_asset_paths'][0]} ({path_type})"
                        )

                except Exception as prim_error:
                    carb.log_error(
                        f"Error analyzing prim {prim_path_str}: {str(prim_error)}"
                    )
                    continue

            carb.log_info(
                f"Discovery complete: {len(reference_prims)} prims with references/payloads"
            )
            return reference_prims

        except Exception as e:
            carb.log_error(f"Error discovering references: {str(e)}")
            return {}

    def create_ui(self):
        """Create the UI window for the Reference Time Offset Editor."""
        try:
            self.window = ui.Window(
                "Reference Time Offset (Relative Paths)",
                width=520,  # Wider to accommodate the longer title
                height=220,
                flags=ui.WINDOW_FLAGS_NO_COLLAPSE,
            )

            with self.window.frame:
                with ui.VStack(
                    spacing=0, style={"margin": 0, "background_color": 0xFF404040}
                ):
                    # Selection instruction - centered, more accurate guidance
                    ui.Label(
                        "Select Prim(s) hierarchy",
                        alignment=ui.Alignment.CENTER,
                        style={"font_size": 14, "color": 0xFFFFFFFF, "margin": 8},
                    )

                    # References summary
                    self.references_summary_label = ui.Label(
                        "No references/payloads discovered yet",
                        alignment=ui.Alignment.CENTER,
                        style={"font_size": 12, "color": 0xFFCCCCCC, "margin": 4},
                    )

                    ui.Spacer(height=8)

                    # Refresh button - same color as Apply Offset
                    self._create_styled_button(
                        "Refresh Discovery (Optional)",
                        self._refresh_discovery,
                        height=24,
                        bg_color=0xFF2A2A2A,  # Dark grey to match Apply Offset
                        border_color=0xFF555555,
                    )

                    ui.Spacer(height=12)

                    # Time Offset controls - perfectly aligned
                    with ui.HStack(spacing=8, style={"alignment": ui.Alignment.CENTER}):
                        # Time Offset label - left aligned
                        ui.Label(
                            "Time Offset:",
                            width=80,
                            style={
                                "font_size": 14,
                                "color": 0xFFFFFFFF,
                                "alignment": ui.Alignment.LEFT_CENTER,
                            },
                        )

                        ui.Spacer()  # Push controls to center-right

                        # Controls group - centered
                        with ui.HStack(
                            spacing=8, style={"alignment": ui.Alignment.CENTER}
                        ):
                            with ui.VStack(
                                width=20, style={"alignment": ui.Alignment.CENTER}
                            ):
                                ui.Button(
                                    "-",
                                    clicked_fn=self._decrement_offset,
                                    width=20,
                                    height=20,
                                    style={
                                        "background_color": 0xFF555555,
                                        "color": 0xFFFFFFFF,
                                        "font_size": 14,
                                        "border_width": 1,
                                        "border_color": 0xFF777777,
                                        "margin": 0,
                                        "padding": 0,
                                    },
                                )

                            with ui.VStack(
                                width=80, style={"alignment": ui.Alignment.CENTER}
                            ):
                                self.offset_field = ui.FloatField(
                                    width=80,
                                    height=22,
                                    style={
                                        "color": 0xFFFFFFFF,
                                        "font_size": 14,
                                        "background_color": 0xFF333333,
                                        "border_width": 1,
                                        "border_color": 0xFF666666,
                                        "margin": 0,
                                        "padding": 4,
                                        "text-align": "center",
                                    },
                                )
                                self.offset_field.model.set_value(0.0)

                            with ui.VStack(
                                width=20, style={"alignment": ui.Alignment.CENTER}
                            ):
                                ui.Button(
                                    "+",
                                    clicked_fn=self._increment_offset,
                                    width=20,
                                    height=20,
                                    style={
                                        "background_color": 0xFF555555,
                                        "color": 0xFFFFFFFF,
                                        "font_size": 14,
                                        "border_width": 1,
                                        "border_color": 0xFF777777,
                                        "margin": 0,
                                        "padding": 0,
                                    },
                                )

                        ui.Spacer()  # Balance the layout

                    # Apply Offset button - full width, dark
                    self._create_styled_button(
                        "Apply Offset",
                        self._apply_offset,
                        height=28,
                        bg_color=0xFF2A2A2A,
                        border_color=0xFF555555,
                    )

                    ui.Spacer(height=4)

                    # Reset Animation button - full width, red tint
                    self._create_styled_button(
                        "Reset Animation",
                        self._reset_animation,
                        height=28,
                        bg_color=0xFF4A2A2A,  # Slightly red tint
                        border_color=0xFF775555,
                    )

            carb.log_info("Reference Time Offset Editor UI created successfully")

        except Exception as e:
            carb.log_error(f"Error creating UI: {str(e)}")

    def _create_styled_button(
        self,
        text: str,
        callback,
        height: int = 24,
        bg_color: int = 0xFF555555,
        border_color: int = 0xFF777777,
    ):
        """Create a styled button with consistent appearance."""
        return ui.Button(
            text,
            clicked_fn=callback,
            height=height,
            style={
                "background_color": bg_color,
                "color": 0xFFFFFFFF,
                "font_size": 12,
                "border_width": 1,
                "border_color": border_color,
                "margin": 2,
            },
        )

    def _refresh_discovery(self):
        try:
            carb.log_info("Manual refresh requested")
            self.reference_prims = self.discover_reference_prims()
            self._update_references_summary()
        except Exception as e:
            carb.log_error(f"Error refreshing discovery: {str(e)}")

    def _update_references_summary(self):
        """Update the references summary label."""
        try:
            if self.references_summary_label:
                # Clear old text first
                self.references_summary_label.text = ""

                if self.reference_prims:
                    relative_count = sum(
                        1
                        for info in self.reference_prims.values()
                        if info.get("path_types") and "relative" in info["path_types"]
                    )
                    absolute_count = len(self.reference_prims) - relative_count

                    summary = f"Found {len(self.reference_prims)} prim(s): {relative_count} relative, {absolute_count} absolute paths"
                else:
                    summary = "No references/payloads found in selection"

                self.references_summary_label.text = summary
        except Exception as e:
            carb.log_error(f"Error updating references summary: {str(e)}")

    def _increment_offset(self):
        try:
            current_value = self.offset_field.model.as_float
            self.offset_field.model.set_value(current_value + 1.0)
            carb.log_info(f"Incremented offset to {current_value + 1.0}")
        except Exception as e:
            carb.log_error(f"Error incrementing offset: {str(e)}")

    def _decrement_offset(self):
        try:
            current_value = self.offset_field.model.as_float
            self.offset_field.model.set_value(current_value - 1.0)
            carb.log_info(f"Decremented offset to {current_value - 1.0}")
        except Exception as e:
            carb.log_error(f"Error decrementing offset: {str(e)}")

    def _apply_offset(self):
        try:
            offset = self.offset_field.model.as_float
            carb.log_info(
                f"Applying offset {offset} with relative path preservation..."
            )

            # Get fresh stage reference (important after save/reload)
            current_stage = omni.usd.get_context().get_stage()
            if not current_stage:
                carb.log_error("No stage available")
                return

            # Get current selection
            current_selected_paths = self.selection.get_selected_prim_paths()
            if not current_selected_paths:
                carb.log_warn("No prims selected")
                return

            # Discover current prims
            current_reference_prims = {}
            for prim_path_str in current_selected_paths:
                # Validate path string before creating SdfPath
                if (
                    not prim_path_str
                    or not isinstance(prim_path_str, str)
                    or prim_path_str.strip() == ""
                ):
                    carb.log_warn(f"Skipping invalid path in apply: '{prim_path_str}'")
                    continue

                try:
                    # Import Sdf locally and create SdfPath properly
                    from pxr import Sdf

                    # Additional validation to prevent SdfPath warnings
                    clean_path = prim_path_str.strip()
                    if not clean_path or clean_path == "":
                        carb.log_warn(
                            f"Skipping empty path after cleaning in apply: '{prim_path_str}'"
                        )
                        continue

                    # Create SdfPath object explicitly
                    sdf_path = Sdf.Path(clean_path)

                    # Validate the SdfPath was created successfully
                    if not sdf_path or sdf_path.isEmpty:
                        carb.log_warn(
                            f"Failed to create valid SdfPath from: '{clean_path}' in apply"
                        )
                        continue

                    prim = current_stage.GetPrimAtPath(sdf_path)

                    if not prim.IsValid():
                        continue

                    has_payloads = prim.HasPayload()
                    if has_payloads:
                        original_payload = self._find_original_asset_path(
                            prim, "payload"
                        )
                        if original_payload:
                            current_reference_prims[prim_path_str] = {
                                "has_payloads": True,
                                "original_asset_paths": [
                                    original_payload["asset_path"]
                                ],
                                "prim_paths": [original_payload["prim_path"]],
                                "current_offset": (
                                    original_payload["layer_offset"].offset
                                    if original_payload["layer_offset"]
                                    else 0.0
                                ),
                            }

                except Exception as prim_error:
                    carb.log_error(
                        f"Error analyzing prim {prim_path_str}: {str(prim_error)}"
                    )
                    continue

            if not current_reference_prims:
                carb.log_warn("No references/payloads found")
                return

            # Apply offsets
            successful_count = 0
            for prim_path, ref_info in current_reference_prims.items():
                try:
                    current_offset = ref_info.get("current_offset", 0.0)
                    new_offset = current_offset + offset

                    if self._apply_payload_offset(prim_path, ref_info, new_offset):
                        successful_count += 1
                        carb.log_info(f"Applied offset to {prim_path}")

                except Exception as e:
                    carb.log_error(f"Error applying offset to {prim_path}: {str(e)}")

            carb.log_info(
                f"Applied offset to {successful_count}/{len(current_reference_prims)} prims"
            )

            # Clear cached selection
            self.reference_prims.clear()
            carb.log_info("Cleared cached selection - tool ready for new selections")

        except Exception as e:
            carb.log_error(f"Error applying offset: {str(e)}")

    def _apply_payload_offset(self, prim_path_str, ref_info, new_offset):
        try:
            from pxr import Sdf

            # Get fresh stage reference (important after save/reload)
            current_stage = omni.usd.get_context().get_stage()
            if not current_stage:
                carb.log_error("No stage available for payload offset")
                return False

            # Get edit target layer
            try:
                edit_target = current_stage.GetEditTarget()
                target_layer = edit_target.GetLayer()
            except Exception as edit_target_error:
                carb.log_info(
                    f"GetEditTarget() failed after save/reload: {str(edit_target_error)}"
                )
                # Fallback: Use the root layer (session layer or main layer)
                try:
                    target_layer = current_stage.GetSessionLayer()
                    if not target_layer:
                        target_layer = current_stage.GetRootLayer()
                    carb.log_info(f"Using fallback layer: {target_layer.identifier}")
                except Exception as fallback_error:
                    carb.log_error(
                        f"Fallback layer access also failed: {str(fallback_error)}"
                    )
                    return False

            # Validate path string before creating SdfPath
            if (
                not prim_path_str
                or not isinstance(prim_path_str, str)
                or prim_path_str.strip() == ""
            ):
                carb.log_error(f"Invalid prim path string: '{prim_path_str}'")
                return False

            clean_path = prim_path_str.strip()
            if not clean_path or clean_path == "":
                carb.log_error(f"Empty prim path after cleaning: '{prim_path_str}'")
                return False

            # Get or create prim spec
            sdf_path = Sdf.Path(clean_path)
            prim_spec = target_layer.GetPrimAtPath(sdf_path)
            if not prim_spec:
                prim_spec = Sdf.CreatePrimInLayer(target_layer, sdf_path)

            # Clear existing payload edits
            if prim_spec.payloadList:
                prim_spec.payloadList.ClearEdits()

            # Use original asset path
            original_asset_path = ref_info["original_asset_paths"][0]
            original_prim_path = (
                ref_info["prim_paths"][0] if ref_info["prim_paths"] else ""
            )

            # Create layer offset
            layer_offset = Sdf.LayerOffset(new_offset)

            # Create new payload with original path + LayerOffset
            # Validate prim path to prevent SdfPath warnings
            if original_prim_path and original_prim_path.strip():
                validated_prim_path = original_prim_path.strip()
            else:
                validated_prim_path = ""  # Empty string is valid for USD default prim

            carb.log_info(
                f"Creating payload: asset='{original_asset_path}', prim='{validated_prim_path}', offset={layer_offset}"
            )
            new_payload = Sdf.Payload(
                original_asset_path, validated_prim_path, layer_offset
            )

            # Add to payload list
            if not prim_spec.payloadList:
                prim_spec.payloadList = Sdf.PayloadListOp()

            prim_spec.payloadList.explicitItems.append(new_payload)

            carb.log_info(
                f"Applied payload with original path: '{original_asset_path}'"
            )
            return True

        except Exception as e:
            carb.log_error(f"Failed to apply payload offset: {str(e)}")
            return False

    def _reset_animation(self):
        try:
            carb.log_info("Resetting animation to original state...")

            # Get fresh stage reference (important after save/reload)
            current_stage = omni.usd.get_context().get_stage()
            if not current_stage:
                carb.log_error("No stage available for reset")
                return

            # Get current selection
            current_selected_paths = self.selection.get_selected_prim_paths()
            if not current_selected_paths:
                carb.log_warn("No prims selected for reset")
                return

            successful_count = 0
            total_count = 0

            for prim_path_str in current_selected_paths:
                # Validate path string before creating SdfPath
                if (
                    not prim_path_str
                    or not isinstance(prim_path_str, str)
                    or prim_path_str.strip() == ""
                ):
                    carb.log_warn(f"Skipping invalid path in reset: '{prim_path_str}'")
                    continue

                total_count += 1

                try:
                    # Import Sdf locally and create SdfPath properly
                    from pxr import Sdf

                    # Additional validation to prevent SdfPath warnings
                    clean_path = prim_path_str.strip()
                    if not clean_path or clean_path == "":
                        carb.log_warn(
                            f"Skipping empty path after cleaning in reset: '{prim_path_str}'"
                        )
                        continue

                    # Get edit target layer (where our LayerOffset edits are stored)
                    try:
                        edit_target = current_stage.GetEditTarget()
                        target_layer = edit_target.GetLayer()
                    except Exception as edit_target_error:
                        carb.log_info(
                            f"GetEditTarget() failed after save/reload: {str(edit_target_error)}"
                        )
                        # Fallback: Use the root layer (session layer or main layer)
                        try:
                            target_layer = current_stage.GetSessionLayer()
                            if not target_layer:
                                target_layer = current_stage.GetRootLayer()
                            carb.log_info(
                                f"Using fallback layer: {target_layer.identifier}"
                            )
                        except Exception as fallback_error:
                            carb.log_error(
                                f"Fallback layer access also failed: {str(fallback_error)}"
                            )
                            continue

                    # Create SdfPath object explicitly
                    sdf_path = Sdf.Path(clean_path)

                    # Validate the SdfPath was created successfully
                    if not sdf_path or sdf_path.isEmpty:
                        carb.log_warn(
                            f"Failed to create valid SdfPath from: '{clean_path}' in reset"
                        )
                        continue

                    # Get prim spec in edit target layer
                    prim_spec = target_layer.GetPrimAtPath(sdf_path)

                    if not prim_spec:
                        carb.log_info(
                            f"No prim spec found in edit target layer for {prim_path_str} - nothing to reset"
                        )
                        successful_count += 1  # Nothing to reset is success
                        continue

                    carb.log_info(f"Resetting {prim_path_str}...")

                    # Reset payload by restoring original payload without LayerOffset
                    reset_success = False
                    if prim_spec.payloadList:
                        carb.log_info(f"Found payload list in edit target layer")

                        # Get the current payload info to extract original asset path
                        current_payloads = (
                            list(prim_spec.payloadList.explicitItems)
                            if prim_spec.payloadList.explicitItems
                            else []
                        )

                        if current_payloads:
                            # Extract original asset path from current payload (removing LayerOffset)
                            current_payload = current_payloads[0]
                            original_asset_path = str(current_payload.assetPath)
                            original_prim_path = (
                                str(current_payload.primPath)
                                if current_payload.primPath
                                else ""
                            )

                            carb.log_info(
                                f"Restoring original payload: '{original_asset_path}' without LayerOffset"
                            )

                            # Clear existing payloads and add back without LayerOffset
                            prim_spec.payloadList.ClearEdits()

                            # Create new payload without LayerOffset
                            # Validate prim path to prevent SdfPath warnings
                            if original_prim_path and original_prim_path.strip():
                                validated_prim_path = original_prim_path.strip()
                            else:
                                validated_prim_path = (
                                    ""  # Empty string is valid for USD default prim
                                )

                            carb.log_info(
                                f"Creating reset payload: asset='{original_asset_path}', prim='{validated_prim_path}'"
                            )
                            reset_payload = Sdf.Payload(
                                original_asset_path, validated_prim_path
                            )  # No LayerOffset!

                            # Add back to payload list
                            if not prim_spec.payloadList:
                                prim_spec.payloadList = Sdf.PayloadListOp()
                            prim_spec.payloadList.explicitItems.append(reset_payload)

                            carb.log_info(
                                f"Restored original payload without LayerOffset"
                            )
                            reset_success = True
                        else:
                            carb.log_info(
                                f"No payloads found in explicitItems - just clearing edits"
                            )
                            prim_spec.payloadList.ClearEdits()
                            reset_success = True

                    # Remove reference deltas from edit target layer
                    if prim_spec.referenceList:
                        carb.log_info(
                            f"Clearing reference deltas from edit target layer"
                        )
                        prim_spec.referenceList.ClearEdits()
                        reset_success = True

                    # Clean up: If prim spec now has no meaningful data, remove it entirely
                    if reset_success:
                        # Check if the prim spec is now empty (no payloads, references, or other meaningful data)
                        has_meaningful_data = False

                        # Check for payloads
                        if (
                            prim_spec.payloadList
                            and prim_spec.payloadList.explicitItems
                        ):
                            has_meaningful_data = True

                        # Check for references
                        if (
                            prim_spec.referenceList
                            and prim_spec.referenceList.explicitItems
                        ):
                            has_meaningful_data = True

                        # Check for other attributes (properties, metadata, etc.)
                        if (
                            prim_spec.properties
                            or prim_spec.attributes
                            or prim_spec.relationships
                        ):
                            has_meaningful_data = True

                        # Check for type name or other specs
                        if hasattr(prim_spec, "typeName") and prim_spec.typeName:
                            has_meaningful_data = True

                        if not has_meaningful_data:
                            carb.log_info(
                                f"Prim spec now empty - removing entirely to clean up USD"
                            )
                            target_layer.RemoveSpec(sdf_path)

                        successful_count += 1
                        carb.log_info(f"Reset animation for {prim_path_str}")
                    else:
                        carb.log_info(f"No LayerOffset edits found for {prim_path_str}")
                        successful_count += 1  # Nothing to reset is success

                except Exception as prim_error:
                    carb.log_error(
                        f"Error resetting {prim_path_str}: {str(prim_error)}"
                    )

            if successful_count > 0:
                carb.log_info(
                    f"Reset animation for {successful_count}/{total_count} prims"
                )
                # Clear cached selection
                self.reference_prims.clear()
                carb.log_info("Cleared cached selection - ready for new operations")
            else:
                carb.log_error(f"Failed to reset animation for any prims")

        except Exception as e:
            carb.log_error(f"Error in reset animation: {str(e)}")


def main():
    try:
        carb.log_info(
            "Starting Reference Time Offset Editor with Relative Path Preservation..."
        )

        editor = ReferenceTimeOffsetEditor()
        editor.create_ui()

        carb.log_info("Reference Time Offset Editor ready!")
        carb.log_info("Instructions:")
        carb.log_info("   1. Select prim(s) with references/payloads in the viewport")
        carb.log_info("   2. Set desired time offset using +/- buttons or direct input")
        carb.log_info("   3. Click 'Apply Offset' - preserves original relative paths!")
        carb.log_info("   4. Use 'Reset Animation' to restore original timing")
        carb.log_info("   5. 'Apply Offset' always uses current viewport selection")

        return editor

    except Exception as e:
        carb.log_error(f"Failed to start Reference Time Offset Editor: {str(e)}")
        return None


if __name__ == "__main__":
    main()
else:
    main()
