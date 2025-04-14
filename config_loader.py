# config_loader.py - Load application configuration from environment variables

import os
import logging
from typing import List
from models import AppSettings # Import the model from our models file
from pydantic import HttpUrl, ValidationError

logger = logging.getLogger(__name__)

def load_app_config() -> AppSettings:
    """
    Loads configuration from environment variables, validates them,
    and returns an AppSettings object.
    """
    try:
        # Handle API_KEY (potentially multiple keys separated by comma)
        api_keys_str = os.environ.get("API_KEY", "everypage-9d207bf0-10f5-4d8f-a479-22ff5aeff8d1")
        api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]

        settings = AppSettings(
            api_keys=api_keys,
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            gemini_api_url=HttpUrl(os.environ.get("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent")),
            # REMOVED fixed_processing_prompt_template loading
            # Use getint helper for integer conversion with default
            max_workers=int(os.environ.get('MAX_WORKERS', '5')),
            process_timeout=int(os.environ.get('PROCESS_TIMEOUT', '90')),
            temp_dir_base=os.environ.get('TEMP_DIR_BASE', '/tmp/everypage_pure'),
            libreoffice_command=os.environ.get('LIBREOFFICE_COMMAND', 'libreoffice'),
            pdftoppm_command=os.environ.get('PDFTOPPM_COMMAND', 'pdftoppm'),
            pdfinfo_command=os.environ.get('PDFINFO_COMMAND', 'pdfinfo'),
            log_level=os.environ.get('LOG_LEVEL', 'INFO').upper()
        )

        # Basic logging after loading
        logger.info("Configuration loaded successfully.")
        if not settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY environment variable not set. Mock results will be used.")
        else:
            logger.info("GEMINI_API_KEY is configured.")
        # REMOVED logging for fixed prompt template
        logger.info(f"Max workers: {settings.max_workers}, Process timeout: {settings.process_timeout}s")
        logger.info(f"Temporary directory base: {settings.temp_dir_base}")

        return settings

    except (ValidationError, ValueError) as e:
        logger.error(f"Configuration validation failed: {e}")
        # Provide more specific error messages based on common issues
        if 'api_keys' in str(e):
             logger.error("Check the format of the API_KEY environment variable (comma-separated if multiple).")
        if 'gemini_api_url' in str(e):
             logger.error("Check the format of the GEMINI_API_URL environment variable (must be a valid URL).")
        if 'max_workers' in str(e) or 'process_timeout' in str(e):
             logger.error("Check if MAX_WORKERS and PROCESS_TIMEOUT environment variables are valid integers.")

        # Re-raise the exception to prevent the application from starting with invalid config
        raise ValueError(f"Invalid application configuration: {e}") from e

# Example usage (optional, for testing the loader directly)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        config = load_app_config()
        print("\nLoaded Configuration:")
        print(config.model_dump_json(indent=2))
    except ValueError as exc:
        print(f"\nFailed to load configuration: {exc}")