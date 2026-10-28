from app.rag.filtering import ExclusionReason, FileFilter


def test_supported_file_types():
    filter_engine = FileFilter(max_bytes=100_000)

    # Valid code files
    assert filter_engine.evaluate_path("src/index.js").accepted is True
    assert filter_engine.evaluate_path("src/index.js").language == "javascript"

    assert filter_engine.evaluate_path("app/main.py").accepted is True
    assert filter_engine.evaluate_path("app/main.py").language == "python"

    assert filter_engine.evaluate_path("web/App.tsx").accepted is True
    assert filter_engine.evaluate_path("web/App.tsx").language == "typescript"

    assert filter_engine.evaluate_path("queries/schema.sql").accepted is True
    assert filter_engine.evaluate_path("queries/schema.sql").language == "sql"

    assert filter_engine.evaluate_path("Dockerfile").accepted is True
    assert filter_engine.evaluate_path("Dockerfile").language == "dockerfile"


def test_directory_exclusions():
    filter_engine = FileFilter()

    # Excluded directories
    res_node = filter_engine.evaluate_path("node_modules/express/index.js")
    assert res_node.accepted is False
    assert res_node.reason == ExclusionReason.DIRECTORY_EXCLUDED

    res_git = filter_engine.evaluate_path(".git/HEAD")
    assert res_git.accepted is False
    assert res_git.reason == ExclusionReason.DIRECTORY_EXCLUDED

    res_venv = filter_engine.evaluate_path(".venv/lib/python3.10/site.py")
    assert res_venv.accepted is False
    assert res_venv.reason == ExclusionReason.DIRECTORY_EXCLUDED

    res_dist = filter_engine.evaluate_path("dist/bundle.js")
    assert res_dist.accepted is False
    assert res_dist.reason == ExclusionReason.DIRECTORY_EXCLUDED


def test_secret_file_exclusions():
    filter_engine = FileFilter()

    # .env files
    assert filter_engine.evaluate_path(".env").accepted is False
    assert filter_engine.evaluate_path(".env").reason == ExclusionReason.SECRET_FILE
    assert filter_engine.evaluate_path(".env.production").accepted is False
    assert filter_engine.evaluate_path("backend/.env.local").accepted is False

    # Private keys
    assert filter_engine.evaluate_path("id_rsa").accepted is False
    assert filter_engine.evaluate_path("id_rsa").reason == ExclusionReason.SECRET_FILE
    assert filter_engine.evaluate_path("certs/server.pem").accepted is False
    assert filter_engine.evaluate_path("keys/app.key").accepted is False
    assert filter_engine.evaluate_path("config/credentials.json").accepted is False


def test_binary_and_compiled_exclusions():
    filter_engine = FileFilter()

    assert filter_engine.evaluate_path("src/app.exe").accepted is False
    assert filter_engine.evaluate_path("src/app.exe").reason == ExclusionReason.BINARY_OR_COMPILED

    assert filter_engine.evaluate_path("assets/logo.png").accepted is False
    assert filter_engine.evaluate_path("data.sqlite").accepted is False
    assert filter_engine.evaluate_path("lib.so").accepted is False


def test_lockfile_and_minified_exclusions():
    filter_engine = FileFilter()

    assert filter_engine.evaluate_path("package-lock.json").accepted is False
    assert filter_engine.evaluate_path("package-lock.json").reason == ExclusionReason.LOCKFILE_OR_MINIFIED

    assert filter_engine.evaluate_path("pnpm-lock.yaml").accepted is False
    assert filter_engine.evaluate_path("Cargo.lock").accepted is False
    assert filter_engine.evaluate_path("static/app.min.js").accepted is False


def test_file_size_limits():
    filter_engine = FileFilter(max_bytes=1000)

    # Within limit
    assert filter_engine.evaluate_path("main.py", file_size=500).accepted is True

    # Exceeds limit
    res_large = filter_engine.evaluate_path("main.py", file_size=2000)
    assert res_large.accepted is False
    assert res_large.reason == ExclusionReason.FILE_TOO_LARGE


def test_content_level_secret_and_binary_detection():
    filter_engine = FileFilter()

    # Null bytes (binary file with .txt extension)
    binary_content = b"Some normal text\x00\x01\x02more binary"
    res_bin = filter_engine.evaluate_content("notes.txt", binary_content)
    assert res_bin.accepted is False
    assert res_bin.reason == ExclusionReason.BINARY_OR_COMPILED

    # Embedded RSA private key header in text file
    key_content = b"-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA..."
    res_key = filter_engine.evaluate_content("test_key.txt", key_content)
    assert res_key.accepted is False
    assert res_key.reason == ExclusionReason.SECRET_FILE

    # Normal python content
    normal_py = b"def add(a, b):\n    return a + b\n"
    res_normal = filter_engine.evaluate_content("math_utils.py", normal_py)
    assert res_normal.accepted is True
    assert res_normal.language == "python"


def test_path_traversal_detection():
    filter_engine = FileFilter()

    res = filter_engine.evaluate_path("../../etc/passwd")
    assert res.accepted is False
    assert res.reason == ExclusionReason.PATH_TRAVERSAL
