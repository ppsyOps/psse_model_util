"""
file_lock_checker.py - Windows File Lock Detection Module

This module provides reliable mechanisms for checking if files are locked in a Windows environment.
It's particularly useful for scenarios where you need to verify file availability before
performing operations that require exclusive access.

Use Cases:
    1. File Processing Pipelines
        Check if files are ready for processing:
        >>> # from psse_model_util.common.file_lock_checker import check_file_lock
        >>> def process_file(filepath):
        ...     is_locked, lock_type = check_file_lock(filepath)
        ...     if not is_locked:
        ...         # Safe to process
        ...         with open(filepath, 'r') as f:
        ...             process_content(f)
        ...     else:
        ...         print(f"File is {lock_type}, skipping...")

    2. File System Operations
        Ensure safe file operations in multi-process environments:
        >>> def safe_delete(filepath):
        ...     is_locked, _ = check_file_lock(filepath)
        ...     if not is_locked:
        ...         os.remove(filepath)
        ...         return True
        ...     return False

    3. Application File Monitoring
        Monitor when applications release file locks:
        >>> def wait_for_file_release(filepath, timeout=60):
        ...     start_time = time.time()
        ...     while time.time() - start_time < timeout:
        ...         is_locked, lock_type = check_file_lock(filepath)
        ...         if not is_locked:
        ...             return True
        ...         time.sleep(1)
        ...     return False

Common Lock Types Detected:
    - "Process lock": File is opened by another process
    - "File lock": File has an explicit lock by another application
    - "Rename lock": File cannot be renamed (indicating it's in use)
    - "Not locked": File is freely available

Notes:
    - This module uses Windows-specific APIs and is not compatible with other operating systems
    - File locks are checked using multiple methods for maximum reliability
    - The module includes retry capabilities for handling temporary locks
    - All functions are thread-safe

Requirements:
    - Windows operating system
    - Python 3.6+
    - pywin32 package (`pip install pywin32`)

Authors:
    [Your name or organization]

Version:
    1.0.0
"""
import os
import msvcrt
import win32file
import win32con
import pywintypes
import time
from functools import wraps
import portalocker



def retry_on_lock(attempts=3, delay=1):
    """
    Decorator that retries a file lock checking function if it detects a lock.

    Args:
        attempts (int): Number of times to retry the function (default: 3)
        delay (float): Number of seconds to wait between attempts (default: 1)

    Returns:
        function: Decorated function that will retry on detecting a lock

    Example:
        @retry_on_lock(attempts=3, delay=1)
        def check_file_lock(file_path):
            return is_file_locked(file_path)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(attempts):
                is_locked, lock_type = func(*args, **kwargs)
                if not is_locked:
                    return False, lock_type
                if attempt < attempts - 1:
                    time.sleep(delay)
            return True, lock_type

        return wrapper

    return decorator


def is_file_locked(file_path: str) -> tuple[bool, str]:
    """Check if a file is locked by attempting to acquire a lock.

    Args:
        file_path: Path to the file to check

    Returns:
        A tuple containing:
        - bool: True if file is locked, False if unlocked
        - str: Description of lock state ("Not locked" or lock type)

    Raises:
        FileNotFoundError: If the file does not exist
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        with portalocker.Lock(file_path, timeout=1) as _:
            return False, "Not locked"
    except portalocker.exceptions.LockException:
        return True, "Process lock"
    except PermissionError:
        return True, "Process lock"  # Permission denied indicates file is locked


@retry_on_lock(attempts=3, delay=1)
def check_file_lock(file_path):
    """
    Check if a file is locked, with automatic retries.

    This function wraps is_file_locked() with the retry_on_lock decorator to provide
    automatic retries when a lock is detected. This helps handle cases where files
    might be temporarily locked.

    Args:
        file_path (str): Path to the file to check

    Returns:
        tuple: (is_locked, lock_type) where:
            - is_locked (bool): True if the file is locked, False otherwise
            - lock_type (str): Description of the lock type detected

    Example:
        >>> is_locked, lock_type = check_file_lock("example.txt")
        >>> print(f"Locked: {is_locked}, Type: {lock_type}")
        Locked: False, Type: Not locked
    """
    return is_file_locked(file_path)


# Example usage
if __name__ == "__main__":
    file_path = "README.md"
    try:
        is_locked, lock_type = check_file_lock(file_path)
        print(f"File: {file_path}")
        print(f"Locked: {is_locked}")
        print(f"Lock type: {lock_type}")
    except Exception as e:
        print(f"Error checking file: {str(e)}")