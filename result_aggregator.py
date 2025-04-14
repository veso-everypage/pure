# result_aggregator.py - Combines individual page results into a final structure

import logging
import time
from typing import List, Dict, Any
from datetime import datetime

# Import necessary models
from models import PageProcessingResult, AggregatedResult, PageProcessingStatus, AppSettings

logger = logging.getLogger(__name__)

def aggregate_processing_results(
    job_id: str,
    document_name: str,
    page_results: List[PageProcessingResult],
    pdf_metadata: Dict[str, Any],
    user_prompt: str, # Use the actual user prompt for the summary
    start_timestamp: float # Unix timestamp when processing started
) -> AggregatedResult:
    """
    Aggregates individual page processing results into a final structured result.
    (Pure Function)

    Args:
        job_id: The unique identifier for the processing job.
        document_name: The original name of the document.
        page_results: A list of PageProcessingResult objects, one for each page processed.
        pdf_metadata: A dictionary containing metadata extracted from the PDF (e.g., page count from pdfinfo).
        user_prompt: The prompt template provided by the user for this job.
        start_timestamp: The time.time() value when the overall processing workflow began.

    Returns:
        An AggregatedResult object containing the summary and detailed page results.
    """
    logger.info(f"Aggregating results for job {job_id} ('{document_name}')...")
    aggregation_start_time = time.time()

    total_pages = len(page_results)
    # Use pdf_metadata page count as authoritative if available, otherwise use length of results list
    reported_total_pages = pdf_metadata.get('pages', total_pages)

    processed_pages = 0
    successful_pages = 0
    mock_pages = 0
    pages_with_errors = 0

    for result in page_results:
        processed_pages += 1 # Count every result received
        if result.status == PageProcessingStatus.SUCCESS:
            successful_pages += 1
        elif result.status == PageProcessingStatus.MOCK_SUCCESS:
            successful_pages += 1 # Count mock as successful for summary purposes
            mock_pages += 1
        else:
            pages_with_errors += 1

    end_timestamp = time.time()
    total_processing_time_seconds = round(end_timestamp - start_timestamp, 2)
    aggregation_time_seconds = round(end_timestamp - aggregation_start_time, 3)

    # Store a snippet of the user prompt used in the summary
    prompt_snippet = user_prompt[:200] + "..." if len(user_prompt) > 200 else user_prompt

    processing_summary = {
        "document_name": document_name,
        "source_total_pages": reported_total_pages, # Pages reported by pdfinfo
        "processed_pages_count": processed_pages,   # Number of results in the list
        "successful_pages_count": successful_pages,
        "mock_pages_count": mock_pages,
        "pages_with_errors_count": pages_with_errors,
        "processing_prompt_used_snippet": prompt_snippet, # Show snippet of actual prompt
        "aggregation_timestamp": datetime.now().isoformat(),
        "total_processing_time_seconds": total_processing_time_seconds,
        "aggregation_time_seconds": aggregation_time_seconds,
        "pdf_metadata": pdf_metadata, # Include the raw parsed metadata
        # Add more summary fields as needed (e.g., average page processing time)
    }

    # Sort page results by page number just in case they arrive out of order
    sorted_page_results = sorted(page_results, key=lambda p: p.page_number)

    aggregated_result = AggregatedResult(
        job_id=job_id,
        processing_summary=processing_summary,
        pages=sorted_page_results
    )

    logger.info(f"Result aggregation complete for job {job_id}. Processed {processed_pages}/{reported_total_pages} pages ({successful_pages} success, {pages_with_errors} errors).")
    return aggregated_result

# Example Usage (optional)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Create dummy data for testing
    test_job_id = "job-123-test"
    test_doc_name = "example_document.pdf"
    test_start_time = time.time() - 15.5 # Simulate 15.5 seconds elapsed

    # Dummy User Prompt
    test_user_prompt = "Analyze page {page_number}. Extract summary."

    # Dummy PDF Metadata
    test_pdf_metadata = {
        "title": "Example Document",
        "author": "Test User",
        "pages": 3,
        "encrypted": False,
        "page_size": "612 x 792 pts (letter)",
        "page_width_pts": 612.0,
        "page_height_pts": 792.0
    }

    # Dummy Page Results
    page_results_list = [
        PageProcessingResult(
            page_number=1,
            status=PageProcessingStatus.SUCCESS,
            # Assuming old PageResultData structure for example simplicity here
            data={"summary": "Summary page 1", "key_points": ["P1 K1"], "topics": ["T1"]}
        ),
        PageProcessingResult(
            page_number=3, # Out of order to test sorting
            status=PageProcessingStatus.ERROR_API,
            error_message="API call failed: 500 Server Error"
        ),
         PageProcessingResult(
            page_number=2,
            status=PageProcessingStatus.MOCK_SUCCESS,
            data={"mock_result": "Mock summary page 2"} # Using new mock structure
        ),
    ]

    print("Aggregating results...")
    final_result = aggregate_processing_results(
        job_id=test_job_id,
        document_name=test_doc_name,
        page_results=page_results_list,
        pdf_metadata=test_pdf_metadata,
        user_prompt=test_user_prompt, # Pass user prompt
        start_timestamp=test_start_time
    )

    print("\n--- Aggregated Result ---")
    print(final_result.model_dump_json(indent=2))
    print("-----------------------")

    # Verify summary counts
    summary = final_result.processing_summary
    print(f"\nVerification:")
    print(f"  Total Pages (Reported): {summary['source_total_pages']} == 3? {summary['source_total_pages'] == 3}")
    print(f"  Processed Pages: {summary['processed_pages_count']} == 3? {summary['processed_pages_count'] == 3}")
    print(f"  Successful Pages: {summary['successful_pages_count']} == 2? {summary['successful_pages_count'] == 2}")
    print(f"  Mock Pages: {summary['mock_pages_count']} == 1? {summary['mock_pages_count'] == 1}")
    print(f"  Error Pages: {summary['pages_with_errors_count']} == 1? {summary['pages_with_errors_count'] == 1}")
    print(f"  Page 1 Status: {final_result.pages[0].status} == SUCCESS? {final_result.pages[0].status == PageProcessingStatus.SUCCESS}")
    print(f"  Page 2 Status: {final_result.pages[1].status} == MOCK_SUCCESS? {final_result.pages[1].status == PageProcessingStatus.MOCK_SUCCESS}")
    print(f"  Page 3 Status: {final_result.pages[2].status} == ERROR_API? {final_result.pages[2].status == PageProcessingStatus.ERROR_API}")