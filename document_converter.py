# document_converter.py - Handles document conversion to PDF using LibreOffice

import logging
from pathlib import Path
from typing import Tuple, Optional

from models import AppSettings # For accessing config like command path
from external_commands import run_subprocess_async # To run the actual command

logger = logging.getLogger(__name__)

async def convert_to_pdf_libreoffice(
    input_path: Path,
    output_dir: Path,
    config: AppSettings
) -> Tuple[bool, Optional[Path], str]:
    """
    Converts a given input document to PDF format using LibreOffice.

    Args:
        input_path: Path to the input document file.
        output_dir: Directory where the resulting PDF should be saved.
        config: The application settings containing the path to the LibreOffice command.

    Returns:
        A tuple containing:
            - success (bool): True if conversion was successful, False otherwise.
            - output_pdf_path (Optional[Path]): Path to the created PDF file if successful, None otherwise.
            - error_message (str): An error message if conversion failed, empty string otherwise.
    """
    if not input_path.exists():
        error_msg = f"Input file not found for conversion: {input_path}"
        logger.error(error_msg)
        return False, None, error_msg

    output_pdf_path = output_dir / f"{input_path.stem}.pdf"
    description = f"LibreOffice conversion for '{input_path.name}'"

    # Ensure output directory exists
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured output directory exists: {output_dir}")
    except OSError as e:
        error_msg = f"Failed to create output directory '{output_dir}': {e}"
        logger.error(error_msg)
        return False, None, error_msg

    # Construct the command
    # Using --norestore to prevent issues with recovery dialogs
    # Using --nolockcheck to prevent issues with stale lock files (use cautiously)
    # Using --invisible as an alternative to --headless, sometimes more reliable
    cmd = [
        config.libreoffice_command,
        "--invisible", # or "--headless"
        "--norestore",
        "--nolockcheck", # Consider potential risks if multiple processes access same files
        "--convert-to", "pdf:writer_pdf_Export", # Specify PDF export filter
        "--outdir", str(output_dir),
        str(input_path)
    ]

    logger.info(f"Attempting conversion: {' '.join(cmd)}")
    returncode, stdout, stderr = await run_subprocess_async(cmd, description)

    if returncode == 0 and output_pdf_path.exists():
        logger.info(f"Successfully converted '{input_path.name}' to '{output_pdf_path.name}'.")
        return True, output_pdf_path, ""
    else:
        # Determine specific error message
        if not output_pdf_path.exists():
            error_msg = f"Conversion failed: Output PDF file '{output_pdf_path.name}' was not created."
            logger.error(error_msg)
        else: # returncode != 0 but file exists (less common)
             error_msg = f"Conversion command finished with error code {returncode}, although output file might exist."
             logger.warning(error_msg) # Log as warning since file exists

        # Add details from stderr if available
        if stderr:
            error_msg += f" Stderr: {stderr}"
            # Check for common LibreOffice errors
            if "Error: source file could not be loaded" in stderr:
                 error_msg = f"Conversion failed: LibreOffice could not load the source file '{input_path.name}'. It might be corrupted or an unsupported format. Stderr: {stderr}"
            elif "javaldx failed" in stderr:
                 error_msg = f"Conversion failed: LibreOffice Java setup issue (javaldx failed). Check Java installation and LibreOffice configuration. Stderr: {stderr}"
        elif stdout: # Sometimes errors appear in stdout
             error_msg += f" Stdout: {stdout}"


        # Clean up potentially incomplete output file if it exists but conversion failed
        if output_pdf_path.exists() and returncode != 0:
            try:
                output_pdf_path.unlink()
                logger.warning(f"Removed potentially incomplete output file: {output_pdf_path}")
            except OSError as e:
                logger.error(f"Failed to remove potentially incomplete output file '{output_pdf_path}': {e}")

        return False, None, error_msg.strip()

# Example Usage (optional)
async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Create dummy config and directories/files for testing
    # IMPORTANT: Requires 'libreoffice' command to be available!
    if not shutil.which('libreoffice'):
        print("Skipping document_converter example: 'libreoffice' command not found.")
        return

    temp_dir = Path("./temp_converter_test")
    temp_dir.mkdir(exist_ok=True)
    input_dir = temp_dir / "input"
    output_dir = temp_dir / "output"
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    # Create a dummy input file (e.g., a simple text file)
    # LibreOffice might convert this, but ideally test with DOCX, ODT etc.
    dummy_input_path = input_dir / "test_doc.txt"
    dummy_input_path.write_text("This is a test document for conversion.", encoding='utf-8')
    print(f"Created dummy input: {dummy_input_path}")

    # Create dummy AppSettings
    config = AppSettings(libreoffice_command="libreoffice") # Assuming default path

    print(f"\nAttempting conversion of {dummy_input_path.name}...")
    success, pdf_path, error = await convert_to_pdf_libreoffice(dummy_input_path, output_dir, config)

    if success:
        print(f"Conversion successful: {pdf_path}")
        print(f"Output file exists: {pdf_path.exists()}")
    else:
        print(f"Conversion failed: {error}")

    # Clean up
    shutil.rmtree(temp_dir)
    print(f"\nCleaned up test directory: {temp_dir}")


if __name__ == "__main__":
     import shutil # For example usage cleanup
     asyncio.run(main())