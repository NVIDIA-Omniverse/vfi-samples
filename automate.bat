@echo off 
:: For how to build using the Kit application template (KAT) - https://github.com/NVIDIA-Omniverse/kit-app-template?tab=readme-ov-file#quick-
:: Set the paths below to where the files are on your hard drive.
set KIT_PATH=C:/Projects/Omniverse/KIT/107.3.1/_build/windows-x86_64/release/kit/kit.exe

:: SCRIPTS: Use current directory (where this batch file is located)
set SCRIPT_ROOT=%~dp0scripts

:: DATA: Point to your data folder (change this path as needed)
set VFI_WORKFLOW_DATA_FOLDER=C:/Projects/Omniverse/VFI/vfi_workflow_data

:: OUTPUT: Point to your output folder (change this path as needed)
set OUTPUT_ROOT=C:/Projects/Omniverse/VFI/vfi_workflow_data/_output

:: =============================================================================
:: DERIVED PATHS - No need to change these
:: =============================================================================

:: Script paths (all come from current directory)
set SCRIPT_CONVERT_JT=%SCRIPT_ROOT%/convert_jt.py
set SCRIPT_COPY_USD_FILES=%SCRIPT_ROOT%/copy_usd_files.py
set SCRIPT_VALIDATE=%SCRIPT_ROOT%/asset_validate.py
set SCRIPT_OPTIMIZE=%SCRIPT_ROOT%/scene_optimize.py
set SCRIPT_ASSIGN_MATERIALS=%SCRIPT_ROOT%/assign_materials.py
set SCRIPT_AGGREGATE_COMPONENTS=%SCRIPT_ROOT%/aggregate_components.py

:: Data paths (all come from data folder)
set JT_FOLDER=%VFI_WORKFLOW_DATA_FOLDER%/JT
set JT_SPEC_FILE=%SCRIPT_ROOT%/data/jt_spec.json
set GEO_ISSUES_FOLDER=%VFI_WORKFLOW_DATA_FOLDER%/GeoIssues
set MATERIAL_FOLDER=%VFI_WORKFLOW_DATA_FOLDER%/Materials

:: Output paths (all go to output folder)
set WHEEL_ASSET_FOLDER=%OUTPUT_ROOT%/Asset/Wheel
set WHEEL_PARTS_FOLDER=%WHEEL_ASSET_FOLDER%/Parts
set CONVERSION_LOG=%WHEEL_ASSET_FOLDER%/Automation/conversion.log
set VALIDATION_OUTPUT=%WHEEL_ASSET_FOLDER%/Automation/Validation/
set VALIDATION_LOG=%WHEEL_ASSET_FOLDER%/Automation/validation.log
set OPTIMIZER_LOG=%WHEEL_ASSET_FOLDER%/Automation/optimizer.log

:: =============================================================================
:: WORKFLOW EXECUTION
:: =============================================================================

ECHO -----------------------------------------------
ECHO Kit Path: %KIT_PATH%
ECHO Scripts from: %SCRIPT_ROOT%
ECHO Data from: %VFI_WORKFLOW_DATA_FOLDER%
ECHO Output to: %WHEEL_ASSET_FOLDER%
ECHO -----------------------------------------------

:: =============================================================================
:: CAD CONVERSION
:: Converts JT files to USD format using the JT converter
:: Scripts: convert_jt.py, copy_usd_files.py
:: Input: JT files from vfi_workflow_data/JT/
:: Output: USD files to Assets/Wheel/Parts/
:: =============================================================================

ECHO --- Converting JT Files ---
ECHO Converting files in: %JT_FOLDER%
ECHO Converting to: %WHEEL_PARTS_FOLDER%
ECHO Using Script: %SCRIPT_CONVERT_JT%
ECHO Using Spec File: %JT_SPEC_FILE%
ECHO Log Path: %CONVERSION_LOG%
call %KIT_PATH% --enable omni.services.convert.cad --exec "%SCRIPT_CONVERT_JT% --input_dir %JT_FOLDER% --output_dir %WHEEL_PARTS_FOLDER% --spec_path %JT_SPEC_FILE%" --/log/file=%CONVERSION_LOG% --no-window
ECHO --- Converting JT Files Complete ---

