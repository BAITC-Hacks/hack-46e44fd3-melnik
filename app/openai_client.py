import json
import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openai_client")

_client = None

def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "sk-placeholder"))
    return _client

def chat(messages, model="gpt-4o-mini", tools=None, response_format=None, **kwargs):
    logger.info("OpenAI request: model=%s messages=%s tools=%s", model, messages, bool(tools))
    resp = get_client().chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        response_format=response_format,
        **kwargs,
    )
    logger.info("OpenAI response id=%s finish_reason=%s", resp.id, resp.choices[0].finish_reason)
    return resp

def structured_output(messages, schema: dict, model="gpt-4o-mini", schema_name="response"):
    """schema — JSON Schema dict, ответ парсится и возвращается как dict."""
    resp = chat(
        messages=messages,
        model=model,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        },
    )
    return json.loads(resp.choices[0].message.content)

def call_with_tools(messages, tools, model="gpt-4o-mini"):
    """Возвращает сырой response — сам разбирай tool_calls в вызывающем коде."""
    return chat(messages=messages, model=model, tools=tools, tool_choice="auto")
