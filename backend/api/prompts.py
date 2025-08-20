import asyncio
import logging
import os
import aiofiles

from fastapi import APIRouter, HTTPException

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/")
async def get_prompts():
    try:
        # Adjust path to look for prompts directory at project root
        prompts_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "prompts")
        )
        prompts = []
        defaults = {}

        # Function to read prompt files recursively - PERFORMANCE FIX: Make async
        async def read_prompt_files(directory, base_path=""):
            entries = await asyncio.to_thread(os.listdir, directory)
            for entry in entries:
                full_path = os.path.join(directory, entry)
                rel_path = os.path.join(base_path, entry) if base_path else entry
                if await asyncio.to_thread(os.path.isdir, full_path):
                    await read_prompt_files(full_path, rel_path)
                elif await asyncio.to_thread(os.path.isfile, full_path) and (
                    entry.endswith(".txt") or entry.endswith(".md")
                ):
                    try:
                        # PERFORMANCE FIX: Convert to async file I/O
                        async with aiofiles.open(full_path, "r", encoding="utf-8") as f:
                            content = await f.read()
                        prompt_id = (
                            rel_path.replace("/", "_")
                            .replace("\\", "_")
                            .rsplit(".", 1)[0]
                        )
                        prompt_type = base_path if base_path else "custom"
                        prompts.append(
                            {
                                "id": prompt_id,
                                "name": entry.rsplit(".", 1)[0],
                                "type": prompt_type,
                                "path": rel_path,
                                "content": content,
                            }
                        )
                        if "default" in directory:
                            defaults[prompt_id] = content
                    except Exception as e:
                        logger.error(f"Error reading prompt file {full_path}: {str(e)}")

        # Read prompts from the prompts directory
        if os.path.exists(prompts_dir):
            await read_prompt_files(prompts_dir)
        else:
            logger.warning(f"Prompts directory {prompts_dir} not found")

        logger.info(f"Returning {len(prompts)} prompts")
        return {"prompts": prompts, "defaults": defaults}
    except Exception as e:
        logger.error(f"Error getting prompts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting prompts: {str(e)}")


@router.post("/{prompt_id}")
async def save_prompt(prompt_id: str, request: dict):
    try:
        content = request.get("content", "")
        # Derive the file path from the prompt_id, relative to project root
        prompts_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "prompts")
        )

        # Sanitize prompt_id to prevent path traversal
        # Remove any path traversal attempts
        safe_prompt_id = prompt_id.replace("..", "").replace("~", "").strip("/")

        # Convert underscores to directory separators
        relative_path = safe_prompt_id.replace("_", "/")

        # Build the full path
        file_path = os.path.join(prompts_dir, relative_path)

        # Ensure the resolved path is within prompts_dir
        resolved_path = os.path.abspath(file_path)
        if not resolved_path.startswith(prompts_dir):
            return {"error": "Invalid prompt_id - path traversal detected"}, 400

        # Ensure the directory exists
        os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

        # Write the content to the file - PERFORMANCE FIX: Convert to async file I/O
        async with aiofiles.open(resolved_path, "w", encoding="utf-8") as f:
            await f.write(content)
        logger.info(f"Saved prompt {prompt_id} to {file_path}")
        # Return the updated prompt data
        prompt_name = os.path.basename(file_path).rsplit(".", 1)[0]
        prompt_type = (
            os.path.dirname(file_path).replace(prompts_dir + "/", "")
            if prompts_dir in file_path
            else os.path.dirname(file_path)
        )
        return {
            "id": prompt_id,
            "name": prompt_name,
            "type": prompt_type if prompt_type else "custom",
            "path": (
                file_path.replace(prompts_dir + "/", "")
                if prompts_dir in file_path
                else file_path
            ),
            "content": content,
        }
    except Exception as e:
        logger.error(f"Error saving prompt {prompt_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving prompt: {str(e)}")


@router.post("/{prompt_id}/revert")
async def revert_prompt(prompt_id: str):
    try:
        prompts_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "prompts")
        )
        # Check if there is a default version of this prompt
        default_file_path = os.path.join(
            prompts_dir, "default", prompt_id.replace("_", "/")
        )
        if os.path.exists(default_file_path):
            # PERFORMANCE FIX: Convert to async file I/O
            async with aiofiles.open(default_file_path, "r", encoding="utf-8") as f:
                default_content = await f.read()
            # Save the default content to the custom prompt location
            custom_file_path = os.path.join(prompts_dir, prompt_id.replace("_", "/"))
            os.makedirs(os.path.dirname(custom_file_path), exist_ok=True)
            async with aiofiles.open(custom_file_path, "w", encoding="utf-8") as f:
                await f.write(default_content)
            logger.info(f"Reverted prompt {prompt_id} to default")
            prompt_name = os.path.basename(custom_file_path).rsplit(".", 1)[0]
            prompt_type = (
                os.path.dirname(custom_file_path).replace(prompts_dir + "/", "")
                if prompts_dir in custom_file_path
                else os.path.dirname(custom_file_path)
            )
            return {
                "id": prompt_id,
                "name": prompt_name,
                "type": prompt_type if prompt_type else "custom",
                "path": (
                    custom_file_path.replace(prompts_dir + "/", "")
                    if prompts_dir in custom_file_path
                    else custom_file_path
                ),
                "content": default_content,
            }
        else:
            logger.warning(f"No default found for prompt {prompt_id}")
            raise HTTPException(
                status_code=404, detail=f"No default prompt found for {prompt_id}"
            )
    except Exception as e:
        logger.error(f"Error reverting prompt {prompt_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reverting prompt: {str(e)}")
