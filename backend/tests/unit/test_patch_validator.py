import pytest

from app.execution.patch.validator import PatchValidationError, PatchValidator

VALID_PATCH = """diff --git a/src/calculator.py b/src/calculator.py
--- a/src/calculator.py
+++ b/src/calculator.py
@@ -1,5 +1,7 @@
 def add(a: int, b: int) -> int:
-    return a - b
+    # Fixed addition logic
+    return a + b
+
 def subtract(a: int, b: int) -> int:
     return a - b
"""

VALID_MULTI_FILE_PATCH = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
 import os
+import sys
 print("Hello")
diff --git a/tests/test_app.py b/tests/test_app.py
new file mode 100644
--- /dev/null
+++ b/tests/test_app.py
@@ -0,0 +1,2 @@
+def test_dummy():
+    assert True
"""


def test_valid_patch_validation():
    result = PatchValidator.validate_patch(VALID_PATCH)
    assert result.is_valid is True
    assert result.changed_files_count == 1
    assert result.additions_count == 3
    assert result.deletions_count == 1
    assert result.changed_files[0].file_path == "src/calculator.py"
    assert result.changed_files[0].change_type == "modify"
    assert result.patch_hash is not None


def test_valid_multi_file_patch():
    result = PatchValidator.validate_patch(VALID_MULTI_FILE_PATCH)
    assert result.is_valid is True
    assert result.changed_files_count == 2
    paths = {f.file_path for f in result.changed_files}
    assert "src/app.py" in paths
    assert "tests/test_app.py" in paths


def test_empty_patch_rejection():
    with pytest.raises(PatchValidationError, match="cannot be empty"):
        PatchValidator.validate_patch("")

    with pytest.raises(PatchValidationError, match="cannot be empty"):
        PatchValidator.validate_patch("   \n\t  ")


def test_absolute_path_rejection():
    diff_abs = """diff --git a//etc/passwd b//etc/passwd
--- a//etc/passwd
+++ b//etc/passwd
@@ -1,1 +1,2 @@
+root::0:0:root:/root:/bin/bash
"""
    with pytest.raises(PatchValidationError, match="Absolute path"):
        PatchValidator.validate_patch(diff_abs)


def test_path_traversal_rejection():
    diff_traversal = """diff --git a/src/../../etc/passwd b/src/../../etc/passwd
--- a/src/../../etc/passwd
+++ b/src/../../etc/passwd
@@ -1,1 +1,2 @@
+malicious
"""
    with pytest.raises(PatchValidationError, match="Path traversal detected"):
        PatchValidator.validate_patch(diff_traversal)


def test_symlink_escape_rejection():
    diff_symlink = """diff --git a/link b/link
new file mode 120000
--- /dev/null
+++ b/link
@@ -0,0 +1,1 @@
+/etc/passwd
"""
    with pytest.raises(PatchValidationError, match="Symlink creation or modification is strictly forbidden"):
        PatchValidator.validate_patch(diff_symlink)


def test_binary_diff_rejection():
    diff_bin = """diff --git a/image.png b/image.png
GIT binary patch
literal 128
zc$@#&
"""
    with pytest.raises(PatchValidationError, match="Binary file modifications are forbidden"):
        PatchValidator.validate_patch(diff_bin)


@pytest.mark.parametrize(
    "forbidden_path",
    [
        ".env",
        ".env.production",
        ".env.local",
        ".git/config",
        ".git/HEAD",
        "secrets.json",
        "credentials.yaml",
        "service_account.json",
        "id_rsa",
        "server.pem",
        "private.key",
        ".github/workflows/deploy.yml",
    ],
)
def test_protected_path_modifications(forbidden_path):
    diff_protected = f"""diff --git a/{forbidden_path} b/{forbidden_path}
--- a/{forbidden_path}
+++ b/{forbidden_path}
@@ -1,1 +1,2 @@
+NEW_SECRET=12345
"""
    with pytest.raises(PatchValidationError, match="attempts to modify protected file"):
        PatchValidator.validate_patch(diff_protected)


def test_patch_size_limit_rejection():
    large_diff = "diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n@@ -1,1 +1,2 @@\n" + ("+line\n" * 5000)
    with pytest.raises(PatchValidationError, match="exceeds maximum allowed size"):
        PatchValidator.validate_patch(large_diff, max_bytes=2048)


def test_changed_file_count_limit():
    multi_file = ""
    for i in range(10):
        multi_file += f"""diff --git a/file_{i}.py b/file_{i}.py
--- a/file_{i}.py
+++ b/file_{i}.py
@@ -1,1 +1,2 @@
+# change {i}
"""
    with pytest.raises(PatchValidationError, match="exceeding limit of 5 files"):
        PatchValidator.validate_patch(multi_file, max_files=5)
