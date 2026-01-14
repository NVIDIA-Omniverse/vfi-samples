# Animation Workflow and Supporting Scripts

This directory contains animation-focused script samples for Virtual Facility Integration (VFI) workflows. The utilities help extract, validate, and reuse USD animation clips so you can optimize shared assets within large facilities. These samples accompany the VFI guide documentation's [VFI Animation Workflow and Supporting Scripts section](http://docs.omniverse.nvidia.com/vfi/latest/guide/animation.html).

This workflow serves as a guide to creating a scalable animation pipeline that enables a more efficient workflow for animated assets. Separating animation data from the assets, in the form of TimeSampled animation clips (Value clips) offers more flexibility in asset management and stage composition. When many instances of the same asset occur in a single stage, it removes the need for duplication of the whole asset with embedded animation, enabling lighter stages and databases.

As not all exporters and connectors will export value clips, we have provided some sample scripts that will assist in generating Animation clip data.

 Benefits of TimeSampled animation (value) clips include:

* Lighter weight stages
* Separation of animation data and model assets
* Improved asset management with more intuitive stage composition
* Simple workflow to swap out or update animations
* Enables the sequencing of multiple animations on the same asset

## Table of Contents

- [Included Scripts](#included-scripts)
  - [USD animation asset extractor (`usd_anim_asset_extractor.py`)](#usd-animation-asset-extractor-usd_anim_asset_extractorpy)
    - [Applying the value clip to the asset in a new stage](#applying-the-value-clip-to-the-asset-in-a-new-stage)
  - [USD Reference Time Offset (`reference_time_offset_editor.py`)](#usd-reference-time-offset-reference_time_offset_editorpy)
  - [Convert Orient to Eulers (`convert_orient_to_euler_simple.py`)](#convert-orient-to-eulers-convert_orient_to_euler_simplepy)
  - [Value Clip Sequencing (`value_clip_sequencer.py`)](#value-clip-sequencing-value_clip_sequencerpy)


## Included Scripts
### USD animation asset extractor (`usd_anim_asset_extractor.py`)

This script combines 3 functions to generate compatible animation assets. There are three independent features (each controlled by its own flag):

1. extract_model: Extract model layer (creates file, doesn't modify stage)
2. extract_animation: Extract animation layer (creates file, doesn't modify stage)
3. replace_in_stage: Replace original prim with references (modifies current stage)

Key improvement: Static model adds a wrapper root prim to ensure animation timesamples always override default values regardless of reference order.

At the top of the script you will find the three functions and flags to set up your desired behavior.  The script will execute any combination of these three options. Replace `True` with `False` to de-activate a feature.

```
# ============================================

# CONFIGURATION: Set default behavior for three independent features

# ============================================

# extract_model: Extract model layer (creates file, doesn't modify stage)
# extract_animation: Extract animation layer (creates file, doesn't modify stage)
# replace_in_stage: Replace original prim with references (modifies current stage)

DEFAULT_EXTRACT_MODEL = True      # <-- Copy the static model prim/attributes into another USD layer

DEFAULT_EXTRACT_ANIMATION = True  # <-- Copy the animated prim/attributes into another USD layer

DEFAULT_REPLACE_IN_STAGE = True   # <-- Replace the original prim with the two USD layers in payload/reference
```

> **Note:** In some cases, the reference stack for an asset can be very deep, which may cause the script to fail when generating the clip. If that happens, open the upstream referenced layer that contains the asset and animation directly, then rerun the script.

To use:

1. Copy the script to a desired accessible location.
2. Open the script editor in Omniverse USD Composer.
4. Enter the following command (adapt this path for the location of the script):
    `exec(open(r'{repo_root}/scripts/animation/usd_anim_asset_extractor.py').read())`

> **Note:** In versions prior to kit 109, a bug exists with FSD that prevents the animation from playing upon initial loading. Saving and reloading the file will allow the Animation to Play.

To see the animations play as you add them to the stage, please disable FSD during this process. This issue is resolved in Kit 109 and above.

#### Applying the value clip to the asset in a new stage

1. Add the asset to a new stage (as either a payload or reference). It is good practice to create an Xform and name it appropriately and add the asset to this xform as a payload or reference. The first prim within the payload should exactly match the asset it was exported from.
2. Select this Prim -> Right Click -> Add payload/reference.  
3. Navigate to the location of the value clip and assign it.

The value clip has now been referenced to the asset and the animation should play. You can now add the same asset to the stage as many times as required and mix and match the animations applied to each one.

### USD Reference Time Offset (`reference_time_offset_editor.py`)

This script/utility enables the user to offset the play time of a selected value clip. 

To use:

1. Copy the script to a desired accessible location.
2. Open the script editor in Omniverse USD Composer.
3. Select the prim that contains the value clip reference or payload that you want to offset.
4. Enter the following command (adapt this path for the location of the script):
    `exec(open(r'{repo_root}/scripts/animation/reference_time_offset_editor.py').read())`
5. Click `Run`.

### Convert Orient to Eulers (`convert_orient_to_euler_simple.py`)

The default rotation values for usd are written as quaternions. In cases where the user wants to convert timesamples to animation curves for editing with omniverse curve editor, it will be necessary to convert the Quaternion data to Euler data prior to the curve conversion.

To use:

1. Select the prim that contains the hierarchy of timeSample animation and execute the script.
2. Copy the script to a location on your hard drive.
3. Open the script editor in Omniverse USD Composer.
4. Select the prim containing the quaternion timesample data.
5. Enter the following command (adapt this path for the location of the script):
    `exec(open(r'{repo_root}/scripts/animation/convert_orient_to_euler_simple.py').read())`
6. Click `Run`.

The data has now been converted to Eulers.


### Value Clip Sequencing (`value_clip_sequencer.py`)

For value clip sequencing, please refer to the [Value Clip Sequencer Guide](scripts/animation/VALUE_CLIP_SEQUENCER_GUIDE.md).
For a more detailed developer guide for usd value clips, please refer to the [Value Clips Developer Guide](scripts/animation/VALUE_CLIPS_DEVELOPER_GUIDE.md).

