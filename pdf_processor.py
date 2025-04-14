# pdf_processor.py - Handles PDF page extraction (screenshots) and metadata extraction

import logging
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from models import AppSettings # For accessing config like command paths
from external_commands import run_subprocess_async # To run the actual commands

logger = logging.getLogger(__name__)

# --- PDF to PNG Extraction ---

async def extract_pdf_pages_as_png(
    pdf_path: Path,
    output_dir: Path,
    config: AppSettings
) -> Tuple[bool, List[Path], str]:
    """
    Generates PNG screenshots (300 DPI) for each page of a PDF using pdftoppm.

    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Directory where the resulting PNG images should be saved.
        config: The application settings containing the path to the pdftoppm command.

    Returns:
        A tuple containing:
            - success (bool): True if screenshot generation was successful (or partially successful with warnings).
            - screenshot_paths (List[Path]): List of paths to the created PNG files. Empty if failed catastrophically.
            - error_message (str): An error message if generation failed completely, or warnings if partially successful.
    """
    if not pdf_path.exists():
        error_msg = f"Input PDF file not found for screenshot generation: {pdf_path}"
        logger.error(error_msg)
        return False, [], error_msg

    # pdftoppm creates files like <output_prefix>-01.png, <output_prefix>-02.png etc.
    # We use the PDF filename stem as the prefix.
    output_prefix = output_dir / pdf_path.stem
    description = f"pdftoppm screenshot generation for '{pdf_path.name}'"

    # Ensure output directory exists
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured screenshot output directory exists: {output_dir}")
    except OSError as e:
        error_msg = f"Failed to create screenshot output directory '{output_dir}': {e}"
        logger.error(error_msg)
        return False, [], error_msg

    # Construct the command
    cmd = [
        config.pdftoppm_command,
        "-png",      # Output format
        "-r", "300", # Resolution (DPI)
        "-cropbox",  # Use the CropBox defined in the PDF (often better than MediaBox)
        # Consider adding -gray for grayscale if color isn't needed (smaller files)
        # Consider adding -aa yes -aaVector yes for anti-aliasing (prettier but slower?)
        str(pdf_path),      # Input PDF path
        str(output_prefix)  # Output file prefix (pdftoppm adds page numbers and extension)
    ]

    logger.info(f"Attempting screenshot generation: {' '.join(cmd)}")
    returncode, stdout, stderr = await run_subprocess_async(cmd, description)

    # Check for output files *after* the command runs
    # Use glob to find generated files, sort them numerically if possible
    generated_files = sorted(
        list(output_dir.glob(f"{output_prefix.name}-*.png")),
        key=lambda p: int(re.search(r'-(\d+)\.png$', str(p)).group(1)) if re.search(r'-(\d+)\.png$', str(p)) else 0
    )

    if generated_files:
        logger.info(f"Successfully generated {len(generated_files)} screenshots for '{pdf_path.name}'.")
        if returncode != 0:
            # Log warning if pdftoppm returned non-zero but files exist (common for minor issues like font errors)
            warning_msg = f"pdftoppm finished with code {returncode} but {len(generated_files)} screenshots were generated. Stderr: {stderr or '(empty)'}. Stdout: {stdout or '(empty)'}"
            logger.warning(warning_msg)
            # Return success=True, but include the warning message
            return True, generated_files, warning_msg.strip()
        else:
            # Success case
            return True, generated_files, ""
    else:
        # No files generated - definite failure
        error_msg = f"Screenshot generation failed: No PNG files were found for prefix '{output_prefix}'."
        if returncode != 0:
            error_msg += f" pdftoppm exited with code {returncode}."
        if stderr:
            error_msg += f" Stderr: {stderr}"
        if stdout:
            error_msg += f" Stdout: {stdout}"
        logger.error(error_msg)
        return False, [], error_msg.strip()


# --- PDF Metadata Extraction ---

async def extract_pdf_metadata(
    pdf_path: Path,
    config: AppSettings
) -> Tuple[bool, str, str]:
    """
    Extracts metadata from a PDF file using pdfinfo.

    Args:
        pdf_path: Path to the input PDF file.
        config: The application settings containing the path to the pdfinfo command.

    Returns:
        A tuple containing:
            - success (bool): True if pdfinfo ran successfully (exit code 0).
            - stdout (str): The standard output from pdfinfo (contains metadata).
            - stderr (str): The standard error from pdfinfo.
    """
    if not pdf_path.exists():
        error_msg = f"Input PDF file not found for metadata extraction: {pdf_path}"
        logger.error(error_msg)
        return False, "", error_msg

    description = f"pdfinfo metadata extraction for '{pdf_path.name}'"
    cmd = [config.pdfinfo_command, str(pdf_path)]

    logger.info(f"Attempting metadata extraction: {' '.join(cmd)}")
    returncode, stdout, stderr = await run_subprocess_async(cmd, description)

    if returncode == 0:
        logger.info(f"Successfully extracted metadata for '{pdf_path.name}'.")
        return True, stdout, stderr # Return stderr even on success, might contain warnings
    else:
        error_msg = f"Metadata extraction failed: pdfinfo exited with code {returncode}."
        if stderr:
            error_msg += f" Stderr: {stderr}"
        if stdout: # Sometimes errors are in stdout
            error_msg += f" Stdout: {stdout}"
        logger.error(error_msg)
        # Return stdout/stderr even on failure for potential debugging
        return False, stdout, error_msg.strip()


