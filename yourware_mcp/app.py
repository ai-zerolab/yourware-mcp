import io
import os
import zipfile
from pathlib import Path
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP

from yourware_mcp.client import get_client
from yourware_mcp.credentials import API_BASE_URL, CREDENTIALS_PATH, Credentials
from yourware_mcp.utils import urljoin

mcp = FastMCP("yourware-mcp")


@mcp.tool(description="Check your yourware credentials exists and are valid.")
async def check_credentials():
    try:
        credentials = Credentials.load()
    except FileNotFoundError:
        return {
            "success": False,
            "message": "Credentials not found",
            "help": "Run `create_api_key` to create one",
        }

    if not await credentials.check_credentials():
        return {
            "success": False,
            "message": "Credentials are invalid",
            "help": "Call `create_api_key` to create one",
        }

    return {
        "success": True,
        "message": "Credentials are valid",
    }


@mcp.tool(
    description=f"Create a new yourware API key. This will automatically be stored in {CREDENTIALS_PATH.as_posix()}. Use this tool if current credentials are invalid"
)
async def create_api_key(api_key: Annotated[str | None, "The API key to store"] = None):
    if not api_key:
        quick_create_address = urljoin(API_BASE_URL, "/api/v1/api-keys/quick-create")
        login_address = urljoin(API_BASE_URL, "/login")
        return {
            "success": False,
            "message": "API key is required, please guide the user to create one. Let the user tell you what the page shows and guide them through the login process if needed.",
            "help": f"Click this link to create one: {quick_create_address}\n\nClick this link to login if needed: {login_address}",
        }

    Credentials(api_key=api_key).store_credentials()
    return {
        "success": True,
        "message": "API key created",
    }


@mcp.tool(
    description="Upload a file or directory to yourware, might be a dist/out directory or a single html file. Use absolute path if possible. "
    "For multiple files, you should move them to a directory first, then use this tool to upload the directory"
)
async def upload_project(  # noqa: C901
    file_path: Annotated[
        str,
        "The path to the dist/out directory or single file. If ends with /, it will be treated as a directory",
    ],
    cwd: Annotated[
        str | None,
        "The current working directory to resolve relative paths from, should be a absolute path",
    ] = None,
):
    if cwd:
        cwd_path = Path(cwd).expanduser().resolve()
        file_path = cwd_path / file_path
    else:
        file_path = Path(file_path)

    file_path = file_path.expanduser().resolve()

    try:
        credentials = Credentials.load()
    except FileNotFoundError:
        return {
            "success": False,
            "message": "Credentials not found",
            "help": "Run `create_api_key` to create one",
        }

    if not await credentials.check_credentials():
        return {
            "success": False,
            "message": "Credentials are invalid",
            "help": "Call `create_api_key` to create one",
        }
    client = get_client(credentials)

    # 1. Create a zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        if file_path.is_dir():
            # 2. Zip the directory into it
            for root, dirs, files in os.walk(file_path):
                # Skip .git directories
                if ".git" in dirs:
                    dirs.remove(".git")  # This modifies dirs in-place to prevent os.walk from traversing .git

                for file in files:
                    file_full_path = Path(root) / file
                    arc_name = file_full_path.relative_to(file_path)
                    zip_file.write(file_full_path, arcname=arc_name)
        else:
            # Zip the single file
            zip_file.write(file_path, arcname=file_path.name)

    # Get the zip content
    zip_buffer.seek(0)
    zip_content = zip_buffer.getvalue()
    zip_size = len(zip_content)

    # 3. Call /api/v1/files/upload for upload infos
    upload_response = await client.post(
        "/api/v1/files/upload",
        json={
            "files": [
                {
                    "file_name": "source_code.zip",
                    "file_size": zip_size,
                    "mime_type": "application/zip",
                }
            ],
            "event_type": "source_code",
            "is_public": False,
        },
    )

    if upload_response.status_code != 200:
        return {
            "success": False,
            "message": f"Failed to get upload info: {upload_response.text}",
        }

    upload_data = upload_response.json()
    upload_info = upload_data["data"]["upload_infos"][0]
    file_id = upload_info["file_id"]
    upload_url = upload_info["upload_url"]
    fields = upload_info["fields"]

    # 4. Upload the zip to the upload url
    files = {"file": ("source_code.zip", zip_content, "application/zip")}
    form_data = {**fields}

    async with httpx.AsyncClient() as upload_client:
        upload_result = await upload_client.post(upload_url, data=form_data, files=files)

    if upload_result.status_code not in (200, 201, 204):
        return {
            "success": False,
            "message": f"Failed to upload file: {upload_result.text}",
        }

    # 5. Call /api/v1/projects/deploy with the file_id
    deploy_response = await client.post("/api/v1/projects/deploy", json={"file_id": file_id})

    if deploy_response.status_code != 200:
        return {
            "success": False,
            "message": f"Failed to deploy project: {deploy_response.text}",
        }

    deploy_data = deploy_response.json()
    project_data = deploy_data["data"]

    return {
        "success": True,
        "message": "Project uploaded successfully",
        "project_url": project_data["project_url"],
        "iframe_url": project_data["iframe_url"],
    }
