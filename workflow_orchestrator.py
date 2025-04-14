# workflow_orchestrator.py - Coordinates the document processing workflow

import asyncio
import logging
import time
import shutil
import json # For meta-context synthesis
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

# Import models and functions from other modules
from models import (
    AppSettings, Job, JobStatus, PageProcessingResult, PageProcessingStatus,
    AggregatedResult
)
from job_store import BaseJobStore
from document_converter import convert_to_pdf_libreoffice
from pdf_processor import extract_pdf_pages_as_png, extract_pdf_metadata, parse_pdfinfo_output
from image_processor import encode_image_to_base64
from ai_processor_gemini import (
    construct_gemini_payload, call_gemini_api,
    parse_gemini_response, parse_and_validate_ai_output
)
from result_aggregator import aggregate_processing_results

logger = logging.getLogger(__name__)

# --- Constants ---
META_PROMPT_TEMPLATE = """<document_analysis>
  <system>
    You are an expert document analysis AI. Your task is to analyze the first few pages of a document to understand its overall context and structure. Focus on identifying the document type, main purpose, intended audience, and key sections or topics covered in these initial pages. Keep your analysis concise.
  </system>
  <input>
    <image_data>Page {page_number} of document (initial pages)</image_data>
    <task>Analyze initial page(s) for overall document context.</task>
  </input>
  <output_format>
    <format>JSON</format>
    <structure>
    {{
      "document_type": "e.g., Invoice, Contract, Report, Presentation, Email, Other",
      "main_purpose": "Brief summary of the document's goal based on these pages.",
      "key_sections_or_topics": ["List key sections/topics observed on these pages"]
    }}
    </structure>
    <constraints>
      <constraint>Return ONLY valid JSON.</constraint>
      <constraint>Keep analysis concise and based *only* on the provided initial pages.</constraint>
    </constraints>
</document_analysis>"""

MAX_META_PAGES = 3 # Number of initial pages to scan for meta context


# --- Helper Function for Single Page Processing ---

async def _process_single_page(
    page_num: int,
    screenshot_path: Path,
    prompt_to_use: str, # Renamed from user_prompt for clarity
    output_format: str,
    job_dir: Path, # For saving individual results if needed
    config: AppSettings
) -> PageProcessingResult:
    """
    Processes a single page: encode image, call AI (or mock), parse, validate.
    Designed to be run concurrently for multiple pages.
    """
    page_start_time = time.time()
    logger.info(f"Starting processing for page {page_num} ({screenshot_path.name}).")

    # 1. Encode image
    img_base64, img_err = encode_image_to_base64(screenshot_path)
    if img_err:
        logger.error(f"Page {page_num}: Failed to encode image: {img_err}")
        return PageProcessingResult(
            page_number=page_num,
            status=PageProcessingStatus.ERROR_IMAGE_ENCODING,
            error_message=f"Failed to encode image: {img_err}"
        )

    # 2. Construct Payload
    # Note: output_format here dictates the 'Accept' header / requested response type from Gemini
    payload, prompt_err = construct_gemini_payload(img_base64, page_num, prompt_to_use, output_format, config)
    if prompt_err:
         logger.error(f"Page {page_num}: Failed to construct prompt/payload: {prompt_err}")
         return PageProcessingResult(
             page_number=page_num,
             status=PageProcessingStatus.ERROR_UNKNOWN, # Or a new status like ERROR_PROMPT_FORMAT
             error_message=f"Failed to format prompt: {prompt_err}"
         )

    # 3. Check for Mock Mode (Before API call)
    if not config.gemini_api_key:
         logger.warning(f"Page {page_num}: Mock mode enabled (no GEMINI_API_KEY). Returning placeholder.")
         # Return a simple mock structure based on requested format
         mock_data: Union[Dict, str]
         if output_format == "json":
              mock_data = {"mock_result": f"Mock JSON response for page {page_num}."}
         else:
              mock_data = f"Mock text response for page {page_num}."

         return PageProcessingResult(
             page_number=page_num,
             status=PageProcessingStatus.MOCK_SUCCESS,
             data=mock_data
         )

    # 4. Call Gemini API
    response_json, error_status, error_msg = await call_gemini_api(payload, config, page_num)
    if error_msg:
        return PageProcessingResult(
            page_number=page_num,
            status=error_status or PageProcessingStatus.ERROR_API,
            error_message=error_msg
        )

    # 5. Parse API Response to get text/content part
    extracted_text, parse_err = parse_gemini_response(response_json)
    if parse_err:
        return PageProcessingResult(
            page_number=page_num,
            status=PageProcessingStatus.ERROR_PARSING,
            error_message=parse_err,
            raw_response=str(response_json)[:1000]
        )

    # 6. Parse/Validate AI Output Content (JSON or Text) based on requested format
    requested_format = payload.get("generationConfig", {}).get("response_mime_type", "text/plain")
    result_data: Optional[Union[Dict[str, Any], str]]
    result_data, validation_status, validation_err = parse_and_validate_ai_output(
        extracted_text, page_num, requested_format
    )

    if validation_err:
        # Error occurred (e.g., failed to parse JSON when JSON was expected)
        return PageProcessingResult(
            page_number=page_num,
            status=validation_status or PageProcessingStatus.ERROR_PARSING,
            error_message=validation_err,
            raw_response=extracted_text[:1000],
            data=result_data # Still include the raw text data if parsing failed
        )

    # 7. Success Case
    page_end_time = time.time()
    logger.info(f"Page {page_num}: Processing successful in {page_end_time - page_start_time:.2f} seconds.")
    return PageProcessingResult(
        page_number=page_num,
        status=PageProcessingStatus.SUCCESS,
        data=result_data # Can be dict or string
    )


