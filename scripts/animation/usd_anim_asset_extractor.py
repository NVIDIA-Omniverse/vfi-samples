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
USD Asset Refactor - Split asset into Model + Animation layers
Extract static model (with wrapper prim) and animation data into separate layers,
with optional replacement of the original prim with references.

Three independent features (each controlled by its own flag):
1. extract_model: Extract model layer (creates file, doesn't modify stage)
2. extract_animation: Extract animation layer (creates file, doesn't modify stage)
3. replace_in_stage: Replace original prim with references (modifies stage)

Key improvement: Static model adds a wrapper root prim to ensure animation timesamples
always override default values regardless of reference order.
"""

from pxr import Usd, UsdGeom, Sdf
import omni.usd
import omni.client
import os


# ============================================
# CONFIGURATION: Set default behavior for three independent features
# ============================================
# extract_model: Extract model layer (creates file, doesn't modify stage)
# extract_animation: Extract animation layer (creates file, doesn't modify stage)
# replace_in_stage: Replace original prim with references (modifies stage)

DEFAULT_EXTRACT_MODEL = (
    True  # <-- Copy the static model prim/attributes into another USD layer
)
DEFAULT_EXTRACT_ANIMATION = (
    True  # <-- Copy the animated prim/attributes into another USD layer
)
DEFAULT_REPLACE_IN_STAGE = (
    False  # <-- Replace the original prim with the two USD layers in payload/reference
)

REMOTE_URI_PREFIXES = tuple(
    f"{scheme}://" for scheme in ("omniverse", "s3", "http", "https")
)
# ============================================


def get_dir_from_url(url):
    """
    Get directory from URL by removing the filename part.
    Works with all URL types (omniverse://, s3://, http://, local paths, etc.)
    Simple string manipulation without manual URL reconstruction.
    """
    if not url:
        return url

    # Remove trailing slashes first
    url = url.rstrip("/")

    # Find the last slash
    last_slash = url.rfind("/")

    # For URLs with scheme (e.g., omniverse://server/path/file.usd)
    # Make sure we don't cut into the scheme part
    scheme_end = url.find("://")
    if scheme_end >= 0:
        # Ensure last_slash is after the scheme
        if last_slash > scheme_end + 2:
            return url[:last_slash]
        else:
            # No path component, return as-is
            return url
    else:
        # Raw path (no scheme)
        if last_slash >= 0:
            return url[:last_slash]
        else:
            # No slash found, return current directory
            return "."


def join_url(base, *parts):
    """
    Join URL parts using omni.client.combine_urls.
    Works with all URL types and local paths.
    """
    # Ensure base ends with '/' so combine_urls treats it as a directory
    if base and not base.endswith("/"):
        base = base + "/"

    result = base
    for part in parts:
        result = omni.client.combine_urls(result, part)
    return result


def _extract_model_layer_with_wrapper(
    stage, prim_path, output_dir, output_name, verbose=False
):
    """
    Extract static model (non-animated attributes) to a separate layer with a wrapper root prim.
    The wrapper ensures animation timesamples always override default values.
    Returns the path to the created model file.
    """
    selected_prim = stage.GetPrimAtPath(prim_path)
    if not selected_prim.IsValid():
        print(f"Error: Invalid prim: {prim_path}")
        return None

    # Determine output filename
    model_name = output_name if output_name else selected_prim.GetPath().name
    if not model_name.endswith(".model"):
        model_name = f"{model_name}.model"

    # Build full path using omni.client.combine_urls
    model_file = join_url(output_dir, f"{model_name}.usda")

    if verbose:
        print(f"   Creating model layer with wrapper: {model_file}")

    # Create anonymous layer in memory (not on disk) to avoid registry cache issues
    import uuid

    temp_identifier = f"anon:temp_model_{uuid.uuid4().hex[:8]}.usda"
    model_layer = Sdf.Layer.CreateAnonymous(temp_identifier)
    if not model_layer:
        print(f"Error: Failed to create model layer: {model_file}")
        return None

    # Copy stage metadata
    temp_stage = Usd.Stage.Open(model_layer)
    axis = UsdGeom.GetStageUpAxis(stage)
    UsdGeom.SetStageUpAxis(temp_stage, axis)

    try:
        meters_per_unit = stage.GetMetadata("metersPerUnit")
        if meters_per_unit is not None:
            temp_stage.SetMetadata("metersPerUnit", meters_per_unit)
    except:
        pass

    temp_stage.Save()
    del temp_stage

    # Find the introducing layer for this prim
    prim_stack = selected_prim.GetPrimStack()

    if prim_stack:
        introducing_spec = prim_stack[-1]
        introducing_layer = introducing_spec.layer
        source_path_in_layer = introducing_spec.path

        if verbose:
            print(f"   Prim has {len(prim_stack)} layer specs")
            print(
                f"   Introducing layer: {introducing_layer.GetDisplayName() or introducing_layer.identifier}"
            )
            print(f"   Path in introducing layer: {source_path_in_layer}")
    else:
        if verbose:
            print(f"   Using root layer (no prim stack found)")
        introducing_layer = stage.GetRootLayer()
        source_path_in_layer = Sdf.Path(prim_path)

    # Flatten and copy from introducing layer
    mask = [source_path_in_layer]
    masked_stage = Usd.Stage.OpenMasked(
        introducing_layer, Usd.StagePopulationMask(mask)
    )
    if not masked_stage:
        print("Error: Failed to create masked stage for model")
        return None

    source_flattened_layer = masked_stage.Flatten()
    if not source_flattened_layer:
        print("Error: Failed to flatten masked stage for model")
        return None

    # Create wrapper root prim
    wrapper_prim_name = "ModelRoot"
    wrapper_path = Sdf.Path(f"/{wrapper_prim_name}")

    # Create wrapper prim as Xform
    wrapper_spec = Sdf.PrimSpec(
        model_layer, wrapper_prim_name, Sdf.SpecifierDef, "Xform"
    )

    # Copy prim under the wrapper
    source_path = source_path_in_layer
    original_prim_name = selected_prim.GetPath().name
    target_path = Sdf.Path(f"/{wrapper_prim_name}/{original_prim_name}")

    Sdf.CreatePrimInLayer(model_layer, target_path)
    Sdf.CopySpec(source_flattened_layer, source_path, model_layer, target_path)

    # Set wrapper as default prim
    model_layer.defaultPrim = wrapper_prim_name

    # Clear timeSamples recursively
    def clear_timesamples_recursive(prim_spec):
        for attr_spec in prim_spec.attributes:
            if attr_spec.HasInfo("timeSamples"):
                attr_spec.ClearInfo("timeSamples")
        for child_spec in prim_spec.nameChildren:
            clear_timesamples_recursive(child_spec)

    with Sdf.ChangeBlock():
        for root_prim_spec in model_layer.rootPrims:
            clear_timesamples_recursive(root_prim_spec)

    # Export layer - use omni.client for ALL writes (local and remote)
    layer_content = model_layer.ExportToString()
    if not layer_content:
        print(f"Error: Failed to export model layer to string")
        return None

    content = layer_content.encode("utf-8")
    result = omni.client.write_file(model_file, content)

    if result != omni.client.Result.OK:
        print(f"Error: Failed to write model layer: {model_file}, error code: {result}")
        return None

    if verbose:
        print(f"   Model layer created with wrapper: {os.path.basename(model_file)}")
        print(f"   Wrapper prim: /{wrapper_prim_name}")
        print(f"   Original prim: /{wrapper_prim_name}/{original_prim_name}")

    return model_file


def _extract_animation_layer(stage, prim_path, output_dir, output_name, verbose=False):
    """
    Extract animation (timeSamples only) to a separate layer.
    No wrapper prim - keeps original structure.
    Returns the path to the created animation file, or None if no animation found.
    """
    selected_prim = stage.GetPrimAtPath(prim_path)
    if not selected_prim.IsValid():
        print(f"Error: Invalid prim: {prim_path}")
        return None

    # Determine output filename
    anim_name = output_name if output_name else selected_prim.GetPath().name
    if not anim_name.endswith(".anim"):
        anim_name = f"{anim_name}.anim"

    # Build full path using omni.client.combine_urls
    animation_file = join_url(output_dir, f"{anim_name}.usda")

    if verbose:
        print(f"   Creating animation layer: {animation_file}")

    # Create anonymous layer in memory (not on disk) to avoid registry cache issues
    import uuid

    temp_identifier = f"anon:temp_anim_{uuid.uuid4().hex[:8]}.usda"
    animation_layer = Sdf.Layer.CreateAnonymous(temp_identifier)
    if not animation_layer:
        print(f"Error: Failed to create animation layer: {animation_file}")
        return None

    # Copy stage metadata
    temp_stage = Usd.Stage.Open(animation_layer)
    axis = UsdGeom.GetStageUpAxis(stage)
    UsdGeom.SetStageUpAxis(temp_stage, axis)

    try:
        meters_per_unit = stage.GetMetadata("metersPerUnit")
        if meters_per_unit is not None:
            temp_stage.SetMetadata("metersPerUnit", meters_per_unit)
    except:
        pass

    # Copy timing metadata (fps only - time codes will be set later based on actual data)
    temp_stage.SetFramesPerSecond(stage.GetFramesPerSecond())
    temp_stage.SetTimeCodesPerSecond(stage.GetTimeCodesPerSecond())
    # NOTE: startTimeCode and endTimeCode will be set after scanning actual animation data

    temp_stage.Save()
    del temp_stage

    # Find the introducing layer
    prim_stack = selected_prim.GetPrimStack()

    if prim_stack:
        introducing_spec = prim_stack[-1]
        introducing_layer = introducing_spec.layer
        source_path_in_layer = introducing_spec.path

        if verbose:
            print(f"   Prim has {len(prim_stack)} layer specs")
            print(
                f"   Introducing layer: {introducing_layer.GetDisplayName() or introducing_layer.identifier}"
            )
            print(f"   Path in introducing layer: {source_path_in_layer}")
    else:
        if verbose:
            print(f"   Using root layer (no prim stack found)")
        introducing_layer = stage.GetRootLayer()
        source_path_in_layer = Sdf.Path(prim_path)

    # Flatten and copy
    mask = [source_path_in_layer]
    masked_stage = Usd.Stage.OpenMasked(
        introducing_layer, Usd.StagePopulationMask(mask)
    )
    if not masked_stage:
        print("Error: Failed to create masked stage for animation")
        return None

    source_flattened_layer = masked_stage.Flatten()
    if not source_flattened_layer:
        print("Error: Failed to flatten masked stage for animation")
        return None

    # Copy prim WITHOUT wrapper
    # Use "root" as the standard root prim name so animation clips match model asset hierarchy
    source_path = source_path_in_layer
    root_prim_name = "root"  # Standardized name to match model asset hierarchy
    root_target_path = f"/{root_prim_name}"
    target_path = Sdf.Path(root_target_path)

    Sdf.CreatePrimInLayer(animation_layer, target_path)
    Sdf.CopySpec(source_flattened_layer, source_path, animation_layer, target_path)

    # Set default prim to "root" - this ensures value clips can bind correctly
    animation_layer.defaultPrim = root_prim_name

    # Remove attributes without timeSamples
    has_animation = False
    prims_to_remove = []

    def process_prim_for_animation(prim_spec):
        nonlocal has_animation, prims_to_remove
        prim_has_animation = False

        attrs_with_timesamples = set()
        has_xformop_animation = False

        attr_metadata_to_remove = ["customData", "documentation", "comment"]

        for attr_spec in prim_spec.attributes:
            attr_name = attr_spec.name
            if attr_spec.HasInfo("timeSamples"):
                attrs_with_timesamples.add(attr_name)
                has_animation = True
                prim_has_animation = True
                if attr_name.startswith("xformOp:"):
                    has_xformop_animation = True

                for metadata_key in attr_metadata_to_remove:
                    if attr_spec.HasInfo(metadata_key):
                        attr_spec.ClearInfo(metadata_key)

        attrs_to_remove = []
        for attr_spec in prim_spec.attributes:
            attr_name = attr_spec.name

            if attr_name not in attrs_with_timesamples:
                if attr_name == "xformOpOrder" and has_xformop_animation:
                    for metadata_key in attr_metadata_to_remove:
                        if attr_spec.HasInfo(metadata_key):
                            attr_spec.ClearInfo(metadata_key)
                    continue

                attrs_to_remove.append(attr_spec)

        for attr_spec in attrs_to_remove:
            prim_spec.RemoveProperty(attr_spec)

        rels_to_remove = list(prim_spec.relationships)
        for rel_spec in rels_to_remove:
            prim_spec.RemoveProperty(rel_spec)

        if prim_spec.variantSetNameList:
            variant_sets_to_remove = (
                prim_spec.variantSetNameList.GetAddedOrExplicitItems()
            )
            for variant_set_name in variant_sets_to_remove:
                prim_spec.RemoveVariantSet(variant_set_name)

        metadata_to_remove = [
            "customData",
            "documentation",
            "comment",
            "assetInfo",
            "apiSchemas",
            "kind",
        ]
        for metadata_key in metadata_to_remove:
            if prim_spec.HasInfo(metadata_key):
                prim_spec.ClearInfo(metadata_key)

        for child_spec in prim_spec.nameChildren:
            child_has_animation = process_prim_for_animation(child_spec)
            if child_has_animation:
                prim_has_animation = True
            else:
                prims_to_remove.append(child_spec.path)

        return prim_has_animation

    with Sdf.ChangeBlock():
        for root_prim_spec in animation_layer.rootPrims:
            process_prim_for_animation(root_prim_spec)

        for prim_path in prims_to_remove:
            parent_path = prim_path.GetParentPath()
            prim_name = prim_path.name

            if parent_path == Sdf.Path.absoluteRootPath:
                del animation_layer.rootPrims[prim_name]
            else:
                parent_spec = animation_layer.GetPrimAtPath(parent_path)
                if parent_spec:
                    del parent_spec.nameChildren[prim_name]

    if not has_animation:
        if verbose:
            print(f"   No animation data found, animation layer not created")
        return None

    # Scan all time samples to find the actual animation time range
    # Exclude 'visibility' attributes as they often have a single sample at frame 0
    min_time = float("inf")
    max_time = float("-inf")

    def scan_time_samples(prim_spec):
        nonlocal min_time, max_time
        for attr_spec in prim_spec.attributes:
            # Skip visibility - it often has a single sample at frame 0 that skews the range
            if attr_spec.name == "visibility":
                continue
            if attr_spec.HasInfo("timeSamples"):
                time_samples = attr_spec.GetInfo("timeSamples")
                if time_samples:
                    times = list(time_samples.keys())
                    if times:
                        min_time = min(min_time, min(times))
                        max_time = max(max_time, max(times))
        for child_spec in prim_spec.nameChildren:
            scan_time_samples(child_spec)

    for root_prim_spec in animation_layer.rootPrims:
        scan_time_samples(root_prim_spec)

    # Set the correct startTimeCode and endTimeCode based on actual animation data
    if min_time != float("inf") and max_time != float("-inf"):
        animation_layer.startTimeCode = min_time
        animation_layer.endTimeCode = max_time
        if verbose:
            print(f"   Animation time range: {min_time} - {max_time}")
    else:
        # Fallback to stage time codes if no time samples found (shouldn't happen)
        animation_layer.startTimeCode = stage.GetStartTimeCode()
        animation_layer.endTimeCode = stage.GetEndTimeCode()

    # Export layer - use omni.client for ALL writes (local and remote)
    layer_content = animation_layer.ExportToString()
    if not layer_content:
        print(f"Error: Failed to export animation layer to string")
        return None

    content = layer_content.encode("utf-8")
    result = omni.client.write_file(animation_file, content)

    if result != omni.client.Result.OK:
        print(
            f"Error: Failed to write animation layer: {animation_file}, error code: {result}"
        )
        return None

    if verbose:
        print(f"   Animation layer created: {os.path.basename(animation_file)}")

    return animation_file


def _replace_in_stage(
    stage, prim_path, model_file, animation_file, use_payload=True, verbose=False
):
    """
    Replace the original prim in stage with references to model and animation layers.
    This modifies the introducing layer of the stage.

    Args:
        stage: USD stage
        prim_path: Path to prim to replace
        model_file: Path to model layer file
        animation_file: Path to animation layer file (can be None)
        use_payload: If True, use payloads instead of references
        verbose: If True, print detailed processing information

    Returns:
        True if successful, False otherwise
    """
    selected_prim = stage.GetPrimAtPath(prim_path)
    if not selected_prim.IsValid():
        print(f"Error: Invalid prim: {prim_path}")
        return False

    prim_name = selected_prim.GetPath().name
    prim_stack = selected_prim.GetPrimStack()

    if not prim_stack:
        print("Error: No prim stack found, cannot replace in introducing layer")
        return False

    introducing_spec = prim_stack[-1]
    introducing_layer = introducing_spec.layer
    source_path_in_layer = introducing_spec.path

    print(f"   Introducing layer: {introducing_layer.identifier}")
    print(f"   Path in layer: {source_path_in_layer}")

    if not introducing_layer.permissionToEdit:
        print(f"Error: Introducing layer is not writable!")
        return False

    # Get parent path
    parent_path = source_path_in_layer.GetParentPath()
    prim_name_in_layer = source_path_in_layer.name

    # Get output directory from model_file
    output_dir = get_dir_from_url(model_file)

    with Sdf.ChangeBlock():
        # Step 1: Find parent prim spec
        if parent_path == Sdf.Path.absoluteRootPath:
            parent_spec = introducing_layer.pseudoRoot
        else:
            parent_spec = introducing_layer.GetPrimAtPath(parent_path)
            if not parent_spec:
                print(f"Error: Parent spec not found at {parent_path}")
                return False

        # Step 2: Remove original prim spec
        if parent_path == Sdf.Path.absoluteRootPath:
            if prim_name_in_layer in introducing_layer.rootPrims:
                del introducing_layer.rootPrims[prim_name_in_layer]
        else:
            if prim_name_in_layer in parent_spec.nameChildren:
                del parent_spec.nameChildren[prim_name_in_layer]

        # Calculate reference paths
        introducing_layer_path = (
            introducing_layer.realPath or introducing_layer.identifier
        )
        layer_dir = (
            get_dir_from_url(introducing_layer_path) if introducing_layer_path else None
        )

        # Check if introducing layer is on Nucleus, S3, or local
        introducing_broken = (
            omni.client.break_url(introducing_layer_path)
            if introducing_layer_path
            else None
        )
        introducing_is_remote = introducing_broken and introducing_broken.scheme in [
            "omniverse",
            "s3",
            "http",
            "https",
        ]
        introducing_is_local = not introducing_is_remote

        # Check if output is on Nucleus, S3, or local
        output_broken = omni.client.break_url(output_dir)
        output_is_local = output_broken.is_raw or output_broken.scheme == "file"
        output_is_remote = not output_is_local

        # Determine how to handle paths
        if introducing_is_remote and output_is_local:
            # Remote stage referencing local files - must use absolute paths with file:// prefix
            model_ref_path = omni.client.make_file_url_if_possible(model_file)
            anim_ref_path = (
                omni.client.make_file_url_if_possible(animation_file)
                if animation_file
                else None
            )
        elif introducing_is_remote and output_is_remote:
            # Both remote - use absolute remote paths
            model_ref_path = model_file
            anim_ref_path = animation_file
        elif introducing_is_local and output_is_local:
            # Both local - try to use relative paths for portability
            try:
                model_ref_path = os.path.relpath(model_file, layer_dir)
                anim_ref_path = (
                    os.path.relpath(animation_file, layer_dir)
                    if animation_file
                    else None
                )
            except ValueError:
                # Different drives on Windows, use absolute paths with file:// prefix
                model_ref_path = omni.client.make_file_url_if_possible(model_file)
                anim_ref_path = (
                    omni.client.make_file_url_if_possible(animation_file)
                    if animation_file
                    else None
                )
        else:
            # Local stage referencing remote files - use absolute remote paths
            model_ref_path = model_file
            anim_ref_path = animation_file

        # Step 3: Add model reference to PARENT prim
        # This will bring in the wrapper's content, making the original prim reappear
        if use_payload:
            # Use the model's defaultPrim (ModelRoot)
            model_payload = Sdf.Payload(model_ref_path)
            if not hasattr(parent_spec, "payloadList"):
                print(f"Error: Parent spec does not support payloads")
                return False
            parent_spec.payloadList.prependedItems.append(model_payload)
        else:
            # Use the model's defaultPrim (ModelRoot)
            model_ref = Sdf.Reference(model_ref_path)
            if not hasattr(parent_spec, "referenceList"):
                print(f"Error: Parent spec does not support references")
                return False
            parent_spec.referenceList.prependedItems.append(model_ref)

        if verbose:
            print(
                f"   Step 1: Added model {'payload' if use_payload else 'reference'} to parent prim: {parent_path}"
            )
            print(f"     Reference path: {model_ref_path}")
            print(f"     This brings in ModelRoot with {prim_name_in_layer} as child")

        # Step 4: Add animation reference to the re-appeared original prim
        if animation_file and anim_ref_path:
            # The original prim should now exist again due to the model reference
            # Get or create the prim spec for adding animation reference
            reappeared_prim_spec = introducing_layer.GetPrimAtPath(source_path_in_layer)
            if not reappeared_prim_spec:
                # Create a new prim spec at the original location
                if parent_path == Sdf.Path.absoluteRootPath:
                    reappeared_prim_spec = Sdf.PrimSpec(
                        introducing_layer, prim_name_in_layer, Sdf.SpecifierOver
                    )
                else:
                    reappeared_prim_spec = Sdf.PrimSpec(
                        parent_spec, prim_name_in_layer, Sdf.SpecifierOver
                    )

            # Add animation reference to the re-appeared prim
            if use_payload:
                # Use defaultPrim from animation layer
                anim_payload = Sdf.Payload(anim_ref_path)
                reappeared_prim_spec.payloadList.prependedItems.append(anim_payload)
            else:
                # Use defaultPrim from animation layer
                anim_ref = Sdf.Reference(anim_ref_path)
                reappeared_prim_spec.referenceList.prependedItems.append(anim_ref)

            if verbose:
                print(
                    f"   Step 2: Added animation {'payload' if use_payload else 'reference'} to re-appeared prim: {source_path_in_layer}"
                )
                print(f"     Reference path: {anim_ref_path}")
                print(f"     Using defaultPrim from animation layer")

    print(f"\n   ✓ Replacement complete")
    print(f"     Model provides: default values (through wrapper)")
    print(f"     Animation provides: timesamples (overrides defaults)")

    return True


def refactor_asset_with_priority(
    prim_path=None,
    output_path=None,
    output_name=None,
    extract_model=True,
    extract_animation=True,
    replace_in_stage=True,
    use_payload=True,
    verbose=False,
):
    """
    Refactor asset by splitting it into model (with wrapper) and animation layers.
    The wrapper ensures animation timesamples always override default values.

    Args:
        prim_path: Path to prim to process (required, must not be None)
        output_path: Full output path for directory (can be local or Nucleus URL)
                    If None, defaults to current file directory
        output_name: Base name for output files without extension (defaults to prim name)
        extract_model: If True, extract model layer (only creates file, doesn't modify stage)
        extract_animation: If True, extract animation layer (only creates file, doesn't modify stage)
        replace_in_stage: If True, replace prim with references to split layers (modifies stage)
        use_payload: If True, use payloads instead of references when replacing
        verbose: If True, print detailed processing information

    Returns:
        True if successful, False otherwise
    """
    # Get context and stage
    context = omni.usd.get_context()
    if not context or not context.get_stage():
        print("Error: Cannot get USD stage")
        return False

    stage = context.get_stage()

    # Require prim_path
    if prim_path is None:
        print("Error: prim_path is required")
        return False

    # Get prim
    selected_prim = stage.GetPrimAtPath(prim_path)
    if not selected_prim.IsValid():
        print(f"Error: Invalid prim: {prim_path}")
        return False

    print(f"{'='*60}")
    print(f"Refactoring asset: {prim_path}")
    print(f"{'='*60}")

    # Determine output directory
    if output_path is None:
        current_layer = stage.GetRootLayer()
        stage_path = current_layer.identifier if current_layer.identifier else None

        if stage_path:
            # Use omni.client to get directory from any URL type
            output_dir = get_dir_from_url(stage_path)
        else:
            import tempfile

            output_dir = tempfile.gettempdir()
    else:
        output_dir = output_path.rstrip("/\\")

    # Ensure output directory exists for local paths only
    broken_url = omni.client.break_url(output_dir)
    if broken_url.is_raw or broken_url.scheme == "file":
        # Local path - ensure directory exists
        local_dir = output_dir
        if broken_url.scheme == "file":
            # Convert file:// URL to local path
            local_dir = broken_url.path
            if (
                os.name == "nt"
                and local_dir.startswith("/")
                and len(local_dir) >= 3
                and local_dir[2] == ":"
            ):
                local_dir = local_dir[1:]

        if not os.path.exists(local_dir):
            try:
                os.makedirs(local_dir)
                if verbose:
                    print(f"Created output directory: {local_dir}")
            except Exception as e:
                print(f"Error: Cannot create output directory: {e}")
                return False

    if verbose:
        print(f"Output directory: {output_dir}")

    # Initialize variables to track what was created
    model_file = None
    animation_file = None

    # Step 1: Extract model layer WITH WRAPPER (if enabled)
    print(f"\n=== Phase 1: Extract model layer? {extract_model} ===")
    if extract_model:
        print("   WILL EXTRACT: Creating model layer with wrapper")
        print("   Note: Only creates new file, does NOT modify original stage")
        model_file = _extract_model_layer_with_wrapper(
            stage, prim_path, output_dir, output_name, verbose
        )
        if not model_file:
            print("Error: Failed to extract model layer")
            return False
    else:
        print("   SKIP: Not extracting model layer (extract_model=False)")

    # Step 2: Extract animation layer (NO WRAPPER) (if enabled)
    print(f"\n=== Phase 2: Extract animation layer? {extract_animation} ===")
    if extract_animation:
        print("   WILL EXTRACT: Creating animation layer")
        print("   Note: Only creates new file, does NOT modify original stage")
        animation_file = _extract_animation_layer(
            stage, prim_path, output_dir, output_name, verbose
        )
        if animation_file:
            print(f"   Animation layer extracted successfully")
        else:
            print(f"   No animation data found or extraction skipped")
    else:
        print("   SKIP: Not extracting animation layer (extract_animation=False)")

    # Step 3: Replace original prim if requested
    print(f"\n=== Phase 3: Replace in stage? {replace_in_stage} ===")
    if replace_in_stage:
        if not model_file:
            print("   ERROR: Cannot replace in stage without model file")
            print("   Please enable extract_model=True to create model file first")
            return False

        print("   WILL MODIFY: Replacing prim with references")
        print("   Model reference: on parent prim (with wrapper)")
        if animation_file:
            print("   Animation reference: on original prim path")
        else:
            print("   Animation reference: skipped (no animation file)")

        success = _replace_in_stage(
            stage, prim_path, model_file, animation_file, use_payload, verbose
        )
        if not success:
            print("Error: Failed to replace prim in stage")
            return False
    else:
        print("   SKIP: Not modifying the original stage (replace_in_stage=False)")
        print("   Original prim remains unchanged")

    # Summary
    print(f"\n{'='*60}")
    print(f"Asset refactoring complete!")
    print(f"{'='*60}")

    # Determine location type using omni.client
    broken_url = omni.client.break_url(output_dir)
    if broken_url.is_raw or broken_url.scheme == "file":
        print(f"  Location: Local file system")
    else:
        print(f"  Location: Remote ({broken_url.scheme}://)")

    # Report what was done
    print(f"\n  Operations performed:")
    if extract_model and model_file:
        print(
            f"    ✓ Model layer extracted: {os.path.basename(model_file)} (with wrapper)"
        )
    elif extract_model:
        print(f"    ✗ Model layer: Extraction attempted but failed")
    else:
        print(f"    - Model layer: Not extracted (extract_model=False)")

    if extract_animation and animation_file:
        print(
            f"    ✓ Animation layer extracted: {os.path.basename(animation_file)} (no wrapper)"
        )
    elif extract_animation:
        print(f"    - Animation layer: No animation data found")
    else:
        print(f"    - Animation layer: Not extracted (extract_animation=False)")

    if replace_in_stage:
        composition_type = "payloads" if use_payload else "references"
        print(f"    ✓ Original prim replaced with {composition_type}")
        print(
            f"      Solution: Model wrapper ensures animation timesamples always override defaults"
        )
    else:
        print(f"    - Original prim: Unchanged (replace_in_stage=False)")

    print(f"{'='*60}")

    return True


# Main execution
if __name__ == "__main__":
    context = omni.usd.get_context()
    if not context or not context.get_stage():
        print("Error: Cannot get USD stage")
    else:
        stage = context.get_stage()
        selection = context.get_selection()
        selected_paths = selection.get_selected_prim_paths()

        if not selected_paths:
            print("No prims selected. Please select a prim first.")
        else:
            # Import file picker dialog
            try:
                from omni.kit.window.filepicker import FilePickerDialog
                from omni.kit.window.popup_dialog import MessageDialog
                import asyncio

                def on_folder_selected(filename: str, dirname: str):
                    """Handle folder selection from dialog"""

                    async def process_async(dialog_ref):
                        # Ensure omni.client is imported for async operations
                        import omni.client

                        output_path = dirname if dirname else None
                        print(f"Output folder selected: {output_path}")

                        # Try to hide dialog early if no async operations are needed
                        if not output_path or not output_path.startswith(
                            REMOTE_URI_PREFIXES
                        ):
                            # For local paths, we can close dialog immediately
                            try:
                                dialog_ref.hide()
                                print("Dialog closed early for local path")
                            except:
                                pass

                        # Use the default settings
                        extract_model = DEFAULT_EXTRACT_MODEL
                        extract_animation = DEFAULT_EXTRACT_ANIMATION
                        replace_in_stage = DEFAULT_REPLACE_IN_STAGE
                        print(f"Configuration:")
                        print(f"  - Extract model: {extract_model}")
                        print(f"  - Extract animation: {extract_animation}")
                        print(f"  - Replace in stage: {replace_in_stage}")

                        # Check for existing files and prompt for overwrite
                        # Only check files that will actually be created
                        existing_files = []
                        for prim_path in selected_paths:
                            prim_name = prim_path.split("/")[-1]

                            if output_path:
                                # Only check model file if we're extracting model
                                if extract_model:
                                    model_name = f"{prim_name}.model.usda"
                                    model_path = join_url(output_path, model_name)
                                    model_result = await omni.client.stat_async(
                                        model_path
                                    )
                                    if model_result[0] == omni.client.Result.OK:
                                        existing_files.append(model_name)

                                # Only check animation file if we're extracting animation
                                if extract_animation:
                                    anim_name = f"{prim_name}.anim.usda"
                                    anim_path = join_url(output_path, anim_name)
                                    anim_result = await omni.client.stat_async(
                                        anim_path
                                    )
                                    if anim_result[0] == omni.client.Result.OK:
                                        existing_files.append(anim_name)

                        # If files exist, show confirmation dialog
                        if existing_files:
                            # Show overwrite confirmation
                            files_list = "\n".join(
                                f"  • {f}" for f in existing_files[:5]
                            )
                            if len(existing_files) > 5:
                                files_list += (
                                    f"\n  ... and {len(existing_files) - 5} more files"
                                )

                            message = f"The following files already exist:\n{files_list}\n\nDo you want to overwrite them?"

                            def on_overwrite_yes(d):
                                d.hide()
                                # Close the file picker dialog too
                                dialog_ref.hide()
                                # Process files
                                for prim_path in selected_paths:
                                    try:
                                        refactor_asset_with_priority(
                                            prim_path=prim_path,
                                            output_path=output_path,
                                            extract_model=extract_model,
                                            extract_animation=extract_animation,
                                            replace_in_stage=replace_in_stage,
                                        )
                                    except Exception as e:
                                        print(f"Error processing {prim_path}: {e}")

                            def on_overwrite_no(d):
                                d.hide()
                                print("Operation cancelled by user")

                            overwrite_dialog = MessageDialog(
                                title="Overwrite Files?",
                                message=message,
                                ok_handler=on_overwrite_yes,
                                cancel_handler=on_overwrite_no,
                                ok_label="Overwrite",
                                cancel_label="Cancel",
                            )
                            overwrite_dialog.show()
                        else:
                            # No existing files, proceed directly
                            try:
                                # Close the dialog first
                                dialog_ref.hide()
                                print(
                                    f"Dialog closed, processing {len(selected_paths)} prim(s)..."
                                )
                            except Exception as e:
                                print(f"Error closing dialog: {e}")

                            # Process files after dialog is closed
                            for prim_path in selected_paths:
                                try:
                                    refactor_asset_with_priority(
                                        prim_path=prim_path,
                                        output_path=output_path,
                                        extract_model=extract_model,
                                        extract_animation=extract_animation,
                                        replace_in_stage=replace_in_stage,
                                    )
                                except Exception as e:
                                    print(f"Error processing {prim_path}: {e}")

                    # Run async
                    asyncio.ensure_future(process_async(dialog))

                def on_cancel(filename: str, dirname: str):
                    """Handle cancel button"""
                    print("Operation cancelled by user")
                    dialog.hide()

                def on_filter_item(item) -> bool:
                    """Filter to show only folders"""
                    if item and not item.is_folder:
                        return False
                    return True

                # Create and show folder picker dialog
                dialog = FilePickerDialog(
                    "Select Output Folder for Refactored Assets",
                    apply_button_label="Select Folder",
                    click_apply_handler=on_folder_selected,
                    click_cancel_handler=on_cancel,
                    item_filter_fn=on_filter_item,
                    enable_file_bar=True,
                    enable_filename_input=False,
                    enable_checkpoints=False,
                )

                # Set to current stage directory by default
                current_layer = stage.GetRootLayer()
                if current_layer and current_layer.identifier:
                    try:
                        default_dir = get_dir_from_url(current_layer.identifier)
                        dialog.show(default_dir)
                    except:
                        dialog.show()
                else:
                    dialog.show()

            except ImportError:
                # Fallback if file picker is not available
                print("File picker not available, using default output location")
                for prim_path in selected_paths:
                    refactor_asset_with_priority(
                        prim_path=prim_path,
                        output_path=None,
                        extract_model=DEFAULT_EXTRACT_MODEL,
                        extract_animation=DEFAULT_EXTRACT_ANIMATION,
                        replace_in_stage=DEFAULT_REPLACE_IN_STAGE,
                    )
