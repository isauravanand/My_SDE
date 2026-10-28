import logging
import random
import time
from pathlib import Path
from typing import Any

import httpx
import jwt

from app.core.config import Settings, get_settings
from app.core.logging import redact_sensitive_data

logger = logging.getLogger(__name__)


class GitHubApiError(Exception):
    """Raised when GitHub API returns an error or is unreachable."""

    def __init__(self, message: str, status_code: int = 500, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class GitHubConfigError(GitHubApiError):
    """Raised when GitHub App is not properly configured."""

    def __init__(self, message: str = "GitHub App is not configured in this environment"):
        super().__init__(message, status_code=503)


class GitHubRateLimitError(GitHubApiError):
    """Raised when GitHub API rate limit is exceeded."""

    def __init__(self, message: str = "GitHub API rate limit exceeded", reset_at: int | None = None):
        super().__init__(message, status_code=429, details={"reset_at": reset_at})
        self.reset_at = reset_at


class GitHubApiClient:
    """Dedicated HTTP client for GitHub App and installation operations with resilient retries."""

    GITHUB_API_BASE = "https://api.github.com"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._installation_tokens: dict[int, tuple[str, float]] = {}

    @staticmethod
    def _check_rate_limit(response: httpx.Response) -> None:
        """Raise GitHubRateLimitError only if response actually represents rate limiting, otherwise handle 403 permissions."""
        is_429 = response.status_code == 429
        is_rate_limited_403 = response.status_code == 403 and (
            "rate limit" in response.text.lower()
            or response.headers.get("x-ratelimit-remaining") == "0"
        )
        if is_429 or is_rate_limited_403:
            reset_header = response.headers.get("x-ratelimit-reset")
            reset_at = int(reset_header) if reset_header and reset_header.isdigit() else None
            raise GitHubRateLimitError(reset_at=reset_at)

        if response.status_code == 403:
            error_msg = response.text
            try:
                data = response.json()
                if "message" in data:
                    error_msg = data["message"]
            except Exception:
                pass
            raise GitHubApiError(
                f"GitHub Permission Denied (403): {error_msg}. Please ensure your GitHub App has 'Read and write' permissions for Repository 'Contents' and 'Pull requests'.",
                status_code=403,
            )

    def _get_private_key_bytes(self) -> bytes:
        """Load and return GitHub App private key bytes."""
        if self.settings.GITHUB_APP_PRIVATE_KEY:
            return self.settings.GITHUB_APP_PRIVATE_KEY.encode("utf-8")
        if self.settings.GITHUB_APP_PRIVATE_KEY_PATH:
            key_path = Path(self.settings.GITHUB_APP_PRIVATE_KEY_PATH)
            if key_path.exists():
                return key_path.read_bytes()
        raise GitHubConfigError("GitHub App private key is not configured or path does not exist")

    def generate_app_jwt(self) -> str:
        """Generate a short-lived (9 min) RS256 JWT for GitHub App authentication."""
        if not self.settings.GITHUB_APP_ID:
            raise GitHubConfigError("GITHUB_APP_ID is not configured")

        now = int(time.time())
        payload = {
            "iat": now - 60,  # 60s in the past to compensate for server clock drift
            "exp": now + (9 * 60),  # Valid for 9 minutes (max allowed is 10)
            "iss": str(self.settings.GITHUB_APP_ID),
        }

        private_key = self._get_private_key_bytes()
        try:
            token = jwt.encode(payload, private_key, algorithm="RS256")
            return token
        except Exception as e:
            logger.error("Failed to sign GitHub App JWT: %s", redact_sensitive_data(str(e)))
            raise GitHubApiError(f"Failed to generate GitHub App authentication JWT: {e}") from e

    def _request_with_retry(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        json_data: Any = None,
        timeout: float = 15.0,
        max_retries: int = 3,
    ) -> httpx.Response:
        """
        Execute an HTTP request with bounded exponential backoff, randomized jitter,
        and Retry-After support for transient errors (429, 502, 503, 504).
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
                    response = client.request(method, url, headers=headers, json=json_data)
            except httpx.TimeoutException as e:
                if attempt >= max_retries:
                    raise GitHubApiError("Connection to GitHub API timed out", status_code=504) from e
                sleep_sec = (2 ** (attempt - 1)) + random.uniform(0.1, 0.4)
                logger.warning(
                    "GitHub API timeout on attempt %d/%d; retrying in %.2fs",
                    attempt, max_retries, sleep_sec
                )
                time.sleep(sleep_sec)
                continue
            except httpx.RequestError as e:
                if attempt >= max_retries:
                    raise GitHubApiError(f"Unable to reach GitHub API: {e}", status_code=502) from e
                sleep_sec = (2 ** (attempt - 1)) + random.uniform(0.1, 0.4)
                logger.warning(
                    "GitHub API network error on attempt %d/%d; retrying in %.2fs: %s",
                    attempt, max_retries, sleep_sec, redact_sensitive_data(str(e))
                )
                time.sleep(sleep_sec)
                continue

            # Transient 5xx server errors
            if response.status_code in (502, 503, 504) and attempt < max_retries:
                sleep_sec = (2 ** (attempt - 1)) + random.uniform(0.1, 0.4)
                logger.warning(
                    "GitHub API server error %d on attempt %d/%d; retrying in %.2fs",
                    response.status_code, attempt, max_retries, sleep_sec
                )
                time.sleep(sleep_sec)
                continue

            # Rate limit handling (429 or secondary 403)
            if (response.status_code == 429 or (response.status_code == 403 and "rate limit" in response.text.lower())) and attempt < max_retries:
                retry_after_hdr = response.headers.get("retry-after")
                if retry_after_hdr and retry_after_hdr.isdigit():
                    sleep_sec = min(int(retry_after_hdr), 30) + random.uniform(0.1, 0.5)
                else:
                    sleep_sec = (2 ** (attempt - 1)) + random.uniform(0.2, 0.5)
                logger.warning(
                    "GitHub rate limit encountered on attempt %d/%d; sleeping %.2fs",
                    attempt, max_retries, sleep_sec
                )
                time.sleep(sleep_sec)
                continue

            return response

    def get_installation_access_token(self, installation_id: int) -> str:
        """Retrieve a short-lived installation access token, using an in-memory cache."""
        now = time.time()
        if installation_id in self._installation_tokens:
            token, expires_at = self._installation_tokens[installation_id]
            if expires_at - now > 120:
                return token

        app_jwt = self.generate_app_jwt()
        url = f"{self.GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = self._request_with_retry("POST", url, headers=headers, timeout=10.0)

        if response.status_code == 404:
            raise GitHubApiError(f"GitHub installation {installation_id} not found or access revoked", status_code=404)
        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"GitHub API error ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        token = data["token"]
        expires_at = now + 3500
        self._installation_tokens[installation_id] = (token, expires_at)
        return token

    def get_installation_details(self, installation_id: int) -> dict[str, Any]:
        """Fetch installation metadata directly from GitHub App API."""
        app_jwt = self.generate_app_jwt()
        url = f"{self.GITHUB_API_BASE}/app/installations/{installation_id}"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = self._request_with_retry("GET", url, headers=headers, timeout=10.0)

        if response.status_code == 404:
            raise GitHubApiError(f"GitHub installation {installation_id} not found", status_code=404)
        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(f"Failed to fetch installation details: {response.text}", status_code=response.status_code)

        return response.json()

    def list_installation_repositories(self, installation_id: int) -> list[dict[str, Any]]:
        """Fetch all repositories granted to this installation, handling pagination."""
        token = self.get_installation_access_token(installation_id)
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        all_repos: list[dict[str, Any]] = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.GITHUB_API_BASE}/installation/repositories?per_page={per_page}&page={page}"
            response = self._request_with_retry("GET", url, headers=headers, timeout=15.0)

            self._check_rate_limit(response)
            if response.status_code >= 400:
                raise GitHubApiError(
                    f"Failed to list installation repositories ({response.status_code}): {response.text}",
                    status_code=response.status_code,
                )

            data = response.json()
            repos = data.get("repositories", [])
            all_repos.extend(repos)

            total_count = data.get("total_count", 0)
            if len(all_repos) >= total_count or len(repos) < per_page:
                break
            page += 1

        return all_repos

    def get_ref_commit(self, installation_id: int, owner: str, repo: str, ref: str = "main") -> str:
        """Resolve a branch or git reference to an immutable 40-char commit SHA."""
        token = self.get_installation_access_token(installation_id)
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{ref}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = self._request_with_retry("GET", url, headers=headers, timeout=15.0)

        if response.status_code == 404:
            raise GitHubApiError(f"Reference '{ref}' not found in repository {owner}/{repo}", status_code=404)
        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"Failed to resolve ref '{ref}' ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        commit_sha = data.get("sha")
        if not commit_sha:
            raise GitHubApiError(f"Commit SHA missing in response for ref '{ref}'")
        return commit_sha

    def get_tree(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        tree_sha: str,
        recursive: bool = True,
    ) -> dict[str, Any]:
        """Fetch git tree metadata recursively for a given commit or tree SHA."""
        token = self.get_installation_access_token(installation_id)
        rec_param = "1" if recursive else "0"
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive={rec_param}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = self._request_with_retry("GET", url, headers=headers, timeout=20.0)

        if response.status_code == 404:
            raise GitHubApiError(f"Tree '{tree_sha}' not found in repository {owner}/{repo}", status_code=404)
        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"Failed to fetch tree '{tree_sha}' ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        return response.json()

    def get_blob_content(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        blob_sha: str,
    ) -> bytes:
        """Fetch raw blob content by git blob SHA."""
        import base64

        token = self.get_installation_access_token(installation_id)
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/git/blobs/{blob_sha}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = self._request_with_retry("GET", url, headers=headers, timeout=15.0)

        if response.status_code == 404:
            raise GitHubApiError(f"Blob '{blob_sha}' not found", status_code=404)
        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"Failed to fetch blob ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        encoding = data.get("encoding", "base64")
        content_str = data.get("content", "")

        if encoding == "base64":
            return base64.b64decode(content_str)
        return content_str.encode("utf-8")

    def get_ref(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        ref: str,
    ) -> dict[str, Any] | None:
        """Fetch git reference metadata. Returns None if ref is not found (404)."""
        token = self.get_installation_access_token(installation_id)
        clean_ref = ref.removeprefix("refs/")
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/git/ref/{clean_ref}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = self._request_with_retry("GET", url, headers=headers, timeout=15.0)

        if response.status_code == 404:
            return None
        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"Failed to get ref '{ref}' ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        return response.json()

    def create_branch(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        branch_name: str,
        commit_sha: str,
    ) -> dict[str, Any]:
        """Create a new git reference for a branch pointing to commit_sha."""
        token = self.get_installation_access_token(installation_id)
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/git/refs"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {
            "ref": f"refs/heads/{branch_name}",
            "sha": commit_sha,
        }

        response = self._request_with_retry("POST", url, headers=headers, json_data=payload, timeout=15.0)

        # If branch already exists (422), retrieve and return it
        if response.status_code == 422 and "Reference already exists" in response.text:
            existing = self.get_ref(installation_id, owner, repo, f"heads/{branch_name}")
            if existing:
                return existing

        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"Failed to create branch '{branch_name}' ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        return response.json()

    def create_blob(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        content: bytes,
    ) -> str:
        """Create a git blob directly from raw file content. Returns SHA-1 blob hash."""
        import base64

        token = self.get_installation_access_token(installation_id)
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/git/blobs"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        b64_content = base64.b64encode(content).decode("ascii")
        payload = {
            "content": b64_content,
            "encoding": "base64",
        }

        response = self._request_with_retry("POST", url, headers=headers, json_data=payload, timeout=15.0)

        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"Failed to create git blob ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        blob_sha = data.get("sha")
        if not blob_sha:
            raise GitHubApiError("GitHub returned blob object without SHA")
        return blob_sha

    def create_tree(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        tree_items: list[dict[str, Any]],
        base_tree_sha: str | None = None,
    ) -> str:
        """Create a new git tree. Returns tree SHA."""
        token = self.get_installation_access_token(installation_id)
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload: dict[str, Any] = {"tree": tree_items}
        if base_tree_sha:
            payload["base_tree"] = base_tree_sha

        response = self._request_with_retry("POST", url, headers=headers, json_data=payload, timeout=20.0)

        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"Failed to create git tree ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        tree_sha = data.get("sha")
        if not tree_sha:
            raise GitHubApiError("GitHub returned tree object without SHA")
        return tree_sha

    def create_commit(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        message: str,
        tree_sha: str,
        parent_shas: list[str],
    ) -> str:
        """Create an immutable commit pointing to tree_sha and parent_shas. Returns commit SHA."""
        token = self.get_installation_access_token(installation_id)
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/git/commits"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {
            "message": message,
            "tree": tree_sha,
            "parents": parent_shas,
        }

        response = self._request_with_retry("POST", url, headers=headers, json_data=payload, timeout=15.0)

        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"Failed to create git commit ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        commit_sha = data.get("sha")
        if not commit_sha:
            raise GitHubApiError("GitHub returned commit object without SHA")
        return commit_sha

    def update_ref(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        ref: str,
        commit_sha: str,
    ) -> dict[str, Any]:
        """Update reference to point to commit_sha. Never force-pushes."""
        token = self.get_installation_access_token(installation_id)
        clean_ref = ref.removeprefix("refs/")
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/git/refs/{clean_ref}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {
            "sha": commit_sha,
            "force": False,
        }

        response = self._request_with_retry("PATCH", url, headers=headers, json_data=payload, timeout=15.0)

        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"Failed to update ref '{ref}' ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        return response.json()

    def create_pull_request(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, Any]:
        """Open a Pull Request on GitHub."""
        token = self.get_installation_access_token(installation_id)
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/pulls"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        }

        response = self._request_with_retry("POST", url, headers=headers, json_data=payload, timeout=20.0)

        # If PR already exists for this branch (422), find and return the existing PR
        if response.status_code == 422 and "A pull request already exists" in response.text:
            existing_pr = self.find_pull_request(installation_id, owner, repo, head, base)
            if existing_pr:
                return existing_pr

        self._check_rate_limit(response)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"Failed to create pull request ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        return response.json()

    def find_pull_request(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        head: str,
        base: str,
    ) -> dict[str, Any] | None:
        """Find an existing PR matching the head and base branches."""
        token = self.get_installation_access_token(installation_id)
        clean_head = head.split(":")[-1]
        url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/pulls?head={owner}:{clean_head}&base={base}&state=all"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = self._request_with_retry("GET", url, headers=headers, timeout=15.0)

        if response.status_code >= 400:
            return None

        pulls = response.json()
        if isinstance(pulls, list) and len(pulls) > 0:
            return pulls[0]
        return None
