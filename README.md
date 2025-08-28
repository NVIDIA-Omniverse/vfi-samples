# Virtual Facility Integration (VFI) Script Samples

This repository contains script samples for Virtual Facility Integration (VFI) workflows. These utilities help convert CAD data to USD and help validate, optimize, process and aggregate USD data for VFI workflows. These are companion scripts for the [VFI guide documentation](http://docs.omniverse.nvidia.com/vfi/latest/index.html).

## Table of Contents
- [Quick Start](#quick-start)
- [Included Scripts](#included-scripts)
  - [JT to USD Converter](#jt-to-usd-converter-convert_jtpy)
  - [Copy USD Files](#copy-usd-files-copy_usd_filespy)
  - [USD Asset Validator](#usd-asset-validator-asset_validatepy)
  - [USD Scene Optimizer](#usd-scene-optimizer-scene_optimizepy)
  - [Material Assignment](#material-assignment-assign_materialspy)
  - [Component Aggregation](#component-aggregation-aggregate_componentspy)
- [Sample Data](#sample-data)
- [Common Use Cases](#common-use-cases)
- [Troubleshooting](#troubleshooting)
- [Batch Processing](automate.bat)

## Quick Start

1. **Set up NVIDIA Omniverse Kit**
   
   Choose one method to build Kit with the required extensions:

   **Option A - Using Git:**
   ```bash
   git clone https://github.com/NVIDIA-Omniverse/kit-app-template.git
   ```
   Follow the [kit-app-template instructions](https://github.com/NVIDIA-Omniverse/kit-app-template/?tab=readme-ov-file#quick-start) to build the USD Composer template.

   **Option B - Using NGC:**
   Go to [Kit SDK on NGC](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/omniverse/collections/kit) and follow the instructions for your platform.

2. **Download VFI workflow data**
   
   Download the VFI workflow data containing sample JT files, materials, and presets:
   ```
   https://developer.nvidia.com/downloads/usd/dataset/vfi-guide/vfi_workflow_data.zip
   ```
   
   Extract the data to a location on your system (you'll reference this path in the next step).

   **Kit Version Compatibility:**
   
   Some data files have Kit version-specific variants:
   - `so_cad_ingest.json` / `so_cad_ingest_107.json`
   - `so_weld.json` / `so_weld_107.json`
   
   **For Kit 108 users:** Use the default files - the automation scripts will use these automatically.
   
   **For Kit 107 users:** You need to use the `_107` suffixed versions of these files, as they contain Scene Optimizer presets compatible with Kit 107 (e.g., `mergeVertices` instead of `meshCleanup`).

3. **Configure paths in `automate.bat`**
   
   Edit the [`automate.bat`](automate.bat) file and update these three key paths:
   ```batch
   :: Update this path to your Kit executable
   set KIT_PATH=C:/Omniverse/kit-app-template/_build/windows-x86_64/release/kit/kit.exe

   :: Update this path to the sample data folder
   set VFI_WORKFLOW_DATA_FOLDER=C:/Omniverse/vfi/vfi_workflow_data

   :: Update this path to your desired output location
   set OUTPUT_ROOT=C:/Omniverse/vfi/output
   ```

4. **Run the automated workflow**
   
   Execute the [`automate.bat`](automate.bat) file to run the complete VFI pipeline:
   ```cmd
   automate.bat
   ```
   
   **Note:** The batch file includes 5 workflow sections. Section 1 runs automatically, then you'll be prompted with Y/N choices to continue or skip each subsequent section, which will allow you to check the output before moving on:
   - Section 1: CAD Conversion (JT to USD) - *runs automatically*
   - Section 2: USD Validation - *Y/N prompt*
   - Section 3: USD Optimization - *Y/N prompt*
   - Section 4: Material Assignment - *Y/N prompt*
   - Section 5: Component Aggregation - *Y/N prompt*

## Included Scripts

### JT to USD Converter (`convert_jt.py`)

Converts JT files to USD format using the [Omniverse Kit's JT converter](https://docs.omniverse.nvidia.com/kit/docs/omni.kit.converter.jt/latest/Usage.html#converter-options).

**Usage Example:**
```bash
/path/to/kit_executable --enable omni.services.convert.cad --exec "convert_jt.py --input_dir C:/vfi/input/raw_data --output_dir C:/vfi/output/converted --spec_path C:/vfi/jt_spec.json" --/log/file=/path/to/log.log --no-window
```

### Copy USD Files (`copy_usd_files.py`)

Copies USD files from a source directory to a target directory. In the VFI workflow, this script is used specifically to copy files with intentional geometry issues (from the `GeoIssues/` folder) into the output directory. This is necessary because the JT to USD conversion step produces clean geometry with no validation errors, so we need to introduce files with known issues to meaningfully demonstrate the validation and optimization workflow steps.

**Usage Example:**
```bash
/path/to/kit_executable --exec "copy_usd_files.py --source_directory C:/input --target_directory C:/output" --no-window
```

### USD Asset Validator (`asset_validate.py`)

Validates USD files using the [Omni Asset Validator](https://docs.omniverse.nvidia.com/kit/docs/asset-validator/latest/index.html). 

**Usage Example:**
```bash
/path/to/kit_executable --enable omni.asset_validator.core --exec "asset_validate.py --input_dir C:/path/to/input --output_dir C:/path/to/output" --/log/file=/path/to/log.log --no-window
```

### USD Scene Optimizer (`scene_optimize.py`)

Applies [Omniverse Scene Optimizer](https://docs.omniverse.nvidia.com/extensions/latest/ext_scene-optimizer.html) presets to USD stages.

**Usage Example:**
```bash
/path/to/kit_executable --enable omni.scene.optimizer.core --enable omni.usd --exec "scene_optimize.py --input_dir C:/path/to/input --output_dir C:/path/to/output --recursive --csv_output" --/log/file=/path/to/log.log --no-window
```

### Material Assignment (`assign_materials.py`)

Assigns materials to meshes in USD files using Kit commands. Uses a configurable mapping dictionary to associate components with materials.

**Usage Example:**
```bash
/path/to/kit_executable --enable omni.usd --enable omni.mdl.usd_converter --exec "assign_materials.py --input_dir C:/path/to/wheel_parts_folder --material_folder C:/path/to/materials" --/log/file=/path/to/log.log --no-window
```

### Component Aggregation (`aggregate_components.py`)

Creates an assembly from component USD files using USD payloads. Positions components according to predefined configurations, with special handling for bolt duplication to create a complete wheel assembly.

**Usage Example:**
```bash
/path/to/kit_executable --enable omni.usd --exec "aggregate_components.py --input_dir C:/path/to/wheel_parts_folder --output_file C:/path/to/output.usd" --/log/file=/path/to/log.log --no-window
```


## Sample Data

Sample data is available as a separate download:

**Download:** [Sample data download link to be provided]

The sample data includes:
- **JT/**: Original JT format files for automotive wheel components (Bolt, Brake_Disk, Caliper, Rim, Tire)
- **GeoIssues/**: USD files with intentional geometry issues for testing asset validation
- **Materials/**: MDL materials (Chromium, Disk_Brake, Caliper, Steel_Carbon, Tire) with textures
- **SO_Presets/**: Scene Optimizer presets (so_cad_ingest.json, so_weld.json, so_cm_y_up.json)
