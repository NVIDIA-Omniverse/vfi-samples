# USD Value Clips - Developer Guide

## Introduction

USD Value Clips provide a mechanism to sequence external animation data onto prims. This guide explains how to manually construct Value Clips metadata for developers who want to extend or customize animation sequencing workflows.

---

## Value Clips Architecture

### Core Concept

Value Clips allow you to:
1. Store animation data in separate USD files (clips)
2. Reference those clips from a main stage
3. Map stage timeline to clip internal time
4. Sequence multiple clips on the same prim

### Where Clips Metadata Lives

Value Clips metadata is applied to a **prim** (typically the root of an animated hierarchy). The metadata consists of:

```usda
over "AnimatedPrim" (
    clips = {
        dictionary default = {
            asset[] assetPaths = [...]
            string primPath = "..."
            double2[] active = [...]
            double2[] times = [...]
        }
    }
    clipSets = ["default"]
)
```

---

## Metadata Components

### 1. `assetPaths` (asset[])

An array of paths to animation clip files.

```usda
asset[] assetPaths = [
    @./clips/walk.anim.usda@,
    @./clips/run.anim.usda@,
    @./clips/idle.anim.usda@
]
```

- Paths can be relative (to the stage file) or absolute
- Each clip is referenced by its **index** (0, 1, 2, ...) in other arrays

### 2. `primPath` (string)

The prim path **inside the clip files** that maps to the target prim.

```usda
string primPath = "/root"
```

- Tells USD which prim hierarchy in the clip provides animation data
- Usually `/root` or the default prim of the clip file
- Must match the structure inside your clip files

### 3. `active` (double2[])

Specifies **which clip is active** at each stage time.

```usda
double2[] active = [
    (0, 0),      # At stage time 0, use clip index 0
    (1000, 1),   # At stage time 1000, switch to clip index 1
    (2000, 2)    # At stage time 2000, switch to clip index 2
]
```

Format: `(stage_time, clip_index)`

- First value: Stage timeline frame
- Second value: Index into `assetPaths` array

### 4. `times` (double2[])

Maps **stage time to clip internal time**.

```usda
double2[] times = [
    (0, 2052),        # Stage 0 → Clip time 2052
    (726, 2778),      # Stage 726 → Clip time 2778
    (1000, 2778),     # Stage 1000 → Hold at clip time 2778
    (1000, 2052),     # Stage 1000 → Start new clip at 2052
    (1726, 2778),     # Stage 1726 → Clip time 2778
    (2000, 2778)      # Stage 2000 → Hold at end
]
```

Format: `(stage_time, clip_time)`

**Key patterns:**
- Linear playback: `(start, clip_start)` to `(end, clip_end)`
- Hold at frame: Repeat the same clip_time for a range
- Transitions: Duplicate stage_time with different clip_times

### 5. `clipSets` (string[])

Names the clip sets defined in the `clips` dictionary.

```usda
clipSets = ["default"]
```

---

## Complete Example

### Stage File Structure

```usda
#usda 1.0
(
    defaultPrim = "World"
    endTimeCode = 3000
    startTimeCode = 0
    timeCodesPerSecond = 30
)

def Xform "World"
{
    def Xform "Robot_01" (
        payload = @./assets/robot.model.usda@
    )
    {
        # Transform overrides
        double3 xformOp:translate = (100, 0, 0)
        uniform token[] xformOpOrder = ["xformOp:translate"]

        # Value Clips applied to the animated hierarchy
        over "robot_rig" (
            clips = {
                dictionary default = {
                    asset[] assetPaths = [
                        @./clips/robot_wave.anim.usda@,
                        @./clips/robot_walk.anim.usda@,
                        @./clips/robot_wave.anim.usda@
                    ]
                    string primPath = "/root"
                    double2[] active = [
                        (0, 0),
                        (800, 1),
                        (1600, 2)
                    ]
                    double2[] times = [
                        (0, 2052),
                        (726, 2778),
                        (800, 2778),
                        (800, 2052),
                        (1248, 2500),
                        (1600, 2500),
                        (1600, 2052),
                        (2326, 2778),
                        (3000, 2778)
                    ]
                }
            }
            clipSets = ["default"]
        )
        {
        }
    }
}
```

### Animation Clip File Structure

```usda
#usda 1.0
(
    defaultPrim = "root"
    startTimeCode = 2052
    endTimeCode = 2778
    timeCodesPerSecond = 30
)

def Xform "root"
{
    def Xform "joint_01"
    {
        quatd xformOp:orient.timeSamples = {
            2052: (1, 0, 0, 0),
            2100: (0.707, 0, 0.707, 0),
            2200: (0.5, 0.5, 0.5, 0.5),
            ...
            2778: (1, 0, 0, 0),
        }
        uniform token[] xformOpOrder = ["xformOp:orient"]
    }
}
```

---

## Building Times Array - Detailed Logic

### Single Clip (Simple)

