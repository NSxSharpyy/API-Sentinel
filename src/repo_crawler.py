import json
from pathlib import Path
from urllib.request import Request, urlopen


SUPPORTED_EXTENSIONS = {".json", ".yaml", ".yml"}


def discover_openapi_files(repo_owner: str, repo_name: str, branch: str = "main") -> list[str]:
    """Discover OpenAPI specification files in a public GitHub repository."""

    api_url = (
        f"https://api.github.com/repos/"
        f"{repo_owner}/{repo_name}/git/trees/{branch}?recursive=1"
    )

    request = Request(
        api_url,
        headers={"Accept": "application/vnd.github+json"},
    )

    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"Could not inspect repository {repo_owner}/{repo_name}: {exc}"
        ) from exc

    if data.get("truncated"):
        raise RuntimeError(
            "GitHub returned an incomplete repository tree."
        )

    discovered_files = []

    for item in data.get("tree", []):
        if item.get("type") != "blob":
            continue

        file_path = item.get("path", "")
        filename = Path(file_path).name.lower()

        if (
            Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS
            and any(
                keyword in filename
                for keyword in ("openapi", "swagger", "api-spec", "api_spec")
            )
        ):
            discovered_files.append(file_path)

    return sorted(discovered_files)