# job_store.py - Defines job storage mechanisms (in-memory implementation)

import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Tuple
from pathlib import Path

# Import necessary models
from models import Job, JobStatus, AggregatedResult, JobError, ActiveJobSummary

logger = logging.getLogger(__name__)

# --- Abstract Base Class (or Protocol) for Job Stores ---

class BaseJobStore(ABC):
    """
    Abstract base class defining the interface for job storage.
    Implementations will handle the actual storage (e.g., in-memory, Redis, DB).
    """

    @abstractmethod
    # Add use_meta_intelligence parameter
    def create_job(self, document_name: str, input_file_path: Path, job_dir: Path, user_prompt: str, output_format: str, use_meta_intelligence: bool) -> Job:
        """Creates a new job record and returns the initial Job object."""
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieves a job by its ID."""
        pass

    @abstractmethod
    def update_job_status(self, job_id: str, status: JobStatus, progress: Optional[float] = None) -> bool:
        """Updates the status and progress of a job."""
        pass

    @abstractmethod
    def add_job_error(self, job_id: str, code: str, message: str, context: Optional[Dict] = None, recoverable: bool = False) -> bool:
        """Adds an error record to a job."""
        pass

    @abstractmethod
    def set_job_results(self, job_id: str, results: AggregatedResult) -> bool:
        """Sets the final results for a completed job."""
        pass

    @abstractmethod
    def get_active_jobs(self, limit: int = 50) -> List[ActiveJobSummary]:
        """Retrieves a summary list of recent or active jobs."""
        pass

    @abstractmethod
    def count_active_jobs(self) -> int:
        """Returns the count of jobs not in a final state (Completed/Error)."""
        pass

    @abstractmethod
    def cleanup_job_data(self, job_id: str):
        """Perform any necessary cleanup for a job's stored data (optional)."""
        # For in-memory, this might just remove the entry after some time.
        # For file-based, it might delete temporary directories.
        pass


# --- In-Memory Implementation ---

