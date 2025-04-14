# EveryPage by Veso Labs

**A modular, user-configurable document & image processing API using Generative AI Vision.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

EveryPage provides a straightforward FastAPI backend and web interface designed to accept various document formats (or single images), process them page-by-page using **user-defined instructions** via Google's Gemini 2.0 Flash model, and return structured JSON or plain text results. It allows users to define processing tasks using a structured input UI or load pre-defined templates.

## Features

*   **Web Interface:** Clean, side-by-side UI for configuration, document/image upload, and job status tracking/results view (served from `/`).
*   **Multi-Format Input:** Accepts common document types (PDF, DOCX, ODT, PPTX, TXT, etc.) via LibreOffice conversion *and* single image files (PNG, JPG, etc.).
*   **PDF Conversion:** Automatically converts input documents to PDF.
*   **High-Resolution Page Imaging:** Generates 300 DPI PNG images for each page using `pdftoppm`.
*   **PDF Metadata Extraction:** Extracts basic metadata using `pdfinfo`.
*   **Dynamic AI Processing:** Processes each page image using Google Gemini 2.0 Flash based on user-provided instructions (constructed via UI or loaded from templates). Supports requesting JSON or plain text output.
*   **Meta Intelligence (Optional Toggle):** Performs an initial pass on the first few pages to generate document context, then uses this context along with the user's prompt for the main processing pass on all pages, potentially improving results for context-dependent tasks. (Increases processing time/cost; skipped for single image inputs).
*   **Prompt Templates:** Includes pre-defined templates for common tasks (Transcription, Summarization, Translation, Q&A, Table Extraction, Entity Extraction, Invoice Data Extraction) to simplify prompt creation.
*   **Structured/Text Output:** Aggregates results from all pages into a single JSON object (`AggregatedResult`), with each page containing the data returned by the AI (either a JSON object or plain text).
*   **Asynchronous Workflow:** Handles document processing in the background using FastAPI's `BackgroundTasks`.
*   **Modular Architecture:** Codebase organized into logical modules (see `ARCHITECTURE.md`).
*   **Simple Authentication:** Protects API endpoints with API Key authentication (header `x-api-key` or query `api-key`).
*   **Job Status Tracking:** Provides API endpoints (`/jobs/{job_id}`, `/jobs/active`) and a web UI to check job status and retrieve results.
*   **Result Downloads:** Allows downloading full job results as JSON or CSV directly from the web UI.
*   **Dockerized:** Includes an updated Dockerfile for easy containerization and deployment.

## Prerequisites

### System Dependencies

*   **LibreOffice:** Required for converting various document formats to PDF.
    *   Installation (Debian/Ubuntu): `sudo apt-get update && sudo apt-get install -y libreoffice`
*   **Poppler Utilities:** Provides `pdftoppm` (for screenshots) and `pdfinfo` (for metadata).
    *   Installation (Debian/Ubuntu): `sudo apt-get update && sudo apt-get install -y poppler-utils`