def parse_pdfinfo_output(pdfinfo_stdout: str) -> Dict[str, Any]:
    """
    Parses the key-value output of the pdfinfo command into a dictionary.
    (This is a Pure Function)

    Args:
        pdfinfo_stdout: The string output captured from pdfinfo's stdout.

    Returns:
        A dictionary containing the parsed metadata. Keys are lowercased with spaces replaced by underscores.
        Handles multi-line values if subsequent lines start with whitespace.
    """
    metadata = {}
    current_key = None
    current_value = []

    lines = pdfinfo_stdout.splitlines()

    for line in lines:
        match = re.match(r'^([^:]+):\s*(.*)', line)
        if match:
            # New key-value pair found
            # First, store the previous key-value if any
            if current_key and current_value:
                metadata[current_key] = "\n".join(current_value).strip()

            # Prepare the new key
            key_raw = match.group(1).strip()
            current_key = key_raw.lower().replace(' ', '_').replace('-', '_') # Normalize key

            # Store the first line of the value
            current_value = [match.group(2).strip()]
        elif current_key and line.strip() and line.startswith((' ', '\t')):
            # Continuation of the previous value (indented line)
            current_value.append(line.strip())
        elif current_key:
             # Line doesn't match key: value and isn't indented - likely end of previous value block
             if current_key and current_value:
                metadata[current_key] = "\n".join(current_value).strip()
             current_key = None
             current_value = []
        # Ignore lines that don't match the pattern and aren't continuations

    # Store the last key-value pair after the loop finishes
    if current_key and current_value:
        metadata[current_key] = "\n".join(current_value).strip()

    # Attempt to convert known numeric fields
    for key in ['pages', 'page_rot']:
        if key in metadata:
            try:
                metadata[key] = int(metadata[key])
            except (ValueError, TypeError):
                logger.warning(f"Could not convert pdfinfo field '{key}' to int: value='{metadata[key]}'")

    # Attempt to convert known boolean fields
    for key in ['encrypted', 'optimized', 'tagged']:
         if key in metadata:
            metadata[key] = metadata[key].lower() == 'yes'

    # Handle page size (e.g., "612 x 792 pts (letter)")
    if 'page_size' in metadata:
        size_match = re.match(r'([\d\.]+) x ([\d\.]+) pts', metadata['page_size'])
        if size_match:
            try:
                metadata['page_width_pts'] = float(size_match.group(1))
                metadata['page_height_pts'] = float(size_match.group(2))
            except ValueError:
                 logger.warning(f"Could not parse page dimensions from: '{metadata['page_size']}'")

    logger.debug(f"Parsed pdfinfo output: {metadata}")
    return metadata


# Example Usage (optional)
async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    import shutil

    # --- Setup ---
    if not shutil.which('pdftoppm') or not shutil.which('pdfinfo') or not shutil.which('libreoffice'):
        print("Skipping pdf_processor example: 'pdftoppm', 'pdfinfo', or 'libreoffice' command not found.")
        return

    temp_dir = Path("./temp_pdfprocessor_test")
    temp_dir.mkdir(exist_ok=True)
    input_dir = temp_dir / "input"
    output_dir_convert = temp_dir / "converted"
    output_dir_screenshots = temp_dir / "screenshots"
    input_dir.mkdir(exist_ok=True)
    output_dir_convert.mkdir(exist_ok=True)
    output_dir_screenshots.mkdir(exist_ok=True)

    # Create a dummy input file and convert it
    dummy_input_path = input_dir / "test_doc.txt"
    dummy_input_path.write_text("Page 1.\n\nPage 2 content.", encoding='utf-8')
    config = AppSettings(libreoffice_command="libreoffice", pdftoppm_command="pdftoppm", pdfinfo_command="pdfinfo")

    from document_converter import convert_to_pdf_libreoffice # Import for example
    conv_success, pdf_path, conv_error = await convert_to_pdf_libreoffice(dummy_input_path, output_dir_convert, config)

    if not conv_success:
        print(f"Failed to create test PDF: {conv_error}")
        shutil.rmtree(temp_dir)
        return

    print(f"Created test PDF: {pdf_path}")

    # --- Test Screenshot Generation ---
    print("\nTesting screenshot generation...")
    ss_success, ss_paths, ss_error = await extract_pdf_pages_as_png(pdf_path, output_dir_screenshots, config)
    if ss_success:
        print(f"Screenshots generated ({len(ss_paths)}):")
        for p in ss_paths:
            print(f" - {p.name} (Exists: {p.exists()})")
        if ss_error:
            print(f"Warnings during screenshot generation: {ss_error}")
    else:
        print(f"Screenshot generation failed: {ss_error}")

    # --- Test Metadata Extraction ---
    print("\nTesting metadata extraction...")
    meta_success, meta_stdout, meta_error = await extract_pdf_metadata(pdf_path, config)
    if meta_success:
        print("Metadata extraction command successful.")
        print("--- pdfinfo stdout ---")
        print(meta_stdout)
        print("----------------------")
        if meta_error: # Print stderr even if successful (might contain warnings)
             print(f"Warnings (stderr): {meta_error}")

        # --- Test Metadata Parsing ---
        print("\nTesting metadata parsing...")
        parsed_meta = parse_pdfinfo_output(meta_stdout)
        print("--- Parsed Metadata ---")
        import json
        print(json.dumps(parsed_meta, indent=2))
        print("-----------------------")

    else:
        print(f"Metadata extraction failed: {meta_error}")
        print(f"Stdout (if any): {meta_stdout}")


    # --- Cleanup ---
    shutil.rmtree(temp_dir)
    print(f"\nCleaned up test directory: {temp_dir}")


if __name__ == "__main__":
     import shutil # For example usage cleanup
     asyncio.run(main())