import json
import os
import re
from typing import Any

import httpx


class LLMClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def json_response(self, instructions: str, payload: dict[str, Any], use_web_search: bool = False) -> dict[str, Any] | None:
        if not self.available:
            return None
        body: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            # The Responses API enforces that the input literally contains the
            # word "json" when json_object output is requested, so we prefix the
            # serialized payload with an explicit instruction.
            "input": f"Respond with a single strict json object only. Input data:\n{json.dumps(payload)}",
        }
        if use_web_search:
            # Web Search cannot be combined with json_object output mode, so we
            # request JSON via the prompt and parse it tolerantly from the text.
            body["tools"] = [{"type": "web_search_preview"}]
        else:
            # The Responses API takes the JSON-mode flag under `text.format`, not
            # the Chat-Completions `response_format` key. Using `response_format`
            # here makes every call 400 and silently fall back to mock mode.
            body["text"] = {"format": {"type": "json_object"}}
        try:
            with httpx.Client(timeout=45) as client:
                response = client.post(
                    f"{self.base_url}/responses",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=body,
                )
                response.raise_for_status()
                data = response.json()
            text = _extract_output_text(data)
            return _parse_json(text) if text else None
        except Exception:
            return None


def _extract_output_text(data: dict[str, Any]) -> str:
    text = data.get("output_text")
    if text:
        return text
    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    return "".join(chunks)


def _parse_json(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from model output, tolerating ```json fences and
    surrounding prose (e.g. when web search returns annotated text)."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
