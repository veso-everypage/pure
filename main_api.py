# main_api.py - FastAPI application entry point for EveryPage Pure

import logging
import os
import time # <-- ADDED IMPORT
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import (
    FastAPI, File, UploadFile, Depends, HTTPException, status, BackgroundTasks, Request, Form
)
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Import modules created in previous steps
from config_loader import load_app_config
from models import (
    AppSettings, ScanResponse, JobStatusResponse, HealthCheckResponse,
    JobStatus, ActiveJobSummary, Job  # Import Job model for type hinting
)
from api_security import api_key_query, api_key_header, validate_api_key # Import schemes and validator
from job_store import BaseJobStore, InMemoryJobStore
from workflow_orchestrator import process_document_workflow
from external_commands import check_command_availability

# --- Configuration Loading & Basic Setup ---

try:
    config: AppSettings = load_app_config()
except ValueError as e:
    # Configuration failed validation, critical error
    logging.basicConfig(level="ERROR", format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.critical(f"CRITICAL ERROR: Failed to load application configuration. Exiting. Error: {e}")
    # In a real deployment, you might exit or raise a more specific startup exception
    # For simplicity here, we'll let it potentially crash later if config is accessed.
    # Or raise SystemExit(1) # Uncomment to force exit on config error
    raise SystemExit(f"Configuration Error: {e}")


# --- Logging Setup ---
# Configure logging AFTER loading config, using the specified level
log_level = config.log_level.upper()
numeric_level = getattr(logging, log_level, logging.INFO) # Default to INFO if invalid level
logging.basicConfig(
    level=numeric_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logger.info(f"Logging configured at level: {log_level}")


# --- Global Objects ---
# Instantiate the job store (using In-Memory for now)
job_store: BaseJobStore = InMemoryJobStore()

# Create the FastAPI app instance
app = FastAPI(
    title="EveryPage Pure API",
    description="Processes documents page-by-page using a fixed AI Vision prompt.",
    version="1.0.0", # Consider making this dynamic
    # Add OpenAPI tags if desired for better docs organization
)

# --- CORS Middleware ---
# Allow all origins for simplicity in this example. Restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specify origins like ["http://localhost:8000", "http://127.0.0.1:8000"]
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# --- API Key Dependency Factory ---
# This factory creates the actual dependency function used by endpoints,
# injecting the valid API keys from the loaded configuration.
def create_api_key_dependency(valid_keys: List[str]):
    async def get_current_api_key(
        # FastAPI injects values from the request based on the Security schemes
        key_from_query: Optional[str] = Depends(api_key_query),
        key_from_header: Optional[str] = Depends(api_key_header),
    ) -> str:
        """Dependency instance that validates the key against configured keys."""
        # Prioritize header key if both are provided (common practice)
        provided_key = key_from_header or key_from_query

        if validate_api_key(provided_key, valid_keys):
            # Return the validated key (might be useful for logging/auditing later)
            return provided_key
        else:
            logger.warning(f"Unauthorized access attempt: Invalid or missing API Key.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API Key",
                headers={"WWW-Authenticate": "Header"}, # Indicate header auth preferred/supported
            )
    return get_current_api_key

# Create the dependency instance using the loaded config
# Endpoints will use `APIKey = Depends(require_api_key)`
require_api_key = create_api_key_dependency(config.api_keys)


# --- Static Files Mounting (for Web UI) ---
# This will be done *after* API routes are defined below to avoid conflicts

# --- Event Handlers (Startup/Shutdown) ---

@app.on_event("startup")
async def startup_event():
    """Tasks to perform when the application starts."""
    logger.info("Application startup initiated.")
    # Ensure base temporary directory exists
    base_temp_dir = Path(config.temp_dir_base)
    try:
        base_temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Base temporary directory ensured: {base_temp_dir}")
    except OSError as e:
        logger.error(f"Failed to create base temporary directory '{base_temp_dir}': {e}. Processing might fail.")
        # Depending on severity, you might want to prevent startup

    # Check for external command availability (optional, provides early feedback)
    check_command_availability(config.libreoffice_command)
    check_command_availability(config.pdftoppm_command)
    check_command_availability(config.pdfinfo_command)

    logger.info("Application startup complete.")


# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def read_root():
    """Serves the main web interface HTML file."""
    ui_path = Path("web_interface.html")
    if ui_path.is_file():
        return FileResponse(ui_path)
    else:
        # Fallback if the HTML file is missing
        logger.warning("web_interface.html not found. Serving basic message.")
        return HTMLResponse("<html><body><h1>EveryPage Pure API</h1><p>Web interface file not found.</p></body></html>")

# REMOVED the problematic /{filename:path} route


@app.get("/health", response_model=HealthCheckResponse, tags=["Status"])
async def health_check(api_key: str = Depends(require_api_key)):
    """Performs a health check of the API and its dependencies."""
    logger.info(f"Health check requested (API Key ending '...{api_key[-4:]}').")
    dependencies_status = {
        "libreoffice": "available" if check_command_availability(config.libreoffice_command) else "missing",
        "pdftoppm": "available" if check_command_availability(config.pdftoppm_command) else "missing",
        "pdfinfo": "available" if check_command_availability(config.pdfinfo_command) else "missing",
    }
    overall_status = "healthy"
    if "missing" in dependencies_status.values():
        overall_status = "degraded" # Indicate potential issues

    gemini_status = "configured" if config.gemini_api_key else "mock_mode"
    active_jobs = job_store.count_active_jobs()

    return HealthCheckResponse(
        status=overall_status,
        active_jobs_count=active_jobs,
        dependencies=dependencies_status,
        gemini_status=gemini_status
    )

@app.post("/scan", response_model=ScanResponse, status_code=status.HTTP_202_ACCEPTED, tags=["Processing"])
async def scan_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The document file to process (e.g., PDF, DOCX, ODT)."),
    user_prompt: str = Form(..., description="The user-defined prompt to use for processing."),
    output_format: str = Form("json", description="Desired output format ('json' or 'text')."),
    use_meta_intelligence: str = Form("false", description="Whether to enable two-pass meta intelligence ('true' or 'false')."),
    api_key: str = Depends(require_api_key)
):
    """
    Accepts a document file, creates a processing job, and starts the workflow in the background.
    """
    logger.info(f"Scan request received for file '{file.filename}' (Size: {file.size}, Type: {file.content_type}). API Key: ...{api_key[-4:]}. Prompt: '{user_prompt[:100]}...'")

    # Create a job-specific directory within the base temp directory
    job_id_temp = f"job_{int(time.time() * 1000)}_{os.urandom(4).hex()}" # Temp ID for dir name
    job_dir = Path(config.temp_dir_base) / job_id_temp
    upload_dir = job_dir / "upload"
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created job directory: {job_dir}")
    except OSError as e:
        logger.error(f"Failed to create job directory '{job_dir}': {e}")
        raise HTTPException(status_code=500, detail="Failed to create temporary directory for processing.")

    # Sanitize filename (optional, but good practice)
    # Simple sanitization: replace spaces, remove unsafe chars. Improve as needed.
    safe_filename = "".join(c if c.isalnum() or c in ['.', '-', '_'] else '_' for c in file.filename)
    if not safe_filename: safe_filename = "uploaded_file" # Fallback
    input_file_path = upload_dir / safe_filename

    # Save the uploaded file
    try:
        with open(input_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Saved uploaded file to: {input_file_path}")
    except Exception as e:
        logger.error(f"Failed to save uploaded file '{input_file_path}': {e}", exc_info=True)
        # Clean up job directory if save fails
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Could not save uploaded file: {e}")
    finally:
        # Ensure the file pointer is closed
        await file.close()


    # Register the job in the store
    try:
        job = job_store.create_job(
            document_name=file.filename or "Unnamed Document",
            user_prompt=user_prompt,
            output_format=output_format,
            # Convert string "true"/"false" to boolean
            use_meta_intelligence=(use_meta_intelligence.lower() == 'true'),
            input_file_path=input_file_path,
            job_dir=job_dir
        )
        job_id = job.job_id
        logger.info(f"Registered job {job_id} for '{job.document_name}'.")
    except Exception as e:
         logger.error(f"Failed to register job in store: {e}", exc_info=True)
         # Clean up saved file and directory
         shutil.rmtree(job_dir, ignore_errors=True)
         raise HTTPException(status_code=500, detail=f"Failed to create processing job: {e}")


    # Add the processing task to the background
    background_tasks.add_task(
        process_document_workflow,
        job_id=job_id,
        job_store=job_store,
        config=config
    )
    logger.info(f"Enqueued background processing task for job {job_id}.")

    # Update initial job status to QUEUED
    job_store.update_job_status(job_id, JobStatus.QUEUED, progress=0.0)

    # Return the job ID to the client
    return ScanResponse(job_id=job_id)


@app.get("/jobs/active", response_model=List[ActiveJobSummary], tags=["Status"])
async def get_active_jobs_summary(
    limit: int = 50, # Optional query parameter to limit results
    api_key: str = Depends(require_api_key)
):
    """Returns a summary list of the most recent or currently active jobs."""
    logger.debug(f"Request received for active jobs summary (limit {limit}). API Key: ...{api_key[-4:]}")
    try:
        active_jobs = job_store.get_active_jobs(limit=limit)
        return active_jobs
    except Exception as e:
        logger.error(f"Error retrieving active jobs summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve active jobs.")


@app.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["Status"])
async def get_job_status(job_id: str, api_key: str = Depends(require_api_key)):
    """Retrieves the status, progress, and results (if completed) of a specific job."""
    logger.debug(f"Status request received for job {job_id}. API Key: ...{api_key[-4:]}")
    job = job_store.get_job(job_id)
    if not job:
        logger.warning(f"Job status request failed: Job {job_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job with ID '{job_id}' not found.")

    # Construct the response using the Job model data
    response = JobStatusResponse(
        job_id=job.job_id,
        status=job.status.value, # Use the string value of the enum
        document_name=job.document_name,
        progress=job.progress,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        results=job.results, # Embed full results if available
        errors=job.errors if job.errors else None # Return errors if they exist
    )
    return response


# --- Mount Static Files (AFTER API routes) ---
# Serve files from the current directory (".")
# html=True allows serving index.html for the root path of the mount
# Check_dir=False prevents startup error if dir doesn't exist (though "." always exists)
app.mount("/", StaticFiles(directory=".", html=True, check_dir=False), name="static")

# --- Main Execution Guard ---
# Allows running directly with uvicorn for development:
# uvicorn main_api:app --reload
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn development server...")
    # Use host 0.0.0.0 to be accessible externally (e.g., within Docker)
    # Use port 8000 by default
    uvicorn.run(
        "main_api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)), # Allow port override via env var
        reload=True, # Enable auto-reload for development
        log_level=config.log_level.lower() # Pass log level to uvicorn
    )