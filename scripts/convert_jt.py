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
JT to USD Converter Script

This script converts JT files to USD format using the Omniverse Kit's JT converter.
It facilitates the integration of JT data into USD-based workflows, ensuring compatibility
with Omniverse applications and automating the conversion process for large datasets.

Features:
- High-performance concurrent processing
- Automatic output directory creation
- Comprehensive error handling with detailed error messages

Arguments:
    --input_dir      Directory containing input JT files.
    --output_dir     Directory to save converted USD files.
    --spec_path      Path to the JT converter specification JSON.

Example:
    /path/to/kit_executable --enable omni.services.convert.cad --exec "convert_jt.py --input_dir C:/vfi/input/raw_data --output_dir C:/vfi/output/converted --spec_path C:/vfi/jt_spec.json" --/log/file=/path/to/log.log --no-window

Note: If paths contain spaces, wrap them in escaped quotes: --input_dir C:/path with spaces/input

The optimizer preset is specified within the specification JSON file, not as a separate command-line argument.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import carb
import omni.kit.app


# Constants for converter script filenames
CONVERTER_SCRIPT_JT = "jt_main.py"
CONVERTER_SCRIPT_HOOPS = "hoops_main.py"
CONVERTER_SCRIPT_DGN = "dgn_main.py"


def create_temp_spec_with_absolute_paths(original_spec_path: str) -> str:
    """Create a temporary spec file with absolute path for sOptimizeConfig.
    
    This is necessary because the JT converter requires an absolute path on disk
    for the so_cad_ingest.json optimization preset file to function properly.
    """
    with open(original_spec_path, "r") as f:
        spec_data = json.load(f)

    # Set sOptimizeConfig to absolute path - required for JT converter to locate the preset file
    spec_dir = Path(original_spec_path).parent
    spec_data["sOptimizeConfig"] = (spec_dir / "so_cad_ingest.json").as_posix()

    # Write to temp file
    temp_spec_fd, temp_spec_path = tempfile.mkstemp(suffix="_jt_spec.json", text=True)
    with os.fdopen(temp_spec_fd, "w") as temp_file:
        json.dump(spec_data, temp_file, indent=2)

    return temp_spec_path


async def convert_file(
    input_file: Path, output_file: Path, spec_path: str, batch_script: str
) -> bool:
    """
    Run the JT conversion for a single file asynchronously.

    Args:
        input_file: Path to the input JT file
        output_file: Path where the converted USD file will be saved
        spec_path: Path to the JT converter specification JSON file
        batch_script: Path to the converter batch script

    Returns:
        bool: True if conversion succeeded, False otherwise
    """
    # Ensure output directory exists
    output_dir = os.path.dirname(str(output_file))
    os.makedirs(output_dir, exist_ok=True)

    # Get the Kit executable path (Python interpreter in this context)
    kit_file: str = Path(sys.executable).as_posix()

    # Build the command to run the JT converter
    command = f"{kit_file} --allow-root --enable omni.kit.converter.jt_core --exec --/app/fastShutdown=1 "
    command += f'"{batch_script} --input-path "{input_file}" --output-path "{output_file}" --config-path "{spec_path}""'

    # Execute the conversion command asynchronously
    process = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    # Check if conversion was successful
    if process.returncode != 0:
        print(f"Error converting {input_file}: {stderr.decode()}")
        return False
    else:
        print(f"Successfully converted {input_file} to {output_file}")
        return True


async def process_files(
    input_files: List[Path],
    input_dir: str,
    output_dir: str,
    spec_path: str,
    batch_script: str,
) -> None:
    """
    Process multiple JT files concurrently.

    Args:
        input_files: List of input JT file paths
        input_dir: Input directory path (used for path replacement)
        output_dir: Output directory path
        spec_path: Path to the JT converter specification JSON file
        batch_script: Path to the converter batch script
    """
    tasks = []

    # Create conversion tasks for all input files
    for input_file in input_files:
        # Generate output file path by replacing input dir with output dir and changing extension
        output_file = Path(
            input_file.as_posix().replace(input_dir, output_dir).replace(".jt", ".usd")
        )
        task = asyncio.create_task(
            convert_file(input_file, output_file, spec_path, batch_script)
        )
        tasks.append(task)

    # Wait for all conversion tasks to complete
    await asyncio.gather(*tasks)