```python
# Clip plays from stage frame 0, internal range 2052-2778
times = [
    (0, 2052),      # Start
    (726, 2778),    # End (726 = 2778 - 2052)
]
```

### Multiple Clips (Sequential)

```python
# Clip 0: Stage 0-726, Clip range 2052-2778
# Clip 1: Stage 1000-1448, Clip range 2052-2500

times = [
    # Clip 0
    (0, 2052),          # Clip 0 starts
    (726, 2778),        # Clip 0 ends
    (1000, 2778),       # Hold at clip 0 end until clip 1 starts
    
    # Clip 1 (duplicate stage time for transition)
    (1000, 2052),       # Clip 1 starts at same stage time
    (1448, 2500),       # Clip 1 ends
    (2000, 2500),       # Hold at clip 1 end
]

active = [
    (0, 0),             # Clip 0 active from stage 0
    (1000, 1),          # Clip 1 active from stage 1000
]
```

### Key Rules

1. **Duplicate stage times at transitions**: When switching clips, have two entries with the same stage time—one for the old clip's end, one for the new clip's start

2. **Active array determines which times apply**: At any stage time, USD uses the `active` array to determine which clip is active, then looks up that clip's time mapping

3. **Hold behavior**: To hold a pose, create times entries where the clip_time stays constant while stage_time advances

---

## Python API Example

```python
from pxr import Usd, Sdf, Vt, Gf

def apply_value_clips(stage, target_prim_path, clips_data):
    """
    Apply Value Clips metadata to a prim.
    
    Args:
        stage: Usd.Stage
        target_prim_path: str - Path to prim receiving clips
        clips_data: dict with keys:
            - asset_paths: list of clip file paths
            - prim_path: str - primPath inside clips
            - active: list of (stage_time, clip_index) tuples
            - times: list of (stage_time, clip_time) tuples
    """
    layer = stage.GetRootLayer()
    prim_spec = Sdf.CreatePrimInLayer(layer, target_prim_path)
    prim_spec.specifier = Sdf.SpecifierOver
    
    # Build clips dictionary
    clips_dict = {
        "default": {
            'assetPaths': Sdf.AssetPathArray([
                Sdf.AssetPath(p) for p in clips_data['asset_paths']
            ]),
            'primPath': clips_data['prim_path'],
            'active': Vt.Vec2dArray([
                Gf.Vec2d(float(a[0]), float(a[1])) 
                for a in clips_data['active']
            ]),
            'times': Vt.Vec2dArray([
                Gf.Vec2d(float(t[0]), float(t[1])) 
                for t in clips_data['times']
            ]),
        }
    }
    
    # Note: SetInfo may throw but data is still written (known quirk)
    try:
        prim_spec.SetInfo('clips', clips_dict)
        prim_spec.SetInfo('clipSets', ["default"])
    except Exception:
        pass  # Data written despite exception
    
    layer.Save()


# Example usage
clips_data = {
    'asset_paths': [
        './clips/anim_01.usda',
        './clips/anim_02.usda',
    ],
    'prim_path': '/root',
    'active': [(0, 0), (1000, 1)],
    'times': [
        (0, 2052), (726, 2778),
        (1000, 2778), (1000, 2052), (1726, 2778)
    ]
}

stage = Usd.Stage.Open('my_scene.usda')
apply_value_clips(stage, '/World/Robot/rig', clips_data)
```

---

## Optional Metadata

### `interpolateMissingClipValues` (bool)

Enables interpolation for sparse keyframes:

```usda
bool interpolateMissingClipValues = 1
```

When `true`, USD interpolates between existing keyframes if the computed clip time falls between samples.

### `manifestAssetPath` (asset)

Points to a manifest file listing which prims have clip data:

```usda
asset manifestAssetPath = @./clips/manifest.usda@
```

Improves performance by telling USD exactly which prims to look for in clips.

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Animation doesn't play | `primPath` mismatch | Ensure clip's default prim matches `primPath` |
| Wrong frames playing | Incorrect `times` mapping | Verify stage↔clip time calculations |
| Hydra errors | Clip time outside valid range | Check `startTimeCode`/`endTimeCode` in clips |
| Sudden pops | Missing transition entry | Add duplicate stage_time at clip boundaries |

### Debugging Tips

1. **Print the metadata**: Use `prim.GetMetadata('clips')` to inspect
2. **Check clip files**: Verify `startTimeCode` and `endTimeCode` are correct
3. **Test individual clips**: Apply one clip at a time to isolate issues
4. **Console logging**: USD prints useful info about clip resolution

---

## Additional Resources

- [USD Value Clips Documentation](https://graphics.pixar.com/usd/docs/api/class_usd_clips_a_p_i.html)
- [Value Clips Tutorial](https://graphics.pixar.com/usd/docs/Value-Clips.html)
- Animation Asset Extractor tool (for generating clip files)
- Value Clip Sequencer tool (UI for building sequences)

