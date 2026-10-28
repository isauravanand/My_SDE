import hashlib
import re
from pathlib import PurePosixPath

from app.schemas.execution import FileChangeMetadata, PatchValidationResult

# Sensitive file and directory patterns rejected by default
PROTECTED_PATH_PATTERNS = [
    re.compile(r"^\.git(/|$)"),
    re.compile(r"^\.env(\..+)?$"),
    re.compile(r"(^|/)(secrets?|credentials?|service_account)\.(json|yaml|yml|toml)$"),
    re.compile(r"(\.(pem|key|pfx|pkcs12)|(^|/)(id_rsa|id_ed25519))$"),
    re.compile(r"^\.github/workflows/"),
]

# Regex to match git diff headers
DIFF_HEADER_REGEX = re.compile(r"^diff --git a/(.*?) b/(.*?)$", re.MULTILINE)
HUNK_HEADER_REGEX = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class PatchValidationError(Exception):
    """Raised when a patch fails syntax or security validation."""

    pass


class PatchValidator:
    """Validates unified diff patches against strict path, security, and resource boundaries."""

    @classmethod
    def validate_patch(
        cls,
        patch_text: str,
        max_bytes: int = 512000,
        max_files: int = 20,
    ) -> PatchValidationResult:
        """
        Performs comprehensive validation of the provided unified diff.
        Returns a PatchValidationResult with parsed statistics.
        Raises PatchValidationError if any security or format rule is violated.
        """
        if not patch_text or not patch_text.strip():
            raise PatchValidationError("Patch content cannot be empty.")

        # 1. Encoding and Size validation
        encoded_bytes = patch_text.encode("utf-8", errors="replace")
        if len(encoded_bytes) > max_bytes:
            raise PatchValidationError(
                f"Patch exceeds maximum allowed size ({len(encoded_bytes)} bytes > {max_bytes} bytes)."
            )

        patch_hash = hashlib.sha256(encoded_bytes).hexdigest()

        # 2. Binary Diff Detection
        if "GIT binary patch" in patch_text or "Binary files differ" in patch_text:
            raise PatchValidationError("Binary file modifications are forbidden in patches.")

        # 3. Symlink Creation / Mode Escape Detection
        if re.search(r"\b120000\b", patch_text):
            raise PatchValidationError("Symlink creation or modification is strictly forbidden.")

        # 4. Parse file headers
        headers = list(DIFF_HEADER_REGEX.finditer(patch_text))
        if not headers:
            # Check if this is a standard diff with --- and +++
            if not ("--- " in patch_text and "+++ " in patch_text):
                raise PatchValidationError("Malformed patch: No git diff or unified diff headers found.")

        # Parse detailed file blocks
        changed_files_map: dict[str, FileChangeMetadata] = {}
        total_additions = 0
        total_deletions = 0

        # Split patch into file sections by diff --git
        sections = re.split(r"(?=^diff --git )", patch_text, flags=re.MULTILINE)
        sections = [s for s in sections if s.strip()]

        if len(sections) > max_files:
            raise PatchValidationError(
                f"Patch modifies {len(sections)} files, exceeding limit of {max_files} files."
            )

        for sec in sections:
            header_match = DIFF_HEADER_REGEX.search(sec)
            if not header_match:
                continue

            path_a = header_match.group(1).strip()
            path_b = header_match.group(2).strip()

            target_path = path_b if path_b != "/dev/null" else path_a

            # 5. Path Traversal & Absolute Path Validation
            for p in (path_a, path_b):
                if p == "/dev/null":
                    continue
                if p.startswith("/") or p.startswith("\\") or (len(p) > 1 and p[1] == ":"):
                    raise PatchValidationError(f"Absolute path '{p}' is not allowed in patch.")
                if ".." in p or p.startswith("./"):
                    raise PatchValidationError(f"Path traversal detected in path '{p}'.")

                # Normalize using PurePosixPath to detect traversal
                norm = PurePosixPath(p)
                if any(part == ".." for part in norm.parts):
                    raise PatchValidationError(f"Path traversal detected in path '{p}'.")

            # 6. Protected Paths Validation
            for pattern in PROTECTED_PATH_PATTERNS:
                if pattern.search(target_path) or (path_a != "/dev/null" and pattern.search(path_a)):
                    raise PatchValidationError(
                        f"Patch attempts to modify protected file or directory: '{target_path}'"
                    )

            # Determine change type
            change_type = "modify"
            if "new file mode" in sec or path_a == "/dev/null":
                change_type = "add"
            elif "deleted file mode" in sec or path_b == "/dev/null":
                change_type = "delete"
            elif "rename from" in sec:
                change_type = "rename"

            # Count additions and deletions in hunks
            additions = 0
            deletions = 0
            for line in sec.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    additions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1

            total_additions += additions
            total_deletions += deletions

            if change_type == "modify" and deletions > 10 and additions == 0:
                raise PatchValidationError(
                    f"Patch for '{target_path}' deleted {deletions} lines without adding replacement content (truncated patch)."
                )

            changed_files_map[target_path] = FileChangeMetadata(
                file_path=target_path,
                change_type=change_type,
                additions=additions,
                deletions=deletions,
                old_path=path_a if path_a != "/dev/null" else None,
                new_path=path_b if path_b != "/dev/null" else None,
            )

        if not changed_files_map:
            raise PatchValidationError("No valid file modifications found in patch.")

        return PatchValidationResult(
            is_valid=True,
            error_message=None,
            patch_hash=patch_hash,
            changed_files=list(changed_files_map.values()),
            changed_files_count=len(changed_files_map),
            additions_count=total_additions,
            deletions_count=total_deletions,
        )
