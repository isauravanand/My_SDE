import logging
import time
from pathlib import Path
from typing import Any

import httpx
import jwt

from app.core.config import Settings, get_settings

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
    """Dedicated HTTP client for GitHub App and installation operations."""

    GITHUB_API_BASE = "https://api.github.com"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._installation_tokens: dict[int, tuple[str, float]] = {}

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
            logger.error("Failed to sign GitHub App JWT", exc_info=True)
            raise GitHubApiError(f"Failed to generate GitHub App authentication JWT: {e}") from e

    def get_installation_access_token(self, installation_id: int) -> str:
        """Retrieve a short-lived installation access token, using an in-memory cache."""
        now = time.time()
        if installation_id in self._installation_tokens:
            token, expires_at = self._installation_tokens[installation_id]
            # If token is valid for more than 2 minutes into the future, reuse it
            if expires_at - now > 120:
                return token

        app_jwt = self.generate_app_jwt()
        url = f"{self.GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
                response = client.post(url, headers=headers)
        except httpx.TimeoutException as e:
            logger.warning(f"Timeout requesting installation access token for {installation_id}")
            raise GitHubApiError("Connection to GitHub API timed out", status_code=504) from e
        except httpx.RequestError as e:
            logger.warning(f"Network error requesting installation access token for {installation_id}: {e}")
            raise GitHubApiError("Unable to reach GitHub API", status_code=502) from e

        if response.status_code == 404:
            raise GitHubApiError(f"GitHub installation {installation_id} not found or access revoked", status_code=404)
        if response.status_code == 403 or response.status_code == 429:
            reset_header = response.headers.get("x-ratelimit-reset")
            reset_at = int(reset_header) if reset_header and reset_header.isdigit() else None
            raise GitHubRateLimitError(reset_at=reset_at)
        if response.status_code >= 400:
            raise GitHubApiError(
                f"GitHub API error ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        token = data["token"]
        # Default expiration is 1 hour
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

        try:
            with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
                response = client.get(url, headers=headers)
        except httpx.TimeoutException as e:
            raise GitHubApiError("Connection to GitHub API timed out", status_code=504) from e
        except httpx.RequestError as e:
            raise GitHubApiError("Unable to reach GitHub API", status_code=502) from e

        if response.status_code == 404:
            raise GitHubApiError(f"GitHub installation {installation_id} not found", status_code=404)
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

        with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
            while True:
                url = f"{self.GITHUB_API_BASE}/installation/repositories?per_page={per_page}&page={page}"
                try:
                    response = client.get(url, headers=headers)
                except httpx.TimeoutException as e:
                    raise GitHubApiError("Connection to GitHub API timed out while fetching repositories", status_code=504) from e
                except httpx.RequestError as e:
                    raise GitHubApiError("Unable to reach GitHub API", status_code=502) from e

                if response.status_code == 403 or response.status_code == 429:
                    reset_header = response.headers.get("x-ratelimit-reset")
                    reset_at = int(reset_header) if reset_header and reset_header.isdigit() else None
                    raise GitHubRateLimitError(reset_at=reset_at)
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
