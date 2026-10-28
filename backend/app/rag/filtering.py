import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


class ExclusionReason(str, Enum):
    DIRECTORY_EXCLUDED = "directory_excluded"
    SECRET_FILE = "secret_file"
    BINARY_OR_COMPILED = "binary_or_compiled"
    LOCKFILE_OR_MINIFIED = "lockfile_or_minified"
    GENERATED_OR_CACHE = "generated_or_cache"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_TYPE = "unsupported_type"
    PATH_TRAVERSAL = "path_traversal"


@dataclass(frozen=True)
class FilterDecision:
    accepted: bool
    reason: ExclusionReason | None = None
    language: str | None = None
    detail: str | None = None


class FileFilter:
    """Centralized, configurable security policy for file exclusion and language identification."""

    DEFAULT_MAX_BYTES = 512 * 1024  # 512 KB

    # Directories that must never be traversed or indexed
    EXCLUDED_DIRS = {
        ".git",
        ".github",  # workflow files are usually fine, but avoid hidden metadata
        ".venv",
        "venv",
        "env",
        ".env",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        "dist",
        "build",
        "out",
        "target",
        ".next",
        ".nuxt",
        "coverage",
        ".coverage",
        "htmlcov",
        "vendor",
        "bower_components",
        ".idea",
        ".vscode",
        ".turbo",
        ".serverless",
        "bin",
        "obj",
    }

    # Lockfiles and minified/bundled files that add noise rather than retrieval value
    EXCLUDED_FILENAMES = {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "uv.lock",
        "poetry.lock",
        "cargo.lock",
        "gemfile.lock",
        "composer.lock",
        "mix.lock",
        "pipfile.lock",
        ".ds_store",
        "thumbs.db",
    }

    # Secret and credential filenames / extensions
    SECRET_PATTERNS = [
        re.compile(r"^\.env(\..+)?$", re.IGNORECASE),
        re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$", re.IGNORECASE),
        re.compile(r".*\.(pem|key|pkcs12|pfx|p12|keystore|jks|der|crt)$", re.IGNORECASE),
        re.compile(r"^(credentials|secret|secrets|token|tokens)\.(json|yaml|yml|txt|env)$", re.IGNORECASE),
        re.compile(r".*(private.*key|service.*account|client.*secret).*\.(json|pem|key)$", re.IGNORECASE),
        re.compile(r"^(htpasswd|shadow|master\.key)$", re.IGNORECASE),
    ]

    # Binary/compiled extensions
    BINARY_EXTENSIONS = {
        ".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".img",
        ".tar", ".gz", ".tgz", ".zip", ".7z", ".rar", ".bz2", ".xz",
        ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war", ".ear",
        ".o", ".obj", ".a", ".lib",
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp", ".tiff",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".mp3", ".mp4", ".mov", ".avi", ".wav", ".flac", ".ogg",
        ".woff", ".woff2", ".ttf", ".eot", ".otf",
        ".sqlite", ".sqlite3", ".db", ".parquet", ".arrow",
    }

    # Minified / generated bundle extensions
    MINIFIED_EXTENSIONS = {
        ".min.js", ".min.css", ".bundle.js", ".map", ".bundle.css",
    }

    # Language mapping by file extension
    LANGUAGE_MAP = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".scss": "scss",
        ".sass": "sass",
        ".less": "less",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
        ".markdown": "markdown",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".go": "go",
        ".rs": "rust",
        ".sql": "sql",
        ".sh": "shell",
        ".bash": "shell",
        ".zsh": "shell",
        ".rb": "ruby",
        ".php": "php",
        ".proto": "protobuf",
        ".graphql": "graphql",
        ".gql": "graphql",
        ".toml": "toml",
        ".xml": "xml",
        ".txt": "text",
        ".dockerfile": "dockerfile",
    }

    def __init__(self, max_bytes: int | None = None):
        self.max_bytes = max_bytes or self.DEFAULT_MAX_BYTES

    def evaluate_path(self, file_path: str, file_size: int | None = None) -> FilterDecision:
        """Evaluate path metadata before downloading content."""
        clean_path = file_path.replace("\\", "/").strip().lstrip("/")

        # 1. Path traversal & symlink escape safety
        parts = clean_path.split("/")
        if ".." in parts or any(part.startswith("/") for part in parts):
            return FilterDecision(
                accepted=False,
                reason=ExclusionReason.PATH_TRAVERSAL,
                detail="Path contains directory traversal characters",
            )

        # 2. Excluded directories
        for part in parts[:-1]:
            if part.lower() in self.EXCLUDED_DIRS:
                return FilterDecision(
                    accepted=False,
                    reason=ExclusionReason.DIRECTORY_EXCLUDED,
                    detail=f"Directory '{part}' is in excluded list",
                )

        filename = parts[-1]
        filename_lower = filename.lower()

        # 3. Exact lockfiles and generated files
        if filename_lower in self.EXCLUDED_FILENAMES:
            return FilterDecision(
                accepted=False,
                reason=ExclusionReason.LOCKFILE_OR_MINIFIED,
                detail=f"Lockfile '{filename}' is excluded",
            )

        # 4. Secret file patterns (e.g. .env, id_rsa, *.pem)
        for pattern in self.SECRET_PATTERNS:
            if pattern.match(filename):
                return FilterDecision(
                    accepted=False,
                    reason=ExclusionReason.SECRET_FILE,
                    detail="Matches secret credential pattern",
                )

        # 5. Minified bundles
        for min_ext in self.MINIFIED_EXTENSIONS:
            if filename_lower.endswith(min_ext):
                return FilterDecision(
                    accepted=False,
                    reason=ExclusionReason.LOCKFILE_OR_MINIFIED,
                    detail=f"Minified bundle '{min_ext}' is excluded",
                )

        # 6. Binary extensions
        ext = PurePosixPath(clean_path).suffix.lower()
        if ext in self.BINARY_EXTENSIONS:
            return FilterDecision(
                accepted=False,
                reason=ExclusionReason.BINARY_OR_COMPILED,
                detail=f"Binary extension '{ext}' is excluded",
            )

        # 7. File size check (if known beforehand)
        if file_size is not None and file_size > self.max_bytes:
            return FilterDecision(
                accepted=False,
                reason=ExclusionReason.FILE_TOO_LARGE,
                detail=f"File size {file_size} exceeds {self.max_bytes} bytes",
            )

        # Special filenames without standard extensions
        if filename_lower == "dockerfile" or filename_lower.startswith("dockerfile."):
            return FilterDecision(accepted=True, language="dockerfile")
        if filename_lower in ("makefile", "gnumakefile"):
            return FilterDecision(accepted=True, language="makefile")

        # 8. Supported language mapping
        language = self.LANGUAGE_MAP.get(ext)
        if not language:
            return FilterDecision(
                accepted=False,
                reason=ExclusionReason.UNSUPPORTED_TYPE,
                detail=f"Unsupported file extension '{ext}'",
            )

        return FilterDecision(accepted=True, language=language)

    def evaluate_content(self, file_path: str, content: bytes) -> FilterDecision:
        """Validate downloaded content for secrets, null bytes (binary), and size limits."""
        # 1. Size check
        if len(content) > self.max_bytes:
            return FilterDecision(
                accepted=False,
                reason=ExclusionReason.FILE_TOO_LARGE,
                detail=f"Content size {len(content)} exceeds maximum limit {self.max_bytes}",
            )

        # 2. Binary / Null byte check in first 2048 bytes
        sample = content[:2048]
        if b"\x00" in sample:
            return FilterDecision(
                accepted=False,
                reason=ExclusionReason.BINARY_OR_COMPILED,
                detail="Null bytes detected in file content",
            )

        # 3. Content-level secret scan
        try:
            text_sample = sample.decode("utf-8", errors="ignore")
        except Exception:
            text_sample = ""

        secret_signatures = [
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----",
            "-----BEGIN CERTIFICATE-----",
            "AKIA[0-9A-Z]{16}",  # AWS Access Key ID
        ]
        for sig in secret_signatures:
            if re.search(sig, text_sample):
                return FilterDecision(
                    accepted=False,
                    reason=ExclusionReason.SECRET_FILE,
                    detail=f"Sensitive secret signature detected: {sig[:20]}...",
                )

        # Re-verify path metadata to resolve language
        return self.evaluate_path(file_path, file_size=len(content))