*   **Docker:** (Optional, for containerized deployment) [Install Docker](https://docs.docker.com/engine/install/)

### Python Dependencies

*   Python 3.8+
*   Required packages (install via `pip`):
    *   `fastapi`
    *   `uvicorn[standard]`
    *   `python-multipart` (for file uploads)
    *   `httpx` (for making requests to Gemini API)
    *   `pydantic` (used by FastAPI for data validation)

## Installation / Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd everypage-pure # Or your repository directory name
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install Python dependencies:**
    The required packages are listed in `requirements.txt`. Install them using:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration (Environment Variables)

The application uses environment variables for configuration:

*   **`API_KEY` (Required):** Comma-separated list of secret API keys clients must provide to access the API.
    *   Example: `export API_KEY="key1,key2"`
    *   *Default (if not set):* `everypage-9d207bf0-10f5-4d8f-a479-22ff5aeff8d1` (Change this for production!)
*   **`GEMINI_API_KEY` (Required for real processing):** Your API key for the Google Gemini API.
    *   Example: `export GEMINI_API_KEY="your-google-ai-api-key"`
    *   *If not set:* The application will run in **mock mode**, returning sample data instead of calling the actual Gemini API.
*   **`GEMINI_API_URL` (Optional):** The endpoint URL for the Gemini API.
    *   *Default:* `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent`
*   **`FIXED_PROCESSING_PROMPT`:** This environment variable is **no longer used** as prompts are user-defined via the UI.
*   **`MAX_WORKERS` (Optional):** The maximum number of concurrent tasks used for processing document pages in parallel.
    *   *Default:* `5`
*   **`PROCESS_TIMEOUT` (Optional):** Timeout in seconds for individual page processing calls to the Gemini API.
    *   *Default:* `90`
*   **`TEMP_DIR_BASE` (Optional):** Base directory for storing temporary processing files.
    *   *Default:* `/tmp/everypage_pure`
*   **`LIBREOFFICE_COMMAND` (Optional):** Path to the LibreOffice executable.
    *   *Default:* `libreoffice`
*   **`PDFTOPPM_COMMAND` (Optional):** Path to the `pdftoppm` executable.
    *   *Default:* `pdftoppm`
*   **`PDFINFO_COMMAND` (Optional):** Path to the `pdfinfo` executable.
    *   *Default:* `pdfinfo`
*   **`LOG_LEVEL` (Optional):** Logging level (e.g., DEBUG, INFO, WARNING, ERROR).
    *   *Default:* `INFO`

## Running Locally

1.  **Set Environment Variables:**
    ```bash
    export API_KEY="your-dev-api-key"
    export GEMINI_API_KEY="your-google-ai-api-key" # Or leave unset for mock mode
    # Optionally set other variables (though FIXED_PROCESSING_PROMPT is now ignored)
    ```

2.  **Run the FastAPI application using Uvicorn:**
    ```bash
    uvicorn main_api:app --host 0.0.0.0 --port 8000 --reload
    ```
    *   `main_api` refers to the Python file name (`main_api.py`).
    *   `app` refers to the FastAPI instance `app = FastAPI(...)` within that file.
    *   `--reload` enables auto-reloading during development. Remove for production.

The API and Web Interface will be available at `http://localhost:8000`. API Documentation (Swagger UI) will be at `http://localhost:8000/docs`.

## Building the Docker Image

1.  **Ensure `Dockerfile` is present** in the project root (an updated version is included):

    ```dockerfile
    # Use an official Python runtime as a parent image
    # Using Python 3.9 as a baseline, adjust if needed (e.g., 3.10, 3.11)
    FROM python:3.9-slim

    # Set the working directory in the container
    WORKDIR /app

    # Prevent interactive prompts during package installation
    ENV DEBIAN_FRONTEND=noninteractive

    # Install system dependencies required for LibreOffice and Poppler
    # Using --no-install-recommends to keep the image smaller
    RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice \
        poppler-utils \
        # Add any other essential system libraries if discovered later
     && apt-get clean \
     && rm -rf /var/lib/apt/lists/*

    # Copy the requirements file into the container first
    # This leverages Docker layer caching
    COPY requirements.txt .

    # Install Python dependencies
    RUN pip install --no-cache-dir --upgrade pip && \
        pip install --no-cache-dir -r requirements.txt

    # Copy the rest of the application code into the container
    # This includes all .py files, .html, .css, .js at the root level now
    COPY . .

    # Make port 8000 available to the world outside this container
    EXPOSE 8000

    # Define environment variables with defaults (can be overridden at runtime)
    # These should match the defaults in config_loader.py / models.py
    ENV MAX_WORKERS=5
    ENV PROCESS_TIMEOUT=90
    # REMOVED fixed prompt ENV variable
    ENV TEMP_DIR_BASE=/tmp/everypage_pure
    ENV LIBREOFFICE_COMMAND=libreoffice
    ENV PDFTOPPM_COMMAND=pdftoppm
    ENV PDFINFO_COMMAND=pdfinfo
    ENV LOG_LEVEL=INFO
    # API_KEY and GEMINI_API_KEY should be set at runtime using -e flags

    # Healthcheck (Optional but recommended)
    # Note: The default /health endpoint requires authentication.
    # A simple curl check will fail unless the endpoint is unsecured or the key is provided.
    # Consider adding an unauthenticated endpoint like /ping for basic checks if needed.
    # RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
    # HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    #   CMD curl --fail -H "x-api-key: ${API_KEY:-dummy}" http://localhost:8000/health || exit 1

    # Run main_api.py using uvicorn when the container launches
    # Listen on 0.0.0.0 to accept connections from outside the container
    # Updated entry point to main_api:app
    CMD ["uvicorn", "main_api:app", "--host", "0.0.0.0", "--port", "8000"]
    ```

2.  **Build the image:**
    ```bash
    docker build -t everypage-pure:latest .
    ```

## Deploying with Docker

1.  **Run the container:**
    ```bash
    docker run -d \
      -p 8000:8000 \
      -e API_KEY="your_production_api_key" \
      -e GEMINI_API_KEY="your_production_gemini_key" \
      # Optionally override other ENV variables like PROCESS_TIMEOUT, MAX_WORKERS etc.
      --name everypage-pure-instance \
      everypage-pure:latest
    ```
    *   `-d`: Run in detached mode (background).
    *   `-p 8000:8000`: Map port 8000 on the host to port 8000 in the container.
    *   `-e`: Set environment variables. **Crucially, set `API_KEY` and `GEMINI_API_KEY` here.**
    *   `--name`: Assign a name to the container for easier management.

The API will be accessible on your host machine at `http://<host-ip>:8000`.

## Usage

The primary way to interact with the application is via the web interface served at the root URL (`http://localhost:8000` by default).

You can also interact directly with the API endpoints using tools like `curl`, Postman, or scripting libraries. Remember to include your API key either as a query parameter (`?api-key=YOUR_KEY`) or as a header (`x-api-key: YOUR_KEY`).

### Web Interface

1.  Navigate to `http://localhost:8000` (or your deployed URL).
2.  Enter your configured `API_KEY` in the "1. Setup" card and click "Save".
3.  In the "2. Processing Instructions" card, either:
    *   Select a **Template** (like Transcription, Summarization, Extract Tables, etc.) from the dropdown to auto-fill the fields below.
    *   Or, manually fill in:
        *   **Task Description:** What the AI should do (use `{page_number}`).
        *   **Desired Output Format:** Choose JSON or Plain Text.
        *   **Example JSON Structure:** (Optional, appears if JSON is selected) Provide an example to guide the AI's output structure.
    *   Optionally, enable the **Meta Intelligence** toggle (for multi-page documents only) to perform a two-pass analysis for better context understanding.
4.  In the "3. Upload Document" card, click "Choose File" to select your document or image file. The filename will appear next to the button.
5.  Click "Start Processing".
6.  Monitor progress in the "Job Queue" and view details by clicking a job ID in the "Job Details" section on the right. The queue refreshes automatically.
7.  For successfully completed jobs, **Download Results (JSON)** and **Download Results (CSV)** buttons will appear below the job details.

### API Endpoints

**1. Health Check (`/health`)**

*   **Method:** GET
*   **Purpose:** Check if the API is running and basic dependencies are available.
*   **Example (`curl`):**
    ```bash
    curl -X GET "http://localhost:8000/health" -H "x-api-key: <YOUR_API_KEY>"
    # Or: curl -X GET "http://localhost:8000/health?api-key=<YOUR_API_KEY>"
    ```
*   **Success Response (Example):**
    ```json
    {
      "status": "healthy", // or "degraded" if dependencies missing
      "timestamp": "2025-03-24T10:00:00.123456",
      "version": "1.0.0",
      "active_jobs_count": 0,
      "dependencies": {
        "libreoffice": "available", # or "missing"
        "pdftoppm": "available",  # or "missing"
        "pdfinfo": "available"    # or "missing"
      },
      "gemini_status": "configured" # or "mock_mode"
    }
    ```

**2. Scan Document (`/scan`)**

*   **Method:** POST
*   **Purpose:** Submit a document or image file for processing with user-defined instructions.
*   **Body:** `multipart/form-data` including:
    *   `file`: The document or image file being uploaded.
    *   `user_prompt` (string): The full prompt text constructed by the UI (or sent directly), including system instructions, task description with `{page_number}` placeholder, format, structure hints, and constraints.
    *   `output_format` (string): The desired output format selected by the user (e.g., `"json"` or `"text"`).
    *   `use_meta_intelligence` (string): `"true"` or `"false"` indicating whether to use the two-pass meta feature.
*   **Example (`curl`):**
    ```bash
    # Note: Constructing the full XML-like prompt string manually for curl can be complex.
    # It's generally easier to use the web UI which handles prompt construction.
    # Example assumes you have the prompt in a variable $PROMPT_STRING
    curl -X POST "http://localhost:8000/scan" \
      -H "accept: application/json" \
      -H "x-api-key: <YOUR_API_KEY>" \
      -F "file=@/path/to/your/document.docx" \
      -F "user_prompt=$PROMPT_STRING" \
      -F "output_format=json" \
      -F "use_meta_intelligence=false" # Or true
    ```
*   **Success Response (`202 Accepted`):**
    ```json
    {
      "job_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
      "message": "Document scan job created successfully."
    }
    ```
    *   Note down the `job_id`.

**3. Get Job Status & Results (`GET /jobs/{job_id}`)**

*   **Purpose:** Check the progress of a specific job and retrieve results when completed.
*   **Example (`curl`):**
    ```bash
    curl -X GET "http://localhost:8000/jobs/<JOB_ID>" -H "x-api-key: <YOUR_API_KEY>"
    ```
*   **Response (Processing):**
    ```json
    {
      "job_id": "<JOB_ID>",
      "status": "processing", // Could also be "queued", "converting", etc.
      "document_name": "document.docx",
      "progress": 65.5,
      "created_at": "2025-03-24T10:05:00.123Z",
      "updated_at": "2025-03-24T10:07:30.456Z",
      "completed_at": null,
      "results": null,
      "errors": null
    }
    ```
*   **Response (Completed - Example with Translation):**
    ```json
    {
      "job_id": "<JOB_ID>",
      "status": "completed",
      "document_name": "document.docx",
      "progress": 100.0,
      "created_at": "2025-04-02T05:05:00.123456+00:00",
      "updated_at": "2025-04-02T05:10:00.789123+00:00",
      "completed_at": "2025-04-02T05:10:00.789123+00:00",
      "results": {
        "job_id": "<JOB_ID>",
        "processing_summary": {
          "document_name": "document.docx",
          "source_total_pages": 3,
          "processed_pages_count": 3,
          "successful_pages_count": 3,
          "mock_pages_count": 0,
          "pages_with_errors_count": 0,
          "processing_prompt_used_snippet": "Please translate the text on page...",
          "aggregation_timestamp": "2025-04-02T05:10:00.700123+00:00",
          "total_processing_time_seconds": 45.67,
          "aggregation_time_seconds": 0.05,
          "pdf_metadata": {
             "title": "Example Doc",
             "pages": 3,
             /* ... other pdfinfo fields ... */
          }
        },
        "pages": [
          {
            "page_number": 1,
            "status": "success",
            "data": {
              "translation": "Este es el texto traducido de la página 1.\nIncluye saltos de línea."
            },
            "error_message": null,
            "raw_response": null,
            "processed_at": "2025-04-02T05:08:00.111222+00:00"
          },
          {
             "page_number": 2,
             "status": "success",
             "data": {
                "translation": "Contenido de la página 2..."
             },
             /* ... other fields ... */
          },
          {
             "page_number": 3,
             "status": "error_api", // Example error
             "data": null,
             "error_message": "API call failed: ...",
             /* ... other fields ... */
          }
        ]
      },
      "errors": null
    }
    ```
*   **Response (Error - Example):**
    ```json
    {
      "job_id": "<JOB_ID>",
      "status": "error",
      "document_name": "failed_document.pdf",
      "progress": 15.0,
      "created_at": "2025-04-02T06:00:00.123456+00:00",
      "updated_at": "2025-04-02T06:01:00.789123+00:00",
      "completed_at": "2025-04-02T06:01:00.789123+00:00", // Completed time is set even on error
      "results": null,
      "errors": [
        {
          "code": "CONVERSION_FAILED",
          "message": "Conversion failed: LibreOffice could not load the source file 'failed_document.pdf'. It might be corrupted or an unsupported format. Stderr: ...",
          "context": null,
          "timestamp": "2025-04-02T06:01:00.700123+00:00",
          "recoverable": false
        }
      ]
    }
    ```

**4. Get Active Jobs Summary (`GET /jobs/active`)**

*   **Purpose:** Retrieve a list of summaries for recently created or currently processing jobs. Useful for populating the queue UI.
*   **Query Parameters:**
    *   `limit` (int, optional, default 50): Maximum number of job summaries to return.
*   **Example (`curl`):**
    ```bash
    curl -X GET "http://localhost:8000/jobs/active?limit=10" -H "x-api-key: <YOUR_API_KEY>"
    ```
*   **Success Response (Example):**
    ```json
    [
      {
        "job_id": "job-abc...",
        "status": "processing",
        "document_name": "report.docx",
        "progress": 75.0,
        "created_at": "2025-04-02T07:00:00.123Z",
        "updated_at": "2025-04-02T07:05:00.456Z"
      },
      {
        "job_id": "job-xyz...",
        "status": "queued",
        "document_name": "datasheet.pdf",
        "progress": 0.0,
        "created_at": "2025-04-02T07:01:00.789Z",
        "updated_at": null
      }
      // ... other jobs up to limit
    ]
    ```

## Project Structure

The project follows a flat structure for simplicity:

```
/
├── .DS_Store                 # macOS metadata
├── ARCHITECTURE.md           # Detailed architecture description 
├── Dockerfile                # Docker configuration 
├── PLAN.md                   # Refactoring plan
├── README.MD                 # Readme
├── ai_processor_gemini.py    # Handles Gemini API interaction
├── api_security.py           # API key validation
├── config_loader.py          # Loads environment variables
├── document_converter.py     # Handles LibreOffice conversion
├── external_commands.py      # Runs external processes
├── image_processor.py        # Image encoding
├── job_store.py              # In-memory job state management
├── main_api.py               # FastAPI app entry point
├── models.py                 # Pydantic models and enums
├── pdf_processor.py          # PDF screenshotting & metadata
├── requirements.txt          # Python dependencies
├── result_aggregator.py      # Combines page results
├── web_app.js                # Frontend JavaScript
├── web_interface.html        # Frontend HTML
├── web_styles.css            # Frontend CSS
└── workflow_orchestrator.py  # Main processing logic coordination
```

For a more detailed explanation of the architecture, see `ARCHITECTURE.md`.

## Architecture

This project uses a modular architecture designed for clarity and testability. Key components include:

*   **`main_api.py`:** The FastAPI application defining endpoints, handling requests, managing background tasks, and serving the web UI.
*   **`workflow_orchestrator.py`:** Coordinates the steps involved in processing a document.
*   **Specialized Modules:** Separate modules handle configuration (`config_loader.py`), data models (`models.py`), job state (`job_store.py`), external commands (`external_commands.py`), document conversion (`document_converter.py`), PDF processing (`pdf_processor.py`), image encoding (`image_processor.py`), AI interaction (`ai_processor_gemini.py`), and result aggregation (`result_aggregator.py`).
*   **Web UI Files:** `web_interface.html`, `web_styles.css`, and `web_app.js` provide the user interface.

See `ARCHITECTURE.md` for a detailed breakdown.

## Open Source Declaration

EveryPage Pure is an open-source project developed by Veso Labs. We believe in the power of community collaboration and welcome contributions.

## Contributing

We welcome contributions to EveryPage Pure! Here's how you can help:

1.  **Reporting Bugs:** If you find a bug, please open an issue on the GitHub repository detailing the problem, steps to reproduce, and your environment.
2.  **Suggesting Enhancements:** Have an idea for a new feature or improvement? Open an issue to discuss it.
3.  **Code Contributions:**
    *   Fork the repository.
    *   Create a new branch for your feature or bug fix (`git checkout -b feature/your-feature-name` or `bugfix/issue-number`).
    *   Make your changes. Ensure code is well-formatted (e.g., using Black) and includes necessary tests if applicable.
    *   Commit your changes with clear messages.
    *   Push your branch to your fork (`git push origin feature/your-feature-name`).
    *   Open a Pull Request (PR) against the main repository's `main` branch. Describe your changes clearly in the PR.

Please ensure your contributions align with the project's goal of providing a *streamlined, fixed-prompt* processor. For major changes or features adding significant complexity (like user-defined prompts), consider if they belong in the original EveryPage project or a different fork.

We expect all contributors to adhere to a standard code of conduct promoting respectful and constructive collaboration.

## License

This project is licensed under the MIT License. <!-- Assuming MIT, add LICENSE.md if not present -->
