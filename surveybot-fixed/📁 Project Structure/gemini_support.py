"""Gemini REST client shared by the supported Playwright workflow."""
import os

from google import genai
from google.genai import types


def get_api_key():
    """Reuse either existing binding without printing credential values."""
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""


class GeminiModel:
    def __init__(self, model_name=None, *, json_output=False):
        key = get_api_key()
        if not key:
            raise ValueError("Set GOOGLE_API_KEY (or GEMINI_API_KEY) before using Gemini.")
        self.model_name = model_name or os.getenv("AI_MODEL", "gemini-flash-latest")
        # The SDK uses verified HTTPS and respects the environment's proxy settings.
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000))
        self.config = types.GenerateContentConfig(
            response_mime_type="application/json" if json_output else "text/plain"
        )

    @staticmethod
    def _contents(contents):
        if not isinstance(contents, list):
            return contents
        return [
            types.Part.from_bytes(data=item["data"], mime_type=item["mime_type"])
            if isinstance(item, dict) and "data" in item and "mime_type" in item else item
            for item in contents
        ]

    def generate_content(self, contents):
        return self.client.models.generate_content(
            model=self.model_name, contents=self._contents(contents), config=self.config
        )

    async def generate_content_async(self, contents):
        return await self.client.aio.models.generate_content(
            model=self.model_name, contents=self._contents(contents), config=self.config
        )

    async def close(self):
        await self.client.aio.aclose()
        self.client.close()