def get_batch_script_path(converter: str = "jt") -> Optional[str]:
    """
    Get the path to the JT converter script from the Omniverse extension system.

    Args:
        converter: Type of converter ('jt', 'hoops', or 'dgn')

    Returns:
        Optional[str]: Path to the converter script if found, None otherwise

    Raises:
        ValueError: If converter type is not supported
    """
    # Determine which converter script to look for
    if converter == "jt":
        script = CONVERTER_SCRIPT_JT
    elif converter == "hoops":
        script = CONVERTER_SCRIPT_HOOPS
    elif converter == "dgn":
        script = CONVERTER_SCRIPT_DGN
    else:
        raise ValueError(f"Invalid converter: {converter}")

    # Build path to the converter script
    service_path = carb.tokens.get_tokens_interface().resolve(
        "${omni.services.convert.cad}"
    )

    # Check if service_path is empty
    if not service_path:
        print("Unable to find omni.services.convert.cad extension path.")
        return None
    else:
        print(f"Retrieved omni.services.convert.cad extension path: {service_path}")

    batch_script = f"{service_path}/omni/services/convert/cad/services/process/{script}"
    print(f"Batch script path: {batch_script}")

    # Verify the script file actually exists
    if not os.path.exists(batch_script):
        print(f"Batch script file does not exist: {batch_script}")
        return None

    return batch_script


async def convert_files_in_dir(input_dir: str, output_dir: str, spec_path: str) -> None:
    """
    Convert all JT files in a directory to USD format asynchronously.

    Args:
        input_dir: Directory containing input JT files
        output_dir: Directory to save converted USD files
        spec_path: Path to the JT converter specification JSON file
    """
    # Find all JT files in the input directory (recursive search)
    input_files: List[Path] = list(Path(input_dir).rglob("*.jt"))
    total_files: int = len(input_files)

    # Check if there are any JT files to process
    if total_files == 0:
        print("No JT files to process")
        return

    # Get the path to the converter batch script
    batch_script: Optional[str] = get_batch_script_path()

    # Exit if converter script is not available
    if not batch_script:
        print(f"Batch script can not be found")
        return

    print(
        f"Starting conversion of {total_files} JT files\nUsing distributed batch script -  {batch_script}"
    )

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Process all files concurrently
    await process_files(input_files, input_dir, output_dir, spec_path, batch_script)

    print(f"\nConversion completed!")
    print(f"Total files processed: {total_files}")


if __name__ == "__main__":
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(
        description="Convert JT files to USD format using the Omniverse Kit's JT converter.",
        epilog='Example: /path/to/kit_executable --enable omni.services.convert.cad --exec "convert_jt.py --input_dir C:/vfi/input --output_dir C:/vfi/output --spec_path C:/vfi/spec.json" --/log/file=/path/to/log.log --no-window',
    )
    parser.add_argument(
        "--input_dir", required=True, help="Directory containing input JT files."
    )
    parser.add_argument(
        "--output_dir", required=True, help="Directory to save converted USD files."
    )
    parser.add_argument(
        "--spec_path",
        required=True,
        help="Path to the JT converter specification JSON.",
    )

    args = parser.parse_args()

    # Create temporary spec file with resolved absolute paths
    temp_spec_path = None
    try:
        temp_spec_path = create_temp_spec_with_absolute_paths(args.spec_path)
        print(f"Using temporary spec file: {temp_spec_path}")

        # Run the conversion process with the temporary spec file
        asyncio.run(
            convert_files_in_dir(args.input_dir, args.output_dir, temp_spec_path)
        )

    finally:
        # Clean up temporary spec file
        if temp_spec_path and os.path.exists(temp_spec_path):
            try:
                os.unlink(temp_spec_path)
                print(f"Cleaned up temporary spec file: {temp_spec_path}")
            except Exception as e:
                print(
                    f"Warning: Could not clean up temporary spec file {temp_spec_path}: {e}"
                )

    # Properly shut down the Kit application
    omni.kit.app.get_app().post_quit(0)
