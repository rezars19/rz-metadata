"""
RZ Autometadata - Rename Engine
Logic for bulk renaming files with a prefix + sequential number pattern.
Example: prefix="bg" → bg1.jpg, bg2.jpg, bg3.jpg
"""

import os
import shutil


def preview_rename(file_paths, prefix, start_number=1):
    """Generate preview of renamed files without actually renaming.

    Args:
        file_paths: List of absolute file paths
        prefix: Prefix string (e.g. "bg")
        start_number: Starting number (default 1)

    Returns:
        List of tuples: [(original_path, original_name, new_name), ...]
    """
    result = []
    for i, file_path in enumerate(file_paths):
        original_name = os.path.basename(file_path)
        ext = os.path.splitext(original_name)[1].lower()
        number = start_number + i
        new_name = f"{prefix}{number}{ext}"
        result.append((file_path, original_name, new_name))
    return result


def validate_rename(rename_pairs):
    """Validate rename pairs for issues.

    Args:
        rename_pairs: List of tuples from preview_rename

    Returns:
        dict with keys:
            valid: bool - whether it's safe to proceed
            duplicates: list of duplicate new names
            errors: list of error messages
    """
    new_names = [pair[2] for pair in rename_pairs]
    seen = {}
    duplicates = []
    errors = []

    for i, name in enumerate(new_names):
        name_lower = name.lower()
        if name_lower in seen:
            if name_lower not in [d.lower() for d in duplicates]:
                duplicates.append(name)
        else:
            seen[name_lower] = i

    if duplicates:
        errors.append(f"Duplicate names found: {', '.join(duplicates)}")

    # Check for invalid characters
    invalid_chars = set('\\/:*?"<>|')
    for _, _, new_name in rename_pairs:
        name_no_ext = os.path.splitext(new_name)[0]
        bad = [c for c in name_no_ext if c in invalid_chars]
        if bad:
            errors.append(f"Invalid characters in '{new_name}': {''.join(bad)}")
            break

    return {
        "valid": len(errors) == 0,
        "duplicates": duplicates,
        "errors": errors
    }


def execute_rename(rename_pairs):
    """Execute the rename operation.

    Args:
        rename_pairs: List of tuples (original_path, original_name, new_name)

    Returns:
        dict with keys:
            success: int - number of successfully renamed files
            failed: list of (filename, error_message) tuples
            history: list of (new_path, original_path) for undo
    """
    success = 0
    failed = []
    history = []

    for original_path, original_name, new_name in rename_pairs:
        try:
            directory = os.path.dirname(original_path)
            new_path = os.path.join(directory, new_name)

            # Skip if source doesn't exist
            if not os.path.exists(original_path):
                failed.append((original_name, "File not found"))
                continue

            # Skip if target already exists (and it's not the same file)
            if os.path.exists(new_path) and os.path.normpath(new_path) != os.path.normpath(original_path):
                failed.append((original_name, f"Target '{new_name}' already exists"))
                continue

            os.rename(original_path, new_path)
            history.append((new_path, original_path))
            success += 1

        except Exception as e:
            failed.append((original_name, str(e)))

    return {
        "success": success,
        "failed": failed,
        "history": history
    }


def undo_rename(history):
    """Undo a previous rename operation.

    Args:
        history: List of (new_path, original_path) tuples from execute_rename

    Returns:
        dict with keys:
            success: int
            failed: list of (filename, error_message)
    """
    success = 0
    failed = []

    for new_path, original_path in reversed(history):
        try:
            if os.path.exists(new_path):
                os.rename(new_path, original_path)
                success += 1
            else:
                failed.append((os.path.basename(new_path), "File not found"))
        except Exception as e:
            failed.append((os.path.basename(new_path), str(e)))

    return {
        "success": success,
        "failed": failed
    }
