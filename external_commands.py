# external_commands.py - Helper functions for running external commands

import asyncio
import logging
import shutil
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

async def run_subprocess_async(
    command: List[str],
    description: str = "External command"
) -> Tuple[int, str, str]:
    """
    Runs an external command asynchronously and returns its exit code, stdout, and stderr.

    Args:
        command: A list containing the command and its arguments.
        description: A brief description of the command for logging purposes.

    Returns:
        A tuple containing:
            - return_code (int): The exit code of the process.
            - stdout (str): The standard output, decoded as UTF-8.
            - stderr (str): The standard error, decoded as UTF-8.
    """
    cmd_str = ' '.join(command)
    logger.info(f"Running {description}: {cmd_str}")
    start_time = asyncio.get_event_loop().time()

    try:
        process = await asyncio.create_subprocess_exec(
            command[0],  # The command executable
            *command[1:], # The arguments
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout_bytes, stderr_bytes = await process.communicate()
        return_code = process.returncode

        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time

        stdout = stdout_bytes.decode('utf-8', errors='ignore').strip() if stdout_bytes else ""
        stderr = stderr_bytes.decode('utf-8', errors='ignore').strip() if stderr_bytes else ""

        if return_code == 0:
            logger.info(f"{description} completed successfully in {duration:.2f} seconds.")
            # Log snippet of stdout if needed for debugging, but can be noisy
            # if stdout: logger.debug(f"{description} stdout (first 100 chars): {stdout[:100]}...")
        else:
            logger.error(f"{description} failed with code {return_code} after {duration:.2f} seconds.")
            logger.error(f"Command: {cmd_str}")
            if stderr:
                logger.error(f"Stderr: {stderr}")
            else:
                logger.error("Stderr: (empty)")
            if stdout: # Log stdout too on failure, might contain clues
                logger.error(f"Stdout: {stdout}")


        return return_code, stdout, stderr

    except FileNotFoundError:
        logger.error(f"{description} failed: Command not found: '{command[0]}'. Ensure it's installed and in the system PATH.")
        return -1, "", f"Command not found: {command[0]}" # Use a specific code or raise? Returning for now.
    except Exception as e:
        logger.error(f"An unexpected error occurred while running {description} ('{cmd_str}'): {e}", exc_info=True)
        return -2, "", f"Unexpected error running command: {e}"


def check_command_availability(command_name: str) -> bool:
    """
    Checks if an external command is available in the system's PATH.

    Args:
        command_name: The name of the command executable (e.g., "libreoffice", "pdftoppm").

    Returns:
        True if the command is found, False otherwise.
    """
    path = shutil.which(command_name)
    if path:
        logger.info(f"Dependency check: Command '{command_name}' found at '{path}'.")
        return True
    else:
        logger.warning(f"Dependency check: Command '{command_name}' not found in PATH.")
        return False

# Example Usage (optional)
async def main():
    print("Checking command availability:")
    print(f"ls available? {check_command_availability('ls')}")
    print(f"libreoffice available? {check_command_availability('libreoffice')}")
    print(f"pdftoppm available? {check_command_availability('pdftoppm')}")
    print(f"nonexistentcommand available? {check_command_availability('nonexistentcommand')}")

    print("\nRunning 'ls -l *.py':")
    # Note: glob pattern might not work directly like this in subprocess on all OS/shells
    # Better to list files using Python if needed, or pass specific files.
    # Using a simple command like 'echo' for demonstration.
    # code, out, err = await run_subprocess_async(['ls', '-l', '*.py'], "List Python files")
    code, out, err = await run_subprocess_async(['echo', 'Hello from subprocess'], "Echo test")
    print(f"Exit Code: {code}")
    print(f"Stdout:\n{out}")
    print(f"Stderr:\n{err}")

    print("\nRunning a failing command:")
    code, out, err = await run_subprocess_async(['ls', '/nonexistentdir'], "List non-existent dir")
    print(f"Exit Code: {code}")
    print(f"Stdout:\n{out}")
    print(f"Stderr:\n{err}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    asyncio.run(main())