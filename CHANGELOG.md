# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.0] - 2025-12-17

### Added

* Animation workflow scripts and documentation (scripts/animation/)

  * USD Animation Asset Extractor (scripts/animation/usd\_anim\_asset\_extractor.py) - Extracts timeSample data from precomposed stages and generates timeSample value clips with automatic reapplication as referenced clips
  * Value Clip Sequencer (scripts/animation/valie\_clip\_sequencer.py) - A simple interface that allows the composition of sequenced animation as value clips.
  * Reference Time Offset Editor (scripts/animation/reference\_time\_offset\_editor.py) - Enables offsetting the playback time of value clip references and payloads
  * Convert Orient to Eulers (scripts/animation/convert\_orient\_to\_euler\_simple.py) - Converts quaternion rotation data to Euler angles for curve editor compatibility

## [1.0.0] - 2025-07-18

### Added

* JT to USD Converter (scripts/convert\_jt.py) - Converts JT files to USD format
* Copy USD Files (scripts/copy\_usd\_files.py) - Copies USD files between directories with automatic target directory creation
* USD Asset Validator (scripts/asset\_validate.py) - Validates USD files using Asset Validator
* USD Scene Optimizer (scripts/scene\_optimize.py) - Applies Scene Optimizer presets to USD stages with file-specific preset selection
* Material Assignment (scripts/assign\_materials.py) - Assigns materials to meshes in USD files using Kit commands
* Component Aggregation (scripts/aggregate\_components.py) - Creates complete assemblies from component USD files with predefined positioning configurations
* Batch Processing (automate.bat) - Batch processing script to automate VFI workflow
