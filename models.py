# models.py - Data models and enumerations for EveryPage Pure

from pydantic import BaseModel, Field, field_validator, HttpUrl
from typing import Dict, List, Optional, Any, Tuple, Union # Added Union
from enum import Enum
from datetime import datetime
import json

# --- Configuration Model ---

class AppSettings(BaseModel):
    """Application configuration settings loaded from environment variables."""
    api_keys: List[str] = Field(default=["everypage-9d207bf0-10f5-4d8f-a479-22ff5aeff8d1"])
    gemini_api_key: str = ""
    gemini_api_url: HttpUrl = Field(default="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent")
    # REMOVED fixed_processing_prompt_template - will be provided by user
    max_workers: int = 5
    process_timeout: int = 90 # seconds
    temp_dir_base: str = "/tmp/everypage_pure"
    libreoffice_command: str = "libreoffice"
    pdftoppm_command: str = "pdftoppm"
    pdfinfo_command: str = "pdfinfo"
    log_level: str = "INFO"


# --- Job Status and Error Models ---

class JobStatus(str, Enum):
    """Possible states of a document processing job."""
    CREATED = "created"
    QUEUED = "queued"
    VALIDATING = "validating"
    CONVERTING = "converting"
    PROCESSING = "processing"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled" # Added for completeness, though not used in initial workflow

class JobError(BaseModel):
    """Standardized representation of job processing errors."""
    code: str # e.g., "CONVERSION_FAILED", "API_ERROR", "VALIDATION_ERROR"
    message: str
    context: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    recoverable: bool = False # Indicates if the workflow might proceed despite the error


# --- Generic Extraction Model (From AI) ---

class PageResultData(BaseModel):
    """Represents the potentially variable JSON structure returned by the LLM based on user prompt."""
    # We cannot define fixed fields anymore. Use a generic Dict.
    # Pydantic automatically handles Dict[str, Any] for arbitrary JSON objects.
    # We might need more robust handling later if non-JSON output is allowed.
    data: Dict[str, Any] = Field(..., description="Arbitrary JSON data returned by the LLM.")

    # Allow extra fields if the user's prompt defines them
    class Config:
        extra = 'allow'

    # No complex validators needed for a single string field

class PageProcessingStatus(str, Enum):
    """Status for individual page processing."""
    SUCCESS = "success"
    MOCK_SUCCESS = "mock_success"
    ERROR_API = "error_api"          # Error calling the LLM API
    ERROR_PARSING = "error_parsing"    # LLM response wasn't valid JSON
    ERROR_VALIDATION = "error_validation" # JSON structure didn't match PageResultData
    ERROR_TIMEOUT = "error_timeout"    # Request to LLM timed out
    ERROR_IMAGE_ENCODING = "error_image_encoding" # Failed to read/encode image
    ERROR_UNKNOWN = "error_unknown"    # Other unexpected errors during page processing


class PageProcessingResult(BaseModel):
    """Model for the result of processing a single page."""
    page_number: int
    status: PageProcessingStatus
    # Data can now be a Dict or potentially raw string if JSON parsing fails/isn't requested
    data: Optional[Union[Dict[str, Any], str]] = None # Holds the result data (dict or raw string) if successful
    error_message: Optional[str] = None
    raw_response: Optional[str] = None # Store raw response on failure for debugging
    processed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# --- Aggregated Job Result Model ---

class AggregatedResult(BaseModel):
    """Structure for the final aggregated results."""
    job_id: str
    processing_summary: Dict[str, Any] # Contains metadata like page counts, timing, prompt etc.
    pages: List[PageProcessingResult] # List of results for each page


# --- Core Job Tracking Model ---

class Job(BaseModel):
    """Model for tracking document processing jobs in the job store."""
    job_id: str
    status: JobStatus = JobStatus.CREATED
    document_name: str
    user_prompt: Optional[str] = None
    output_format: str = "json" # Store the requested output format
    use_meta_intelligence: bool = False # Flag for the new feature
    input_file_path: Optional[str] = None # Path where the uploaded file is temporarily stored
    job_dir: Optional[str] = None # Path to the job-specific temporary directory
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: float = 0.0
    results: Optional[AggregatedResult] = None # Stores final aggregated results
    errors: List[JobError] = Field(default_factory=list) # Use default factory for lists

    def update_status(self, status: JobStatus, progress: Optional[float] = None) -> None:
        """Helper method to update job status and progress."""
        self.status = status
        if progress is not None:
            # Clamp progress between 0 and 100
            self.progress = max(0.0, min(100.0, float(progress)))
        self.updated_at = datetime.now().isoformat()
        if status == JobStatus.COMPLETED:
            self.completed_at = self.updated_at
            self.progress = 100.0
        elif status == JobStatus.ERROR:
            self.completed_at = self.updated_at # Mark completion time even on error
             # Keep last known progress on error

    def add_error(self, code: str, message: str, context: Optional[Dict[str, Any]] = None, recoverable: bool = False) -> None:
        """Helper method to add an error to the job's error list."""
        error = JobError(code=code, message=message, context=context, recoverable=recoverable)
        self.errors.append(error)
        # If the error is not recoverable, set the job status to ERROR
        if not recoverable:
            self.update_status(JobStatus.ERROR)

    def set_results(self, results: AggregatedResult) -> None:
        """Helper method to set the final results and mark job as completed."""
        self.results = results
        self.update_status(JobStatus.COMPLETED) # Setting results implies completion


# --- API Response Models ---

class ScanResponse(BaseModel):
    """Response model for the initial scan request."""
    job_id: str
    message: str = "Document scan job created successfully."

class JobStatusResponse(BaseModel):
    """Response model for job status requests (/jobs/{job_id})."""
    job_id: str
    status: str # Use the string value of JobStatus enum
    document_name: str
    progress: float
    created_at: str
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    results: Optional[AggregatedResult] = None # Embed full results if completed
    errors: Optional[List[JobError]] = None

class ActiveJobSummary(BaseModel):
    """A lighter summary of a job for the /jobs/active endpoint."""
    job_id: str
    status: str
    document_name: str
    progress: float
    created_at: str
    updated_at: Optional[str] = None

class HealthCheckResponse(BaseModel):
    """Response model for the /health endpoint."""
    status: str # e.g., "healthy", "degraded"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0.0" # Consider making this dynamic later
    active_jobs_count: int
    dependencies: Dict[str, str] # e.g., {"libreoffice": "available", "pdftoppm": "missing"}
    gemini_status: str # e.g., "configured", "mock_mode"