import json
from pathlib import Path
from urllib.request import Request, urlopen
import yaml # type: ignore
from urllib.parse import quote


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
def extract_api_contracts(spec: dict) -> list[dict]:
    """Extract endpoints, HTTP methods, and request parameters."""

    contracts = []
    supported_methods = {
        "get", "post", "put", "patch", "delete",
        "options", "head", "trace"
    }

    paths = spec.get("paths", {})

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        # Parameters defined at the path level
        path_parameters = path_item.get("parameters", [])

        for method, operation in path_item.items():
            if method.lower() not in supported_methods:
                continue

            if not isinstance(operation, dict):
                continue

            operation_parameters = operation.get("parameters", [])
            all_parameters = path_parameters + operation_parameters

            parameters = []

            for parameter in all_parameters:
                if not isinstance(parameter, dict):
                    continue

                parameters.append({
                    "name": parameter.get("name"),
                    "in": parameter.get("in"),
                    "required": parameter.get("required", False),
                    "type": (
                        parameter.get("schema", {}).get("type")
                        if isinstance(parameter.get("schema"), dict)
                        else None
                    ),
                })

            contracts.append({
                "path": path,
                "method": method.upper(),
                "operation_id": operation.get("operationId"),
                "summary": operation.get("summary"),
                "parameters": parameters,
            })

    return contracts
def save_api_contracts(
    contracts: list[dict],
    output_path: str = "reports/repository_contracts.json",
) -> None:
    """Save extracted API contracts as a JSON file."""

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(contracts, file, indent=2)

    print(f"API contracts saved to: {output_file}")
    print(f"Total contracts saved: {len(contracts)}")

def fetch_openapi_spec(
    repo_owner: str,
    repo_name: str,
    branch: str,
    file_path: str,
) -> dict:
    """Download and parse an OpenAPI specification from GitHub."""

    from urllib.parse import quote
    from urllib.request import Request, urlopen

    raw_url = (
        f"https://raw.githubusercontent.com/"
        f"{repo_owner}/{repo_name}/{branch}/"
        f"{quote(file_path, safe='/')}"
    )

    request = Request(
        raw_url,
        headers={"User-Agent": "API-Sentinel"},
    )

    try:
        with urlopen(request, timeout=20) as response:
            content = response.read().decode("utf-8")

        spec = yaml.safe_load(content)

    except Exception as exc:
        raise RuntimeError(
            f"Could not fetch OpenAPI file {file_path}: {exc}"
        ) from exc

    if not isinstance(spec, dict):
        raise RuntimeError(
            f"Invalid OpenAPI document: {file_path}"
        )

    if "openapi" not in spec or "paths" not in spec:
        raise RuntimeError(
            f"File is not a valid OpenAPI document: {file_path}"
        )

    return spec