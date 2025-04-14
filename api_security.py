# api_security.py - API Key validation logic and FastAPI dependency

import logging
from typing import List, Optional
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader, APIKeyQuery

# --- Security Schemes ---
# Define how clients can provide the API key: either in the query ('api-key') or header ('x-api-key')

api_key_query = APIKeyQuery(name="api-key", auto_error=False, description="API Key for authentication (Query Parameter)")
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False, description="API Key for authentication (Header)")

logger = logging.getLogger(__name__)

# --- Core Validation Logic (Pure Function) ---

def validate_api_key(provided_key: Optional[str], valid_keys: List[str]) -> bool:
    """
    Checks if the provided API key is present and valid against a list of known keys.

    Args:
        provided_key: The key received from the request (could be None).
        valid_keys: The list of valid API keys loaded from configuration.

    Returns:
        True if the key is valid, False otherwise.
    """
    if not provided_key:
        logger.debug("API Key validation failed: No key provided.")
        return False
    if not valid_keys:
        logger.warning("API Key validation skipped: No valid keys configured in settings.")
        # Depending on security policy, you might want to return False here always.
        # For now, allowing access if no keys are configured (useful for local dev maybe).
        # Consider changing this for production hardening.
        return True # Or False if you want to enforce key presence always
    is_valid = provided_key in valid_keys
    if not is_valid:
        logger.warning(f"API Key validation failed: Invalid key provided ('{provided_key[:4]}...').")
    else:
         logger.debug("API Key validation successful.")
    return is_valid

# --- FastAPI Dependency (Impure due to Security and HTTPException) ---

async def get_api_key_dependency(
    # These parameters are automatically populated by FastAPI based on the security schemes
    api_key_query_param: Optional[str] = Security(api_key_query),
    api_key_header_param: Optional[str] = Security(api_key_header),
    # We'll need the valid keys from config, but dependencies can't directly access
    # the global config easily. We'll inject the config in main_api.py when using this.
    # For now, define the signature. How to pass valid_keys will be handled at usage time.
    # **Workaround:** We'll define a factory function in main_api.py to create this dependency
    # with the config baked in.
) -> str:
    """
    FastAPI dependency to extract and validate the API key from query or header.

    Raises:
        HTTPException (401 Unauthorized): If the key is missing or invalid.

    Returns:
        The validated API key if successful.
    """
    # This dependency needs access to the `valid_keys` list from AppSettings.
    # Since dependencies are created at startup, we cannot directly pass the config object.
    # A common pattern is to use a factory or closure in the main app setup
    # to create an instance of this dependency function with the required config.
    # See main_api.py for how this is implemented.

    # Placeholder for the actual logic which will be executed by the instance created by the factory.
    # The factory will ensure `valid_keys` is available in the scope.
    raise NotImplementedError("This dependency should be created via a factory in main_api.py")


# --- Factory Function Example (Illustrative - Actual use in main_api.py) ---
# This shows the pattern that will be used in main_api.py

# def create_api_key_dependency(valid_keys: List[str]):
#     async def dependency_instance(
#         api_key_query_param: Optional[str] = Security(api_key_query),
#         api_key_header_param: Optional[str] = Security(api_key_header),
#     ) -> str:
#         if validate_api_key(api_key_query_param, valid_keys):
#             return api_key_query_param
#         if validate_api_key(api_key_header_param, valid_keys):
#             return api_key_header_param
#
#         logger.warning("Unauthorized access attempt: Invalid or missing API Key.")
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid or missing API Key",
#             headers={"WWW-Authenticate": "Header"}, # Indicate header auth preferred
#         )
#     return dependency_instance