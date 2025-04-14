# ai_processor_gemini.py - Handles interaction with the Google Gemini API

import logging
import json
import httpx
import asyncio
from typing import Dict, Any, Tuple, Optional, Union # Added Union

# Import necessary models and configuration structure
from models import AppSettings, PageResultData, PageProcessingResult, PageProcessingStatus
from pydantic import ValidationError

logger = logging.getLogger(__name__)

# --- Pure Functions ---
def construct_gemini_payload(
    image_base64: str,
    page_number: int,
    user_prompt_template: str,
    output_format: str, # Add output format parameter
    config: AppSettings
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Constructs the JSON payload for the Gemini API request using the user-provided prompt template.
    Formats the user prompt with the current page number.
    (Pure Function)

    Args:
        image_base64: Base64 encoded string of the page image.
        page_number: The page number being processed (for inserting into the prompt).
        user_prompt_template: The user-provided prompt string (potentially with {page_number}).
        output_format: The desired output format ('json' or 'text').
        config: Application settings containing the generation config.

    Returns:
        A tuple containing:
         - The dictionary payload if successful.
         - An error message string if formatting the prompt fails.
    """
    try:
        # Use simple string replacement for the placeholder to avoid issues with other braces
        prompt_text = user_prompt_template.replace("{page_number}", str(page_number))
        # Check if replacement happened (basic check if placeholder existed)
        if prompt_text == user_prompt_template and "{page_number}" in user_prompt_template:
             logger.warning("Placeholder {page_number} was found in the template but replacement did not occur. This is unexpected.")
    # Remove the try/except block specifically for KeyError from .format()
    # Any other exception during replace would be caught by the general Exception below
    except Exception as e:
         error_msg = f"Unexpected error formatting user prompt: {e}"
         logger.error(error_msg, exc_info=True)
         return None, error_msg

    # Determine response mime type based on the requested output_format
    response_mime_type = "application/json" if output_format == "json" else "text/plain"
    logger.debug(f"Setting response_mime_type based on requested format '{output_format}': {response_mime_type}")


    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {"inline_data": {"mime_type": "image/png", "data": image_base64}}
            ]
        }],
        "generationConfig": {
            # Set response type based on heuristic (or user preference later)
            "response_mime_type": response_mime_type,
            # Keep generation params relatively deterministic by default
            "temperature": 0.2, # Slightly higher temp might be needed for creative prompts
            "topK": 32,
            "topP": 0.95,
            "maxOutputTokens": 8192,
        },
        "safetySettings": [
            # Using default safety settings, consider making these configurable
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
    }
    logger.debug(f"Constructed Gemini payload for page {page_number}.")
    # Avoid logging the full payload due to potentially large base64 image data
    # logger.debug(f"Payload snippet: {json.dumps(payload, indent=2)[:500]}...")
    return payload, None # Return payload and no error

def parse_gemini_response(response_json: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Parses the Gemini API JSON response to extract the generated content text.
    Assumes 'response_mime_type': 'application/json' was used.
    (Pure Function)

    Args:
        response_json: The parsed JSON dictionary from the Gemini API response.

    Returns:
        A tuple containing:
            - extracted_text (Optional[str]): The extracted text content (should be JSON string) if found.
            - error_message (Optional[str]): An error description if the structure is invalid.
    """
    try:
        # Navigate the expected structure for JSON response mode
        extracted_text = response_json["candidates"][0]["content"]["parts"][0]["text"]
        logger.debug("Successfully extracted text content from Gemini response.")
        return extracted_text.strip(), None
    except (KeyError, IndexError, TypeError) as e:
        error_msg = f"Invalid response structure from Gemini: Failed to extract text content. Error: {e}. Response snippet: {str(response_json)[:500]}..."
        logger.error(error_msg)
        return None, error_msg

def parse_and_validate_ai_output(
    extracted_text: str,
    page_number: int,
    requested_format: str # e.g., "application/json" or "text/plain"
) -> Tuple[Optional[Union[Dict[str, Any], str]], Optional[PageProcessingStatus], Optional[str]]:
    """
    Attempts to parse the extracted text as JSON if requested.
    If JSON is requested but parsing fails, returns an error.
    If plain text is requested or JSON parsing fails for a JSON request, returns the raw text.
    (Pure Function - mostly, JSON parsing can fail)

    Args:
        extracted_text: The string extracted from the Gemini response.
        page_number: The page number for logging context.
        requested_format: The mime type requested from the API.

    Returns:
        A tuple containing:
            - result_data (Optional[Union[Dict, str]]): Parsed JSON dict or raw text string.
            - error_status (Optional[PageProcessingStatus]): Error status if JSON parsing failed when expected.
            - error_message (Optional[str]): Description of the parsing error.
    """
    if requested_format == "application/json":
        try:
            # Basic cleaning: remove potential markdown fences
            clean_text = extracted_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

            # Attempt to decode HTML entities (like &quot;) before parsing
            try:
                import html
                decoded_text = html.unescape(clean_text)
                logger.debug("Attempted HTML entity decoding.")
            except Exception as html_err:
                 # Log if decoding fails, but proceed with original text
                 logger.warning(f"HTML entity decoding failed: {html_err}. Attempting JSON parse with original text.")
                 decoded_text = clean_text


            if not clean_text:
                 raise json.JSONDecodeError("Extracted text is empty.", clean_text, 0)

            # Parse the potentially decoded text as JSON
            parsed_json = json.loads(decoded_text)
            logger.info(f"Successfully parsed AI response as JSON for page {page_number}.")
            # We don't validate against a specific Pydantic model anymore
            # because the structure is defined by the user's prompt.
            return parsed_json, None, None # Return the parsed dict

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse AI response as JSON for page {page_number}, although JSON was requested: {e}. Raw text (after potential decoding): {decoded_text[:500]}..."
            logger.error(error_msg)
            # Return error status and message, but also the raw text in the data field for inspection
            return extracted_text, PageProcessingStatus.ERROR_PARSING, error_msg
        except Exception as e:
             error_msg = f"Unexpected error processing AI JSON response for page {page_number}: {e}."
             logger.error(error_msg, exc_info=True)
             return extracted_text, PageProcessingStatus.ERROR_PARSING, error_msg # Treat as parsing error

    else: # Expected plain text
        logger.info(f"Returning raw text response for page {page_number} as requested.")
        return extracted_text, None, None


# REMOVED generate_mock_page_result function - Mocking is less useful with dynamic prompts.
# The workflow should handle the missing API key directly.
# (Orphaned docstring removed)

# --- Impure Functions ---

async def call_gemini_api(
    payload: Dict[str, Any],
    config: AppSettings,
    page_number: int # For logging context
) -> Tuple[Optional[Dict[str, Any]], Optional[PageProcessingStatus], Optional[str]]:
    """
    Makes the asynchronous POST request to the configured Gemini API endpoint.
    (Impure Function: Network I/O)

    Args:
        payload: The JSON payload dictionary created by construct_gemini_payload.
        config: Application settings containing the API URL, key, and timeout.
        page_number: The page number for logging context.

    Returns:
        A tuple containing:
            - response_json (Optional[Dict[str, Any]]): The parsed JSON response if successful.
            - error_status (Optional[PageProcessingStatus]): An error status enum value if failed.
            - error_message (Optional[str]): Description of the HTTP or timeout error.
    """
    if not config.gemini_api_key:
        # This case should ideally be handled before calling this function,
        # but added as a safeguard. The caller should use generate_mock_page_result instead.
        error_msg = "Attempted to call Gemini API without an API key."
        logger.error(error_msg)
        # Returning None, None, msg - Caller needs to handle this appropriately
        # It's better practice for the caller (workflow) to check for mock mode first.
        return None, PageProcessingStatus.ERROR_API, error_msg

    api_url_with_key = f"{config.gemini_api_url}?key={config.gemini_api_key}"
    headers = {"Content-Type": "application/json"}
    timeout = httpx.Timeout(config.process_timeout)

    description = f"Gemini API call for page {page_number}"
    logger.info(f"Initiating {description} to {config.gemini_api_url}...")
    # Avoid logging payload here due to size and potential sensitive info in prompt/image

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(api_url_with_key, json=payload, headers=headers)

            # Check for HTTP errors (4xx, 5xx)
            response.raise_for_status()

            response_json = response.json()
            logger.info(f"{description} successful (HTTP {response.status_code}).")
            # Log snippet for debugging structure issues if needed
            # logger.debug(f"Gemini response snippet: {str(response_json)[:500]}...")
            return response_json, None, None # Success

    except httpx.TimeoutException:
        error_msg = f"{description} failed: Request timed out after {config.process_timeout} seconds."
        logger.error(error_msg)
        return None, PageProcessingStatus.ERROR_TIMEOUT, error_msg
    except httpx.RequestError as e:
        # Network errors (DNS, connection refused, etc.)
        error_msg = f"{description} failed: Network request error: {e.__class__.__name__} - {e}"
        logger.error(error_msg)
        return None, PageProcessingStatus.ERROR_API, error_msg
    except httpx.HTTPStatusError as e:
        # Handle 4xx/5xx errors specifically
        error_body = e.response.text[:500] # Log response body snippet
        error_msg = f"{description} failed: HTTP status error: {e.response.status_code} {e.response.reason_phrase}. Response: {error_body}..."
        logger.error(error_msg)
        # You might want to map specific HTTP codes to different PageProcessingStatus values
        return None, PageProcessingStatus.ERROR_API, error_msg
    except json.JSONDecodeError as e:
        # If the response isn't valid JSON (unexpected from Gemini API but possible)
        error_msg = f"{description} failed: Could not decode API response as JSON: {e}. Response text snippet: {response.text[:500]}..."
        logger.error(error_msg)
        return None, PageProcessingStatus.ERROR_API, error_msg # Treat as API error
    except Exception as e:
        # Catch-all for other unexpected errors during the request
        error_msg = f"{description} failed: Unexpected error during API call: {e.__class__.__name__} - {e}"
        logger.error(error_msg, exc_info=True)
        return None, PageProcessingStatus.ERROR_UNKNOWN, error_msg


# Example Usage (optional)
async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    import os
    from image_processor import encode_image_to_base64 # Need image processor for example

    # --- Setup ---
    # Create a tiny dummy PNG file (1x1 pixel, black)
    dummy_png_bytes = bytes([
        0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4,
        0x89, 0x00, 0x00, 0x00, 0x0a, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0d, 0x0a, 0x2d, 0xb4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae,
        0x42, 0x60, 0x82
    ])
    with open("dummy_test_image.png", "wb") as f:
        f.write(dummy_png_bytes)
    dummy_image_path = Path("dummy_test_image.png")

    # --- Test Mock Mode ---
    print("\n--- Testing Mock Mode ---")
    config_mock = AppSettings(gemini_api_key="") # No API key
    # Mock mode is handled by the workflow now, not by calling a specific function here.
    # print("\n--- Testing Mock Mode ---")
    # config_mock = AppSettings(gemini_api_key="") # No API key
    # # mock_result = generate_mock_page_result(page_number=1) # Function removed
    # # print(f"Mock Result: {mock_result.model_dump_json(indent=2)}")

    # --- Test Real API Call (Requires GEMINI_API_KEY env var) ---
    print("\n--- Testing Real API Call ---")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Skipping real API call test: GEMINI_API_KEY environment variable not set.")
    else:
        config_real = AppSettings(gemini_api_key=api_key, process_timeout=30) # Short timeout for test
        print("Encoding image...")
        img_base64, img_err = encode_image_to_base64(dummy_image_path)
        if img_err:
            print(f"Failed to encode image: {img_err}")
        else:
            print("Constructing payload...")
            payload, prompt_err = construct_gemini_payload(img_base64, page_number=1, user_prompt_template="Transcribe page {page_number}", config=config_real)
            if prompt_err:
                print(f"Failed to construct payload: {prompt_err}")
                return # Exit example if payload fails

            print("Calling Gemini API...")
            response_json, error_status, error_msg = await call_gemini_api(payload, config_real, page_number=1)

            if error_msg:
                print(f"API call failed: [{error_status}] {error_msg}")
            else:
                print("API call successful!")
                # print(f"Response JSON: {json.dumps(response_json, indent=2)}") # Can be large

                print("\nParsing response...")
                extracted_text, parse_err = parse_gemini_response(response_json)
                if parse_err:
                    print(f"Failed to parse response: {parse_err}")
                else:
                    print(f"Extracted Text (should be JSON): {extracted_text}")

                    print("\nParsing/Validating output...")
                    # Use the updated function name and pass the mime type used in the request
                    # Assuming default payload construction requested JSON for this test
                    result_data, validation_status, validation_err = parse_and_validate_ai_output(extracted_text, page_number=1, requested_format="application/json")
                    if validation_err:
                        print(f"Parsing/Validation failed ({validation_status}): {validation_err}")
                        print(f"Returned Data (might be raw text): {result_data}")
                    else:
                        print("Parsing/Validation successful!")
                        print(f"Result Data: {json.dumps(result_data, indent=2) if isinstance(result_data, dict) else result_data}")

    # --- Cleanup ---
    if dummy_image_path.exists():
        dummy_image_path.unlink()
        print("\nCleaned up dummy image file.")

if __name__ == "__main__":
    # To test real API call, ensure GEMINI_API_KEY is set in your environment
    # e.g., export GEMINI_API_KEY="your_key_here"
    asyncio.run(main())