# Value Clip Sequencer - User Guide

## Overview

The Value Clip Sequencer is a tool for creating animation sequences using USD Value Clips. It allows you to sequence multiple animation clips on a single asset, enabling efficient reuse of animation data across your stage.

### Why Use Value Clips?

- **Efficient Asset Reuse**: Add the same model multiple times without duplicating animation data
- **Flexible Sequencing**: Chain multiple animations together on a single asset
- **Non-Destructive**: Animation data stays separate from the model
- **Scalable Pipeline**: Build animation libraries that can be applied to any compatible asset

---

## Prerequisites

Before using the Value Clip Sequencer, ensure you have:

1. **A model asset** saved as a USD file (e.g., `robot.model.usda`)
2. **Animation clips** extracted using the Animation Asset Extractor tool
   - Clips should have the correct `startTimeCode` and `endTimeCode` set
   - Clips should use `/root` as the default prim

---

## Step-by-Step Guide

### Step 1: Prepare Your Stage

1. Create a new USD stage or open an existing one
2. Add your model as a **Payload** or **Reference**:
   - Right-click in the Stage panel → Add → Payload
   - Browse to your model file (e.g., `robot.model.usda`)
3. Position the asset as needed using transform controls
4. **⚠️ IMPORTANT: Save your stage file before applying clips**
   - File → Save As (e.g., `my_scene.usda`)
   - This is required because clip paths are saved **relative to your stage file location**
   - If you don't save first, you'll see the error: *"Please save your stage first before applying clips"*

### Step 2: Open the Value Clip Sequencer

1. Open the Script Editor in Omniverse
2. Load and run `simple_clip_sequencer.py`
3. The **Value Clip Sequencer** window will appear

### Step 3: Select the Target Prim

1. In your viewport or Stage panel, **select the prim** that contains the model payload
   - This is typically the Xform prim you created when adding the payload
   - Example: `/World/Robot_01`
2. In the sequencer, click **"Get Selected"**
3. The prim path will appear in the Prim Path field

### Step 4: Add Animation Clips

1. Click **"+ ADD CLIP"**
2. In the file browser, navigate to your animation clip file
   - Example: `robot_wave.anim.usda`
3. Click **"Add Clip"** to add it to the sequence
4. Repeat for additional clips

### Step 5: Configure Timing

For each clip in the sequence, you can adjust:

| Field | Description |
|-------|-------------|
| **Stage Start** | The frame on the stage timeline when this clip begins playing |
| **Clip Range** | The internal frame range within the clip file to use (for trimming) |

**Example Configuration:**
```
Clip 1: "wave.anim.usda"
  - Stage Start: 0
  - Clip Range: 2052 - 2778 (726 frames of animation)

Clip 2: "walk.anim.usda"
  - Stage Start: 800
  - Clip Range: 2052 - 2500 (448 frames)

Clip 3: "idle.anim.usda"
  - Stage Start: 1300
  - Clip Range: 2052 - 2652 (600 frames)
```

### Step 6: Reorder Clips (Optional)

- Use the **▲** and **▼** buttons to reorder clips in the list
- Use the **✕** button to remove a clip
- Use **"Clear All"** to remove all clips and start over

### Step 7: Apply to Stage

1. Click **"APPLY TO STAGE"**
2. The Value Clips metadata will be written to your stage file
3. The stage will automatically save
4. Check the Status bar for confirmation

### Step 8: Playback

1. Use the timeline controls to scrub through your animation
2. Each clip will play at its designated start time
3. Between clips, the animation will hold at the last frame

---

## Tips & Best Practices

### Trimming Animations

If your animation clips contain frames you don't want to use (e.g., T-pose at the start):

1. Adjust the **Clip Range Start** to skip unwanted frames
2. Adjust the **Clip Range End** to cut the animation short
3. The **duration** displayed shows the resulting playback length

### Overlapping vs. Sequential

- **Sequential**: Set each clip's Stage Start after the previous clip ends
- **Hard Cut**: Set Stage Start exactly when you want the switch (instant transition)
- **Gap**: Leave frames between clips to hold on the last frame

### Multiple Instances

To animate multiple instances of the same model:

1. Add the model payload multiple times to your stage
2. Run the sequencer for each instance
3. Each can have its own unique sequence of clips

---

## Troubleshooting

### "Please save your stage first before applying clips"

This error appears when you try to apply clips to an **unsaved stage**. The sequencer needs to know your stage file's location to calculate relative paths for clips.

**Solution:** Save your stage file first (File → Save As), then try again.

### Animation Not Playing

- Verify the **Clip Prim Path** matches your clip structure (default: `/root`)
- Check that clip files exist at the specified paths
- Ensure the prim has a valid payload/reference

### Console Warnings (Kit 107.x)

- Some Hydra warnings may appear in Kit 107.x but don't affect playback
- These are resolved in Kit 109+

### Wrong Animation Range

- Re-extract clips using the updated Animation Asset Extractor
- Verify `startTimeCode` and `endTimeCode` in the clip file header

---

## Example Workflow

```
1. Export robot model → robot.model.usda
2. Export animations → robot_wave.anim.usda, robot_walk.anim.usda
3. Create stage → factory_scene.usda
4. Add payload → /World/Robot_01 (robot.model.usda)
5. Run Value Clip Sequencer
6. Select /World/Robot_01 → Get Selected
7. Add clips: wave (start: 0), walk (start: 800), wave (start: 1600)
8. Apply to Stage
9. Play timeline to see the sequence!
```

---

## Related Tools

- **Animation Asset Extractor** - Extract animation clips from animated assets
- **Animation EDL Sequencer** - Batch sequencing using Edit Decision Lists

