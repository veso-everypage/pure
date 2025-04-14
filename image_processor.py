# image_processor.py - Handles image-related operations like encoding

import base64
import logging
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

def encode_image_to_base64(image_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Reads an image file and returns its base64 encoded representation.

    Args:
        image_path: Path to the image file (e.g., a PNG screenshot).

    Returns:
        A tuple containing:
            - base64_encoded_string (Optional[str]): The base64 encoded image data (UTF-8 string),
                                                      or None if an error occurred.
            - error_message (Optional[str]): An error message if reading or encoding failed,
                                             None otherwise.
    """
    description = f"Base64 encoding for '{image_path.name}'"
    logger.debug(f"Attempting {description}...")

    try:
        # Read the image file as bytes
        image_bytes = image_path.read_bytes()

        # Encode the bytes using base64
        base64_bytes = base64.b64encode(image_bytes)

        # Decode the base64 bytes into a UTF-8 string
        base64_string = base64_bytes.decode('utf-8')

        logger.debug(f"{description} successful.")
        return base64_string, None

    except FileNotFoundError:
        error_msg = f"Image file not found for encoding: {image_path}"
        logger.error(error_msg)
        return None, error_msg
    except OSError as e:
        # Catch other potential file system errors (permissions, etc.)
        error_msg = f"OS error reading image file '{image_path}': {e}"
        logger.error(error_msg, exc_info=True) # Include stack trace for OS errors
        return None, error_msg
    except Exception as e:
        # Catch any other unexpected errors
        error_msg = f"Unexpected error during image encoding for '{image_path}': {e}"
        logger.error(error_msg, exc_info=True)
        return None, error_msg

# Example Usage (optional)
if __name__ == "__main__":
    import tempfile
    import shutil

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Create a temporary directory and a dummy file
    temp_dir = Path(tempfile.mkdtemp(prefix="image_processor_test_"))
    # Create a tiny dummy PNG file (1x1 pixel, black)
    # Header: 89 50 4E 47 0D 0A 1A 0A
    # IHDR chunk: 00 00 00 0D (length) 49 48 44 52 (type) ... (data) ... (CRC)
    # IDAT chunk: ...
    # IEND chunk: 00 00 00 00 49 45 4E 44 AE 42 60 82
    dummy_png_bytes = bytes([
        0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4,
        0x89, 0x00, 0x00, 0x00, 0x0a, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0d, 0x0a, 0x2d, 0xb4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae,
        0x42, 0x60, 0x82
    ])
    dummy_image_path = temp_dir / "test_image.png"
    dummy_image_path.write_bytes(dummy_png_bytes)
    print(f"Created dummy image: {dummy_image_path}")

    print("\nTesting image encoding...")
    encoded_data, error = encode_image_to_base64(dummy_image_path)

    if encoded_data:
        print(f"Encoding successful!")
        print(f"Base64 Data (first 60 chars): {encoded_data[:60]}...")
        print(f"Expected start: iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQ...") # Check against known good encoding
        # Verify decoding (optional)
        try:
            decoded_bytes = base64.b64decode(encoded_data.encode('utf-8'))
            print(f"Decoded bytes match original? {decoded_bytes == dummy_png_bytes}")
        except Exception as dec_err:
            print(f"Error decoding result: {dec_err}")
    else:
        print(f"Encoding failed: {error}")

    print("\nTesting with non-existent file:")
    non_existent_path = temp_dir / "not_real.png"
    encoded_data, error = encode_image_to_base64(non_existent_path)
    if error:
        print(f"Encoding failed as expected: {error}")
    else:
        print("Error: Encoding succeeded unexpectedly for a non-existent file.")

    # Cleanup
    shutil.rmtree(temp_dir)
    print(f"\nCleaned up test directory: {temp_dir}")