class InMemoryJobStore(BaseJobStore):
    """
    An in-memory implementation of the job store using a dictionary.
    Suitable for single-instance deployments or testing.
    NOTE: Job data is lost when the application restarts.
    """
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock() # Basic thread safety for dictionary access
        logger.info("Initialized InMemoryJobStore.")

    # Add use_meta_intelligence parameter
    def create_job(self, document_name: str, input_file_path: Path, job_dir: Path, user_prompt: str, output_format: str, use_meta_intelligence: bool) -> Job:
        """Creates a new job record in the in-memory dictionary."""
        import uuid # Import uuid here as it's only needed for job creation
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            document_name=document_name,
            user_prompt=user_prompt, # Pass user_prompt
            output_format=output_format,
            use_meta_intelligence=use_meta_intelligence, # Pass use_meta_intelligence
            input_file_path=str(input_file_path),
            job_dir=str(job_dir),
            status=JobStatus.CREATED
        )
        with self._lock:
            self._jobs[job_id] = job
        logger.info(f"Created and stored new job {job_id} for '{document_name}' in memory.")
        return job # Return a copy? For now return the object itself

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieves a job by its ID from the in-memory dictionary."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                logger.debug(f"Retrieved job {job_id} from memory.")
                # Return a copy to prevent external modification? Pydantic models are mutable.
                # For simplicity, returning the direct object reference now.
                return job
            else:
                logger.warning(f"Job {job_id} not found in memory store.")
                return None

    def update_job_status(self, job_id: str, status: JobStatus, progress: Optional[float] = None) -> bool:
        """Updates the status and progress of a job in the dictionary."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                old_status = job.status
                job.update_status(status, progress) # Use the helper method on the Job model
                logger.info(f"Updated job {job_id} status from {old_status} to {status} (Progress: {job.progress:.1f}%).")
                return True
            else:
                logger.error(f"Failed to update status for non-existent job {job_id}.")
                return False

    def add_job_error(self, job_id: str, code: str, message: str, context: Optional[Dict] = None, recoverable: bool = False) -> bool:
        """Adds an error record to a job in the dictionary."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.add_error(code, message, context, recoverable) # Use helper method
                logger.warning(f"Added error to job {job_id}: Code={code}, Message='{message[:100]}...', Recoverable={recoverable}. New status: {job.status}")
                return True
            else:
                logger.error(f"Failed to add error for non-existent job {job_id}.")
                return False

    def set_job_results(self, job_id: str, results: AggregatedResult) -> bool:
        """Sets the final results for a completed job in the dictionary."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.set_results(results) # Use helper method
                logger.info(f"Set final results for job {job_id}. Status set to {job.status}.")
                return True
            else:
                logger.error(f"Failed to set results for non-existent job {job_id}.")
                return False

    def get_active_jobs(self, limit: int = 50) -> List[ActiveJobSummary]:
        """Retrieves a summary list of recent/active jobs from memory."""
        summaries = []
        with self._lock:
            # Sort jobs by creation time descending to get recent ones
            sorted_jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            count = 0
            for job in sorted_jobs:
                if count >= limit:
                    break
                # Create the summary object
                summary = ActiveJobSummary(
                    job_id=job.job_id,
                    status=job.status.value, # Use the string value of the enum
                    document_name=job.document_name,
                    progress=job.progress,
                    created_at=job.created_at,
                    updated_at=job.updated_at
                )
                summaries.append(summary)
                count += 1
        logger.debug(f"Retrieved {len(summaries)} active/recent job summaries (limit {limit}).")
        return summaries

    def count_active_jobs(self) -> int:
        """Counts jobs not in a final state."""
        count = 0
        final_states = {JobStatus.COMPLETED, JobStatus.ERROR, JobStatus.CANCELLED}
        with self._lock:
            for job in self._jobs.values():
                if job.status not in final_states:
                    count += 1
        logger.debug(f"Counted {count} active (non-final state) jobs.")
        return count

    def cleanup_job_data(self, job_id: str):
        """Removes a job entry from the in-memory store."""
        # In a real scenario, you might implement TTL or periodic cleanup.
        # Here, we just provide a way to remove it explicitly if needed.
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                logger.info(f"Removed job {job_id} data from in-memory store.")
            else:
                logger.warning(f"Attempted to cleanup non-existent job {job_id} from memory.")


# Example Usage (optional)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    store = InMemoryJobStore()
    temp_dir = Path("./temp_jobstore_test")
    temp_dir.mkdir(exist_ok=True)
    input_file = temp_dir / "input.txt"
    input_file.touch()
    job_dir = temp_dir / "job-123"
    job_dir.mkdir(exist_ok=True)


    print("--- Testing Job Creation ---")
    # Update example usage call signature
    job1 = store.create_job("doc1.pdf", input_file, job_dir, "Prompt 1", "json", False)
    job2 = store.create_job("doc2.docx", input_file, job_dir, "Prompt 2", "text", True)
    print(f"Created Job 1: {job1.job_id} ({job1.status})")
    print(f"Created Job 2: {job2.job_id} ({job2.status})")
    print(f"Active Job Count: {store.count_active_jobs()}") # Should be 2

    print("\n--- Testing Get Job ---")
    retrieved_job1 = store.get_job(job1.job_id)
    print(f"Retrieved Job 1: Exists? {retrieved_job1 is not None}")
    print(f"Retrieved Job NonExistent: Exists? {store.get_job('non-existent-id') is not None}")

    print("\n--- Testing Status Update ---")
    store.update_job_status(job1.job_id, JobStatus.PROCESSING, progress=50.5)
    retrieved_job1 = store.get_job(job1.job_id)
    print(f"Job 1 Status: {retrieved_job1.status}, Progress: {retrieved_job1.progress}")

    print("\n--- Testing Add Error ---")
    store.add_job_error(job2.job_id, "CONVERSION_FAILED", "LibreOffice timed out", recoverable=False)
    retrieved_job2 = store.get_job(job2.job_id)
    print(f"Job 2 Status: {retrieved_job2.status}")
    print(f"Job 2 Errors: {retrieved_job2.errors}")
    print(f"Active Job Count: {store.count_active_jobs()}") # Should be 1 (job1 is processing)

    print("\n--- Testing Set Results ---")
    # Create dummy results
    dummy_results = AggregatedResult(
        job_id=job1.job_id,
        processing_summary={"total_pages": 1},
        pages=[]
    )
    store.set_job_results(job1.job_id, dummy_results)
    retrieved_job1 = store.get_job(job1.job_id)
    print(f"Job 1 Status: {retrieved_job1.status}")
    print(f"Job 1 Results Set: {retrieved_job1.results is not None}")
    print(f"Active Job Count: {store.count_active_jobs()}") # Should be 0

    print("\n--- Testing Get Active Jobs ---")
    active_summaries = store.get_active_jobs(limit=5)
    print(f"Retrieved {len(active_summaries)} summaries:")
    for summary in active_summaries:
        print(f"  - {summary.job_id} ({summary.status})") # Should show job2 then job1

    print("\n--- Testing Cleanup ---")
    store.cleanup_job_data(job1.job_id)
    store.cleanup_job_data(job2.job_id)
    print(f"Job 1 Exists: {store.get_job(job1.job_id) is not None}")
    print(f"Job 2 Exists: {store.get_job(job2.job_id) is not None}")

    # Cleanup dummy file/dir
    import shutil
    shutil.rmtree(temp_dir)
    print(f"\nCleaned up test directory: {temp_dir}")