# --- Main Workflow Orchestration Function ---

async def process_document_workflow(
    job_id: str,
    job_store: BaseJobStore,
    config: AppSettings
) -> None:
    """
    Orchestrates the entire document processing workflow asynchronously.
    Includes optional two-pass meta intelligence processing.
    """
    start_timestamp = time.time()
    job: Optional[Job] = job_store.get_job(job_id)

    if not job:
        logger.error(f"Workflow cannot start: Job {job_id} not found in store.")
        return
    # Check all required fields from the Job model
    if not all([job.input_file_path, job.job_dir, job.user_prompt, job.output_format is not None, job.use_meta_intelligence is not None]):
         logger.error(f"Workflow cannot start: Job {job_id} record is incomplete.")
         job_store.add_job_error(job_id, "WORKFLOW_SETUP_ERROR", "Job record is incomplete.", recoverable=False)
         return

    input_file_path = Path(job.input_file_path)
    job_dir = Path(job.job_dir)
    pdf_path: Optional[Path] = None
    screenshot_paths: List[Path] = []
    pdf_metadata: Dict[str, Any] = {}
    page_results: List[PageProcessingResult] = []
    meta_context: str = ""

    # Define progress steps
    PROGRESS_VALIDATION = 5.0
    PROGRESS_CONVERSION = 15.0
    PROGRESS_METADATA_SCREENSHOTS = 30.0
    PROGRESS_START_META = 35.0
    PROGRESS_END_META_START_MAIN = 50.0
    PROGRESS_END_MAIN = 95.0
    PROGRESS_AGGREGATING = 98.0

    try:
        logger.info(f"Starting workflow for job {job_id} ('{job.document_name}'). MetaInt: {job.use_meta_intelligence}")

        # 1. Validation
        await asyncio.sleep(0.01)
        job_store.update_job_status(job_id, JobStatus.VALIDATING, progress=PROGRESS_VALIDATION)
        if not input_file_path.exists():
            raise ValueError(f"Input file disappeared before processing: {input_file_path}")
        logger.info(f"Job {job_id}: Input file validation successful.")

        # --- Determine if input is an image ---
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
        is_image_input = input_file_path.suffix.lower() in image_extensions

        if is_image_input:
            logger.info(f"Job {job_id}: Input file detected as image. Skipping conversion and PDF processing.")
            screenshot_paths = [input_file_path]
            pdf_metadata = {"pages": 1, "source_type": "image"}
            # Skip to the progress level where main processing starts
            job_store.update_job_status(job_id, JobStatus.PROCESSING, progress=PROGRESS_END_META_START_MAIN)
        else:
            # --- Document Processing Path ---
            # 2. Convert to PDF
            job_store.update_job_status(job_id, JobStatus.CONVERTING, progress=PROGRESS_CONVERSION)
            convert_success, pdf_path, convert_error = await convert_to_pdf_libreoffice(input_file_path, job_dir / "converted", config)
            if not convert_success or not pdf_path:
                raise RuntimeError(f"Document conversion failed: {convert_error}")
            logger.info(f"Job {job_id}: Conversion to PDF successful: {pdf_path.name}")

            # 3. Extract Metadata & 4. Generate Screenshots (can run in parallel)
            job_store.update_job_status(job_id, JobStatus.PROCESSING, progress=PROGRESS_METADATA_SCREENSHOTS) # Progress before these tasks

            meta_task = asyncio.create_task(extract_pdf_metadata(pdf_path, config))
            screenshot_task = asyncio.create_task(extract_pdf_pages_as_png(pdf_path, job_dir / "screenshots", config))

            # Wait for metadata extraction
            meta_success, meta_stdout, meta_stderr = await meta_task
            if meta_success:
                pdf_metadata = parse_pdfinfo_output(meta_stdout)
                logger.info(f"Job {job_id}: Metadata extracted. Pages: {pdf_metadata.get('pages', 'N/A')}")
            else:
                logger.warning(f"Job {job_id}: Failed to extract PDF metadata. Stderr: {meta_stderr}")
                job_store.add_job_error(job_id, "METADATA_EXTRACTION_FAILED", meta_stderr or "pdfinfo command failed.", recoverable=True)
            pdf_metadata["source_type"] = "document"

            # Wait for screenshot generation
            ss_success, screenshot_paths, ss_error = await screenshot_task
            if not ss_success or not screenshot_paths:
                raise RuntimeError(f"Screenshot generation failed: {ss_error}")
            elif ss_error:
                 logger.warning(f"Job {job_id}: Warnings during screenshot generation: {ss_error}")
                 job_store.add_job_error(job_id, "SCREENSHOT_WARNINGS", ss_error, recoverable=True)

            logger.info(f"Job {job_id}: Generated {len(screenshot_paths)} screenshots.")
            if not screenshot_paths:
                 raise RuntimeError("Screenshot generation reported success but produced no files.")
            # Progress updated before Meta Pass check


        # 5. Meta Intelligence Pass (Optional)
        if job.use_meta_intelligence and not is_image_input:
            logger.info(f"Job {job_id}: Running Meta Intelligence Pass...")
            job_store.update_job_status(job_id, JobStatus.PROCESSING, progress=PROGRESS_START_META)

            meta_pages_to_scan = min(len(screenshot_paths), MAX_META_PAGES)
            meta_tasks = []
            for i in range(meta_pages_to_scan):
                page_num = i + 1
                task = asyncio.create_task(
                    _process_single_page(
                        page_num=page_num, screenshot_path=screenshot_paths[i],
                        prompt_to_use=META_PROMPT_TEMPLATE, output_format="json",
                        job_dir=job_dir / "meta_results", config=config
                    ), name=f"Job_{job_id}_MetaPage_{page_num}"
                )
                meta_tasks.append(task)

            meta_results_raw = await asyncio.gather(*meta_tasks, return_exceptions=True)

            successful_meta_results = []
            for i, res in enumerate(meta_results_raw):
                page_num = i + 1
                if isinstance(res, Exception): logger.error(f"Job {job_id}: Error during meta scan for page {page_num}: {res}")
                elif isinstance(res, PageProcessingResult):
                    if res.status != PageProcessingStatus.SUCCESS: logger.warning(f"Job {job_id}: Meta scan page {page_num} failed: {res.status} - {res.error_message}")
                    elif res.data and isinstance(res.data, dict): successful_meta_results.append(res.data)
                else: logger.error(f"Job {job_id}: Unexpected result type during meta scan page {page_num}: {type(res)}")

            if successful_meta_results:
                 meta_context = "Document Context Summary (from first {} page(s)):\n".format(len(successful_meta_results))
                 for i, data in enumerate(successful_meta_results): meta_context += f"- Page {i+1}: {json.dumps(data)}\n"
                 meta_context = meta_context.strip()
                 logger.info(f"Job {job_id}: Synthesized meta context: {meta_context[:300]}...")
            else: logger.warning(f"Job {job_id}: Meta Intelligence scan yielded no successful results.")

            job_store.update_job_status(job_id, JobStatus.PROCESSING, progress=PROGRESS_END_META_START_MAIN)
        else:
             logger.info(f"Job {job_id}: Skipping Meta Intelligence Pass.")
             # Ensure progress is at least at the start point for main processing if skipping
             if job.status == JobStatus.PROCESSING and job.progress < PROGRESS_END_META_START_MAIN:
                 job_store.update_job_status(job_id, JobStatus.PROCESSING, progress=PROGRESS_END_META_START_MAIN)


        # 6. Main Processing Pass (All Pages)
        logger.info(f"Job {job_id}: Starting Main Processing Pass...")
        total_pages_to_process = len(screenshot_paths)
        tasks = []
        final_user_prompt = job.user_prompt

        if meta_context:
             final_user_prompt = f"DOCUMENT CONTEXT:\n{meta_context}\n\n---\n\nUSER TASK:\n{job.user_prompt}"
             logger.debug(f"Job {job_id}: Using combined prompt for main pass.")

        for i, screenshot_path in enumerate(screenshot_paths):
            page_num = i + 1
            task = asyncio.create_task(
                _process_single_page(
                    page_num=page_num, screenshot_path=screenshot_path,
                    prompt_to_use=final_user_prompt, output_format=job.output_format,
                    job_dir=job_dir / "page_results", config=config
                ), name=f"Job_{job_id}_MainPage_{page_num}"
            )
            tasks.append(task)

        completed_tasks = 0
        progress_range = PROGRESS_END_MAIN - PROGRESS_END_META_START_MAIN

        for future in asyncio.as_completed(tasks):
            try:
                result: PageProcessingResult = await future
                page_results.append(result)
                completed_tasks += 1
                current_progress = PROGRESS_END_META_START_MAIN + (completed_tasks / total_pages_to_process) * progress_range
                job_store.update_job_status(job_id, JobStatus.PROCESSING, progress=current_progress)
                logger.info(f"Job {job_id}: Completed processing page {result.page_number} (Status: {result.status}). Progress: {current_progress:.1f}%")
            except Exception as e:
                 logger.error(f"Job {job_id}: Unexpected error waiting for page processing task: {e}", exc_info=True)


        logger.info(f"Job {job_id}: Finished main processing pass for {total_pages_to_process} pages.")

        # 7. Aggregate Results
        job_store.update_job_status(job_id, JobStatus.AGGREGATING, progress=PROGRESS_AGGREGATING)
        if not page_results and total_pages_to_process > 0:
             raise RuntimeError("Aggregation failed: No page processing results were collected.")
        elif not page_results and total_pages_to_process == 0:
             logger.warning(f"Job {job_id}: No pages found to process or aggregate.")
             page_results = []

        final_results: AggregatedResult = aggregate_processing_results(
            job_id=job_id, document_name=job.document_name,
            page_results=page_results, pdf_metadata=pdf_metadata,
            user_prompt=job.user_prompt, # Pass original user prompt for summary
            start_timestamp=start_timestamp
        )

        # 8. Set Final Results and Status
        job_store.set_job_results(job_id, final_results)
        logger.info(f"Workflow for job {job_id} completed.")

    except (ValueError, RuntimeError, FileNotFoundError) as e:
        error_msg = f"Workflow for job {job_id} failed: {e}"
        logger.error(error_msg, exc_info=True)
        job_store.add_job_error(job_id, "WORKFLOW_FAILED", str(e), recoverable=False)
    except Exception as e:
        error_msg = f"Unexpected error during workflow for job {job_id}: {e.__class__.__name__} - {e}"
        logger.error(error_msg, exc_info=True)
        job_store.add_job_error(job_id, "UNEXPECTED_WORKFLOW_ERROR", str(e), recoverable=False)

    finally:
        # 9. Cleanup
        final_job_state = job_store.get_job(job_id)
        should_cleanup = True
        if final_job_state and final_job_state.status == JobStatus.ERROR:
             logger.warning(f"Job {job_id} finished with errors. Skipping cleanup of {job_dir} for debugging.")
             should_cleanup = False

        if should_cleanup:
            try:
                if input_file_path and input_file_path.exists():
                    input_file_path.unlink()
                    logger.info(f"Cleaned up input file: {input_file_path}")
            except OSError as e: logger.error(f"Error cleaning up input file {input_file_path}: {e}")
            try:
                if job_dir and job_dir.exists():
                    shutil.rmtree(job_dir)
                    logger.info(f"Cleaned up job directory: {job_dir}")
            except OSError as e: logger.error(f"Error cleaning up job directory {job_dir}: {e}")
            # Optionally remove job from store after cleanup
            # job_store.cleanup_job_data(job_id)


# Example Usage (for direct execution if needed)
if __name__ == "__main__":
    print("Workflow orchestrator module loaded. Run integration tests via main_api.py to test the workflow.")
    logging.basicConfig(level=logging.INFO)
    logger.info("To test the workflow, run the main FastAPI application and submit a document.")