ECHO -----------------------------------------------
ECHO --- Copying bad files over for Asset Validation to find geometry issues ---
call %KIT_PATH% --exec "%SCRIPT_COPY_USD_FILES% --source_directory %GEO_ISSUES_FOLDER% --target_directory %WHEEL_PARTS_FOLDER%" --no-window

:: =============================================================================
:: USD VALIDATION
:: Validates USD files against quality standards and requirements
:: Scripts: asset_validate.py
:: Input: USD files from Assets/Wheel/Parts/
:: Output: Validation logs and CSV reports to Assets/Wheel/Automation/Validation/
:: =============================================================================

:VALIDATION_PHASE
ECHO.
choice /C YN /M "Continue to Asset Validation"
if errorlevel 2 goto :END

ECHO -----------------------------------------------
ECHO --- Running Asset Validation ---
ECHO Validating files in: %WHEEL_PARTS_FOLDER%
call %KIT_PATH% --enable omni.asset_validator.core --exec "%SCRIPT_VALIDATE% --input_dir %WHEEL_PARTS_FOLDER% --output_dir %VALIDATION_OUTPUT%" --/log/file=%VALIDATION_LOG% --no-window

:: =============================================================================
:: USD OPTIMIZATION
:: Applies Scene Optimizer operations to fix geometry issues and improve performance
:: Scripts: scene_optimize.py
:: Input: USD files from Assets/Wheel/Parts/
:: Output: Optimized USD files (in-place) + optimization logs
:: =============================================================================

:OPTIMIZATION_PHASE
ECHO.
choice /C YN /M "Continue to Scene Optimization"
if errorlevel 2 goto :END

ECHO -----------------------------------------------
ECHO --- Running Scene Optimizer ---
ECHO If necessary, optimizing files in : %WHEEL_PARTS_FOLDER%
call %KIT_PATH% --enable omni.scene.optimizer.core --enable omni.usd --exec "%SCRIPT_OPTIMIZE% --input_dir %WHEEL_PARTS_FOLDER% --output_dir %WHEEL_PARTS_FOLDER% --validation_dir %VALIDATION_OUTPUT%" --/log/file=%OPTIMIZER_LOG% --no-window

:: =============================================================================
:: USD AUTHORING - MATERIAL ASSIGNMENT
:: Assigns materials to meshes in USD components using predefined material mappings
:: Scripts: assign_materials.py
:: Input: USD files from Assets/Wheel/Parts/
:: Output: USD files with materials assigned (in-place)
:: =============================================================================

:MATERIAL_PHASE
ECHO.
choice /C YN /M "Continue to Material Assignment"
if errorlevel 2 goto :END

ECHO -----------------------------------------------
ECHO --- Making Material Assignments ---
ECHO Assigning materials to files in : %WHEEL_PARTS_FOLDER%
ECHO Using materials from: %MATERIAL_FOLDER%
call %KIT_PATH% --enable omni.usd --enable omni.mdl.usd_converter --exec "%SCRIPT_ASSIGN_MATERIALS% --input_dir %WHEEL_PARTS_FOLDER% --material_folder %MATERIAL_FOLDER%" --/log/file=%OPTIMIZER_LOG% --no-window --quit

:: =============================================================================
:: USD AND ASSEMBLY
:: Creates final wheel assembly by payloading all components with proper positioning
:: Scripts: aggregate_components.py
:: Input: USD component files from Assets/Wheel/Parts/
:: Output: Complete wheel assembly at Assets/Wheel/Wheel.usd
:: =============================================================================

:AGGREGATION_PHASE
ECHO.
choice /C YN /M "Continue to Component Aggregation"
if errorlevel 2 goto :END

ECHO -----------------------------------------------
ECHO --- Aggregating components ---
ECHO Aggregating components to Wheel.usd file: %WHEEL_PARTS_FOLDER%
call %KIT_PATH% --enable omni.usd --exec "%SCRIPT_AGGREGATE_COMPONENTS% --input_dir %WHEEL_PARTS_FOLDER% --output_file %WHEEL_ASSET_FOLDER%/Wheel.usd" --/log/file=%OPTIMIZER_LOG% --no-window --quit

:END
ECHO.
ECHO ===============================================
ECHO Workflow completed or stopped by user choice.
ECHO ===============================================
exit /b