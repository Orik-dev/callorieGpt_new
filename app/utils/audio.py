# app/utils/audio.py
import os
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

WHISPER_MODEL = "whisper-1"
WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"


async def ogg_to_text(ogg_path: str) -> str:
    """
    Распознаёт речь из OGG-файла через OpenAI Whisper API.
    """
    try:
        with open(ogg_path, "rb") as f:
            files = {"file": (os.path.basename(ogg_path), f, "audio/ogg")}
            data = {"model": WHISPER_MODEL, "language": "ru"}

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    WHISPER_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    files=files,
                    data=data,
                )

            if response.status_code != 200:
                logger.error(f"[Whisper] API error {response.status_code}: {response.text}")
                return ""

            result = response.json()
            text = result.get("text", "").strip()
            logger.info(f"[Whisper] Recognized: '{text[:80]}'")
            return text

    except Exception as e:
        logger.exception(f"[Whisper] Error processing {ogg_path}: {e}")
        return ""
    finally:
        if os.path.exists(ogg_path):
            os.remove(ogg_path)
