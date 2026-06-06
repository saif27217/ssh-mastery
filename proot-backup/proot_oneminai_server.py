#!/usr/bin/env python3
"""
FastAPI server for LiteLLM 1minAI proxy integration.
This server provides OpenAI-compatible endpoints for RAG Superbot agents.
"""

import os
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import httpx
import aiohttp
import tiktoken
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, Response, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import uvicorn

# LiteLLM for fallbacks
import litellm
from litellm import acompletion

# Configure logging with security focus
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security logging
def log_security_event(event_type: str, details: dict, severity: str = "medium"):
    """Log security events with structured format."""
    security_log = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "severity": severity,
        "details": details
    }

    log_message = f"🔒 SECURITY [{severity.upper()}] {event_type}: {details}"

    if severity in ["critical", "high"]:
        logger.error(log_message)
    elif severity == "medium":
        logger.warning(log_message)
    else:
        logger.info(log_message)

def detect_suspicious_request(request: Request) -> list:
    """Detect suspicious patterns in requests."""
    reasons = []
    url = str(request.url).lower()
    user_agent = request.headers.get("user-agent", "").lower()

    # SQL injection patterns
    sql_patterns = ["union select", "drop table", "insert into", "delete from", "exec("]
    if any(pattern in url for pattern in sql_patterns):
        reasons.append("SQL injection pattern detected")

    # XSS patterns
    xss_patterns = ["<script", "javascript:", "onload=", "onerror=", "alert("]
    if any(pattern in url for pattern in xss_patterns):
        reasons.append("XSS pattern detected")

    # Suspicious user agents
    suspicious_agents = ["sqlmap", "nikto", "nmap", "burp", "owasp"]
    if any(agent in user_agent for agent in suspicious_agents):
        reasons.append("Suspicious user agent")

    return reasons

# Initialize FastAPI app
app = FastAPI(
    title="LiteLLM 1minAI Proxy for RAG Superbot",
    description="OpenAI-compatible proxy for 1minAI integration with RAG Superbot (with Fallbacks)",
    version="1.1.0"
)

# Add CORS middleware with secure configuration
# Allow all origins for agent compatibility (OpenClaw, Hermes, etc.)
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in allowed_origins else allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Accept",
        "Origin",
        "Cache-Control",
        "X-Request-ID"
    ],
    expose_headers=["X-Request-ID"],
    max_age=3600
)

# Pydantic models for request/response
class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role (system, user, assistant, tool)")
    content: Optional[str] = Field(None, description="Message content")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Tool calls made by assistant")
    tool_call_id: Optional[str] = Field(None, description="ID of tool call this message is responding to")
    name: Optional[str] = Field(None, description="Name of the tool that produced this message")

class Tool(BaseModel):
    """OpenAI function/tool definition"""
    type: str = Field(default="function", description="Tool type")
    function: Dict[str, Any] = Field(..., description="Function definition with name, description, parameters")

class ChatCompletionRequest(BaseModel):
    model: str = Field(default="gpt-4o-mini", description="Model to use")
    messages: List[ChatMessage] = Field(..., description="List of chat messages")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, description="Maximum tokens to generate")
    stream: Optional[bool] = Field(default=False, description="Whether to stream response")
    response_format: Optional[Dict[str, Any]] = Field(default=None, description="Response format (e.g. json_object)")
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    n: Optional[int] = Field(default=1, ge=1, le=10, description="Number of completions to generate")
    stop: Optional[List[str]] = Field(default=None, description="Stop sequences")
    presence_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0, description="Presence penalty")
    frequency_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0, description="Frequency penalty")
    logit_bias: Optional[Dict[str, float]] = Field(default=None, description="Token logit bias")
    user: Optional[str] = Field(default=None, description="User identifier for tracking")
    seed: Optional[int] = Field(default=None, description="Seed for deterministic sampling")
    tools: Optional[List[Tool]] = Field(default=None, description="List of tools/functions available")
    tool_choice: Optional[str] = Field(default="auto", description="Tool choice: 'auto', 'none', or specific tool")

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, Any]

class OpenAIError(BaseModel):
    """OpenAI-compliant error format"""
    message: str
    type: str
    param: Optional[str] = None
    code: Optional[str] = None

class OpenAIErrorResponse(BaseModel):
    error: OpenAIError

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    service: str = "litellm-1minai-proxy"
    version: str = "1.1.0"

# Initialize tiktoken encoder for accurate token counting
try:
    tokenizer = tiktoken.encoding_for_model("gpt-4o-mini")
except Exception:
    tokenizer = tiktoken.get_encoding("cl100k_base")  # Fallback to GPT-4 encoding

def count_tokens(text: str) -> int:
    """Count tokens using tiktoken for accuracy."""
    try:
        return len(tokenizer.encode(text))
    except Exception as e:
        logger.warning(f"Token counting failed, using word split: {e}")
        return len(text.split())

def count_message_tokens(messages: List[ChatMessage]) -> int:
    """Count tokens in message list following OpenAI's format."""
    num_tokens = 0
    for message in messages:
        # Every message follows <|start|>{role/name}\n{content}<|end|>\n
        num_tokens += 4  # Message formatting tokens
        num_tokens += count_tokens(message.role)
        if message.content:
            num_tokens += count_tokens(message.content)
    num_tokens += 2  # Priming tokens for assistant response
    return num_tokens

def trim_context_window(messages: List[ChatMessage], max_messages: int) -> List[ChatMessage]:
    """
    Trim message history to save tokens while preserving context.
    Keeps system messages + last N messages.
    """
    if len(messages) <= max_messages:
        return messages

    # Separate system messages from others
    system_msgs = [m for m in messages if m.role == "system"]
    other_msgs = [m for m in messages if m.role != "system"]

    # Keep last max_messages of non-system messages
    if len(other_msgs) > max_messages:
        logger.info(f"Trimming context: {len(other_msgs)} → {max_messages} messages")
        other_msgs = other_msgs[-max_messages:]

    return system_msgs + other_msgs

async def stream_openai_chunks(content: str, model: str, request_id: str):
    """
    Generate OpenAI-compatible streaming chunks.
    Yields SSE-formatted chat.completion.chunk objects.
    """
    # Split content into words for streaming
    words = content.split()

    # First chunk with role
    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": ""},
            "finish_reason": None
        }]
    }
    yield f"data: {json.dumps(chunk)}\n\n"

    # Stream content word by word
    for i, word in enumerate(words):
        chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": word + (" " if i < len(words) - 1 else "")},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.01)  # Small delay for realistic streaming

    # Final chunk with finish_reason
    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop"
        }]
    }
    yield f"data: {json.dumps(chunk)}\n\n"

    # Termination signal
    yield "data: [DONE]\n\n"

# Global variables for configuration
ONEMINAI_API_KEY = os.getenv("ONEMINAI_API_KEY")
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "https://api.1min.ai")

# Token optimization settings
MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))
COMPACT_TOOL_DESCRIPTIONS = os.getenv("COMPACT_TOOL_DESCRIPTIONS", "true").lower() == "true"

# 1minAI Model Mapping (configurable via .env)
ONEMINAI_MODEL_MAPPING = {
    "gpt-4o-mini": os.getenv("ONEMINAI_MODEL_GPT4O_MINI", "gpt-4o-mini"),
    "gpt-4o": os.getenv("ONEMINAI_MODEL_GPT4O", "gpt-4o"),
    "claude-3-5-sonnet": os.getenv("ONEMINAI_MODEL_CLAUDE_SONNET", "claude-3-5-sonnet"),
    "claude-3-haiku": os.getenv("ONEMINAI_MODEL_CLAUDE_HAIKU", "claude-3-haiku"),
    "gemini-2.0-flash": os.getenv("ONEMINAI_MODEL_GEMINI_2_FLASH", "gemini-2.0-flash"),
    "gemini-1.5-flash": os.getenv("ONEMINAI_MODEL_GEMINI_15_FLASH", "gemini-1.5-flash"),
    "gemini-1.5-pro": os.getenv("ONEMINAI_MODEL_GEMINI_15_PRO", "gemini-1.5-pro"),
}

# Helper to validate keys (ignore placeholders)
def get_valid_key(name, default=None):
    val = os.getenv(name, default)
    if val and (val.startswith("your_") or val.startswith("sk-or-your-") or "key-here" in val):
        logger.warning(f"Ignoring placeholder value for {name}")
        return None
    return val

# Fallback Keys (Primary + 2 Backups per provider)
OPENROUTER_KEYS = [
    get_valid_key("OPENROUTER_API_KEY"),
    get_valid_key("OPENROUTER_API_KEY_2"),
    get_valid_key("OPENROUTER_API_KEY_3")
]
MISTRAL_KEYS = [
    get_valid_key("MISTRAL_API_KEY"),
    get_valid_key("MISTRAL_API_KEY_2"),
    get_valid_key("MISTRAL_API_KEY_3")
]
GEMINI_KEYS = [
    get_valid_key("GEMINI_API_KEY") or get_valid_key("GOOGLE_API_KEY"),
    get_valid_key("GEMINI_API_KEY_2"),
    get_valid_key("GEMINI_API_KEY_3")
]

# Fallback Models (Configurable)
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/google/gemini-pro-1.5")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral/mistral-large-latest")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini/gemini-1.5-pro")

# We no longer set os.environ globally as we rotate keys dynamically

# Security
security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security), request: Request = None):
    """Verify the provided API key against the configured 1minAI API key."""
    if not ONEMINAI_API_KEY:
        pass

    if credentials.credentials != ONEMINAI_API_KEY:
        client_ip = request.client.host if request else "unknown"
        key_prefix = credentials.credentials[:10] if credentials.credentials else "empty"

        log_security_event("API_KEY_INVALID", {
            "client_ip": client_ip,
            "key_prefix": key_prefix,
            "endpoint": str(request.url) if request else "unknown"
        }, severity="high")

        logger.warning(f"Invalid API key attempt: {key_prefix}... from IP: {client_ip}")

        # Return OpenAI-compliant error
        error_response = OpenAIErrorResponse(
            error=OpenAIError(
                message="Incorrect API key provided. You can find your API key at https://platform.openai.com/account/api-keys.",
                type="invalid_request_error",
                param=None,
                code="invalid_api_key"
            )
        )
        raise HTTPException(
            status_code=401,
            detail=error_response.model_dump(),
            headers={"WWW-Authenticate": "Bearer"}
        )

    return credentials.credentials

# 1minAI API integration functions
async def make_1minai_request(messages: List[ChatMessage], model: str, temperature: float = 0.7, max_tokens: Optional[int] = None, response_format: Optional[Dict[str, Any]] = None, top_p: Optional[float] = 1.0, stop: Optional[List[str]] = None, tools: Optional[List[Tool]] = None, tool_choice: Optional[str] = "auto") -> Dict[str, Any]:
    """
    Make a real request to 1minAI API using the correct endpoint and format.
    Supports function calling via tools parameter.
    Includes token optimization (context window limit, compact tool descriptions).
    """
    if not ONEMINAI_API_KEY:
        error_response = OpenAIErrorResponse(
            error=OpenAIError(
                message="The server is not configured with an API key.",
                type="invalid_request_error",
                param=None,
                code="missing_api_key"
            )
        )
        raise HTTPException(status_code=500, detail=error_response.model_dump())

    # Token optimization: Trim context window
    trimmed_messages = trim_context_window(messages, MAX_CONTEXT_MESSAGES)

    # Transform messages to prompt format
    prompt_parts = []
    has_tool_results = False

    for msg in messages:
        role = msg.role
        content = msg.content

        if role == "system":
            prompt_parts.append(f"System: {content}")
        elif role == "assistant":
            # Check if assistant message has tool_calls
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                # Assistant called a function
                for tool_call in msg.tool_calls:
                    func_name = tool_call.get('function', {}).get('name', 'unknown')
                    func_args = tool_call.get('function', {}).get('arguments', '{}')
                    prompt_parts.append(f"Assistant: [Called function: {func_name} with arguments: {func_args}]")
            elif content:
                prompt_parts.append(f"Assistant: {content}")
        elif role == "tool":
            # Tool result message
            has_tool_results = True
            tool_call_id = getattr(msg, 'tool_call_id', 'unknown')
            tool_name = getattr(msg, 'name', 'function')
            prompt_parts.append(f"Function Result ({tool_name}): {content}")
        else:
            # User message
            prompt_parts.append(f"User: {content}")

    prompt = "\n\n".join(prompt_parts)

    # If we have tool results, instruct the LLM to use them
    if has_tool_results:
        prompt += "\n\nBased on the function results above, provide a natural language response to the user's original question."

    # If tools are provided (and no tool results yet), append them to the prompt
    if tools and not has_tool_results:
        if COMPACT_TOOL_DESCRIPTIONS:
            # Compact format: Tools: func1(param1,param2); func2(param1)
            tools_description = "\n\nTools: "
            tool_list = []
            for tool in tools:
                func = tool.function
                params = list(func.get('parameters', {}).get('properties', {}).keys())
                param_str = ",".join(params) if params else ""
                tool_list.append(f"{func['name']}({param_str})")
            tools_description += "; ".join(tool_list)
            tools_description += "\n\nCall format: {\"function_call\":{\"name\":\"...\",\"arguments\":{...}}}"
        else:
            # Verbose format (original)
            tools_description = "\n\nAvailable functions:\n"
            for tool in tools:
                func = tool.function
                tools_description += f"- {func['name']}: {func.get('description', 'No description')}\n"
                if 'parameters' in func:
                    tools_description += f"  Parameters: {json.dumps(func['parameters'])}\n"
            tools_description += "\n\nIf you need to call a function, respond with JSON in this format: {\"function_call\": {\"name\": \"function_name\", \"arguments\": {...}}}"

        prompt += tools_description

    # Map model names to 1minAI supported format (using configurable mapping)
    # First check if model is in our configurable mapping
    if model in ONEMINAI_MODEL_MAPPING:
        mapped_model = ONEMINAI_MODEL_MAPPING[model]
    else:
        # Fallback to hardcoded mapping for backward compatibility
        model_mapping = {
            "1minai-gpt-4o-mini": "gpt-4o-mini",
            "1minai-gpt-4o": "gpt-4o",
            "1minai-claude-3-5-sonnet": "claude-3-5-sonnet",
            "1minai-claude-3-haiku": "claude-3-haiku",
        }
        mapped_model = model_mapping.get(model, ONEMINAI_MODEL_MAPPING.get("gpt-4o-mini", "gpt-4o-mini"))

    # Create 1minAI payload (updated API format)
    payload = {
        "type": "UNIFY_CHAT_WITH_AI",
        "model": mapped_model,
        "promptObject": {
            "prompt": prompt,
            "settings": {
                "webSearchSettings": {
                    "webSearch": False,
                    "numOfSite": 3,
                    "maxWord": 1000
                },
                "historySettings": {
                    "isMixed": False,
                    "historyMessageLimit": 10
                },
                "withMemories": False
            }
        }
    }

    headers = {
        "API-KEY": ONEMINAI_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        logger.info(f"Making request to: https://api.1min.ai/api/chat-with-ai")
        logger.info(f"Using model: {mapped_model}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.1min.ai/api/chat-with-ai",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=45)
            ) as response:
                logger.info(f"1minAI API response status: {response.status}")
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"1minAI API request successful for model: {model}")

                    # Parse 1minAI response format
                    ai_record = result.get("aiRecord", {})
                    ai_record_detail = ai_record.get("aiRecordDetail", {})
                    result_object = ai_record_detail.get("resultObject", [])

                    # Extract response text
                    response_text = ""
                    if isinstance(result_object, list) and result_object:
                        response_text = str(result_object[0])
                    else:
                        response_text = "No response generated"

                    # Check if response contains function call
                    tool_calls = None
                    finish_reason = "stop"

                    if tools and "{" in response_text and "function_call" in response_text:
                        try:
                            # Try to extract function call from response
                            func_call_data = json.loads(response_text)
                            if "function_call" in func_call_data:
                                tool_calls = [{
                                    "id": f"call_{int(time.time())}",
                                    "type": "function",
                                    "function": {
                                        "name": func_call_data["function_call"]["name"],
                                        "arguments": json.dumps(func_call_data["function_call"]["arguments"])
                                    }
                                }]
                                finish_reason = "tool_calls"
                                response_text = None  # No content when tool is called
                        except json.JSONDecodeError:
                            pass  # Not a function call, treat as normal response

                    # Enforce response_format if json_object requested
                    if response_format and response_format.get("type") == "json_object" and response_text:
                        try:
                            json.loads(response_text)
                        except json.JSONDecodeError:
                            logger.warning("Response format json_object requested but response is not valid JSON")

                    # Calculate accurate token usage
                    prompt_tokens = count_message_tokens(trimmed_messages)
                    completion_tokens = count_tokens(response_text) if response_text else 0

                    # Log token optimization stats
                    if len(messages) != len(trimmed_messages):
                        original_tokens = count_message_tokens(messages)
                        saved_tokens = original_tokens - prompt_tokens
                        logger.info(f"Token optimization: {original_tokens} → {prompt_tokens} tokens (saved {saved_tokens}, {saved_tokens*100//original_tokens}%)")

                    # Build message object
                    message_obj = {
                        "role": "assistant",
                        "content": response_text
                    }
                    if tool_calls:
                        message_obj["tool_calls"] = tool_calls

                    # Convert to OpenAI format
                    openai_response = {
                        "id": f"chatcmpl-{int(time.time())}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "message": message_obj,
                                "finish_reason": finish_reason
                            }
                        ],
                        "usage": {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens
                        }
                    }

                    return openai_response
                else:
                    error_text = await response.text()
                    logger.error(f"1minAI API error: {response.status} - {error_text}")

                    error_response = OpenAIErrorResponse(
                        error=OpenAIError(
                            message=f"1minAI API error: {error_text}",
                            type="api_error",
                            param=None,
                            code="provider_error"
                        )
                    )
                    raise HTTPException(status_code=response.status, detail=error_response.model_dump())
    except aiohttp.ClientError as e:
        logger.error(f"1minAI API connection error: {str(e)}")
        error_response = OpenAIErrorResponse(
            error=OpenAIError(
                message=f"Connection to provider failed: {str(e)}",
                type="api_error",
                param=None,
                code="connection_error"
            )
        )
        raise HTTPException(status_code=503, detail=error_response.model_dump())
    except Exception as e:
        logger.error(f"Unexpected error in 1minAI request: {str(e)}")
        error_response = OpenAIErrorResponse(
            error=OpenAIError(
                message=f"Internal error: {str(e)}",
                type="api_error",
                param=None,
                code="internal_error"
            )
        )
        raise HTTPException(status_code=500, detail=error_response.model_dump())
    """
    Make a real request to 1minAI API using the correct endpoint and format.
    """
    if not ONEMINAI_API_KEY:
        error_response = OpenAIErrorResponse(
            error=OpenAIError(
                message="The server is not configured with an API key.",
                type="invalid_request_error",
                param=None,
                code="missing_api_key"
            )
        )
        raise HTTPException(status_code=500, detail=error_response.model_dump())

    # Transform messages to prompt format
    prompt_parts = []
    for msg in messages:
        role = msg.role
        content = msg.content
        if role == "system":
            prompt_parts.append(f"System: {content}")
        elif role == "assistant":
            prompt_parts.append(f"Assistant: {content}")
        else:
            prompt_parts.append(f"User: {content}")

    prompt = "\n\n".join(prompt_parts)

    # Map model names to 1minAI supported format
    model_mapping = {
        "1minai-gpt-4o-mini": "gpt-4o-mini",
        "1minai-gpt-4o": "gpt-4o",
        "1minai-claude-3-5-sonnet": "claude-3-5-sonnet",
        "1minai-claude-3-haiku": "claude-3-haiku",
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-4o": "gpt-4o",
        "claude-3-5-sonnet": "claude-3-5-sonnet",
        "claude-3-haiku": "claude-3-haiku",
        "gemini-2.0-flash": "gemini-2.0-flash",
        "gemini-1.5-flash": "gemini-1.5-flash",
        "gemini-1.5-pro": "gemini-1.5-pro"
    }

    mapped_model = model_mapping.get(model, "gpt-4o-mini")

    # Create 1minAI payload (updated API format)
    payload = {
        "type": "UNIFY_CHAT_WITH_AI",
        "model": mapped_model,
        "promptObject": {
            "prompt": prompt,
            "settings": {
                "webSearchSettings": {
                    "webSearch": False,
                    "numOfSite": 3,
                    "maxWord": 1000
                },
                "historySettings": {
                    "isMixed": False,
                    "historyMessageLimit": 10
                },
                "withMemories": False
            }
        }
    }

    headers = {
        "API-KEY": ONEMINAI_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        logger.info(f"Making request to: https://api.1min.ai/api/chat-with-ai")
        logger.info(f"Using model: {mapped_model}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.1min.ai/api/chat-with-ai",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=45)
            ) as response:
                logger.info(f"1minAI API response status: {response.status}")
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"1minAI API request successful for model: {model}")

                    # Parse 1minAI response format
                    ai_record = result.get("aiRecord", {})
                    ai_record_detail = ai_record.get("aiRecordDetail", {})
                    result_object = ai_record_detail.get("resultObject", [])

                    # Extract response text
                    response_text = ""
                    if isinstance(result_object, list) and result_object:
                        response_text = str(result_object[0])
                    else:
                        response_text = "No response generated"

                    # Enforce response_format if json_object requested
                    if response_format and response_format.get("type") == "json_object":
                        try:
                            json.loads(response_text)  # Validate it's JSON
                        except json.JSONDecodeError:
                            logger.warning("Response format json_object requested but response is not valid JSON")

                    # Calculate accurate token usage
                    prompt_tokens = count_message_tokens(messages)
                    completion_tokens = count_tokens(response_text)

                    # Convert to OpenAI format
                    openai_response = {
                        "id": f"chatcmpl-{int(time.time())}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": response_text
                                },
                                "finish_reason": "stop"
                            }
                        ],
                        "usage": {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens
                        }
                    }

                    return openai_response
                else:
                    error_text = await response.text()
                    logger.error(f"1minAI API error: {response.status} - {error_text}")

                    error_response = OpenAIErrorResponse(
                        error=OpenAIError(
                            message=f"1minAI API error: {error_text}",
                            type="api_error",
                            param=None,
                            code="provider_error"
                        )
                    )
                    raise HTTPException(status_code=response.status, detail=error_response.model_dump())
    except aiohttp.ClientError as e:
        logger.error(f"1minAI API connection error: {str(e)}")
        error_response = OpenAIErrorResponse(
            error=OpenAIError(
                message=f"Connection to provider failed: {str(e)}",
                type="api_error",
                param=None,
                code="connection_error"
            )
        )
        raise HTTPException(status_code=503, detail=error_response.model_dump())
    except Exception as e:
        logger.error(f"Unexpected error in 1minAI request: {str(e)}")
        error_response = OpenAIErrorResponse(
            error=OpenAIError(
                message=f"Internal error: {str(e)}",
                type="api_error",
                param=None,
                code="internal_error"
            )
        )
        raise HTTPException(status_code=500, detail=error_response.model_dump())

async def make_fallback_request(messages: List[ChatMessage], model: str, temperature: float = 0.7, max_tokens: Optional[int] = None, response_format: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Make a request using LiteLLM to fallback providers manually.
    Iterates through providers and logs specific errors for each.
    """
    logger.info(f"Initiating MANUAL fallback sequence for model: {model}")
    
    # Convert Pydantic messages to dict, preserving tool-related fields
    msg_list = []
    for m in messages:
        msg_dict = {"role": m.role, "content": m.content}

        # Preserve tool_calls for assistant messages
        if hasattr(m, 'tool_calls') and m.tool_calls:
            msg_dict["tool_calls"] = m.tool_calls

        # Preserve tool_call_id and name for tool messages
        if m.role == "tool":
            if hasattr(m, 'tool_call_id') and m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if hasattr(m, 'name') and m.name:
                msg_dict["name"] = m.name

        msg_list.append(msg_dict)
    
    # Define fallback chain dynamically
    fallback_chain = []
    
    # 1. OpenRouter (Up to 3 keys)
    for i, key in enumerate(OPENROUTER_KEYS):
        if key:
            fallback_chain.append({
                "provider": f"OpenRouter (Key {i+1})",
                "model": OPENROUTER_MODEL,
                "api_key": key,
                "extra_headers": {
                    "HTTP-Referer": "https://guidegraph.com",
                    "X-Title": "Medical Triage Bot"
                }
            })
            
    # 2. Mistral Native (Up to 3 keys)
    for i, key in enumerate(MISTRAL_KEYS):
        if key:
            fallback_chain.append({
                "provider": f"Mistral (Key {i+1})",
                "model": MISTRAL_MODEL,
                "api_key": key,
                "extra_headers": None
            })
            
    # 3. Gemini Native (Up to 3 keys)
    for i, key in enumerate(GEMINI_KEYS):
        if key:
            fallback_chain.append({
                "provider": f"Gemini (Key {i+1})",
                "model": GEMINI_MODEL,
                "api_key": key,
                "extra_headers": None
            })
        
    if not fallback_chain:
         logger.warning("No fallback keys configured!")
         raise Exception("No fallback providers configured")

    last_exception = None
    
    # Iterate through chain
    for attempt in fallback_chain:
        provider = attempt["provider"]
        model_name = attempt["model"]
        headers = attempt["extra_headers"]
        current_key = attempt["api_key"]
        
        logger.info(f"👉 Trying Fallback: {provider}")
        
        try:
            # We use acompletion for each step manually
            response = await acompletion(
                model=model_name,
                messages=msg_list,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                extra_headers=headers,
                api_key=current_key # Explicitly pass the key for this attempt
            )
            
            # Log success content preview
            content = response.choices[0].message.content if response.choices else ""
            logger.info(f"✅ Fallback SUCCESS: {provider}")
            logger.info(f"Preview: {content[:200]}...")
            
            return response.model_dump()
            
        except Exception as e:
            logger.error(f"❌ Fallback FAILED: {provider} - Error: {str(e)}")
            last_exception = e
            # Continue to next provider...

    # If we get here, all failed
    logger.error("🔥 All fallbacks exhausted (tried up to 9 keys).")
    raise last_exception or Exception("All fallbacks failed")

async def get_1minai_models() -> List[Dict[str, Any]]:
    """
    Get available models from 1minAI.
    """
    if not ONEMINAI_API_KEY:
        logger.warning("ONEMINAI_API_KEY not configured")
        return []
    
    # Return supported models
    models = [
        {
            "id": "gpt-4o-mini",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "1minai"
        },
        {
            "id": "gemini-2.0-flash",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "1minai"
        },
        {
            "id": "gemini-1.5-flash",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "1minai"
        },
        {
            "id": "gemini-1.5-pro",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "1minai"
        },
        {
            "id": "gpt-4o-mini",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "1minai"
        },
        {
            "id": "gpt-4o",
            "object": "model", 
            "created": int(time.time()),
            "owned_by": "1minai"
        },
        {
            "id": "claude-3-5-sonnet",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "1minai"
        },
        {
            "id": "claude-3-haiku",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "1minai"
        },
    ]
    
    logger.info(f"Returning {len(models)} 1minAI models")
    return models

# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for service monitoring."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        service="litellm-1minai-proxy-rag-superbot",
        version="1.1.0"
    )

# Chat completion endpoint
@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    OpenAI-compatible chat completions endpoint.
    Supports both streaming and non-streaming responses.
    Proxies requests to 1minAI, with fallback to OpenRouter/Mistral/Gemini.
    Requires valid API key authentication.
    """
    try:
        # Log request for debugging (without sensitive data)
        logger.info(f"Chat completion request for model: {request.model}")
        logger.info(f"Request messages: {len(request.messages)} messages")
        logger.info(f"Parameters: temp={request.temperature}, top_p={request.top_p}, max_tokens={request.max_tokens}, stream={request.stream}")

        # Handle streaming requests
        if request.stream:
            logger.info("Streaming request detected")

            async def generate_stream():
                try:
                    # Get non-streaming response first (1minAI supports streaming via query param)
                    response = await make_1minai_request(
                        messages=request.messages,
                        model=request.model,
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                        response_format=request.response_format,
                        top_p=request.top_p,
                        stop=request.stop,
                        tools=request.tools,
                        tool_choice=request.tool_choice
                    )

                    # Convert to streaming format
                    content = response["choices"][0]["message"]["content"]
                    request_id = response["id"]

                    async for chunk in stream_openai_chunks(content, request.model, request_id):
                        yield chunk

                    # Ensure stream is properly terminated
                    logger.info(f"Stream completed for request {request_id}")

                except Exception as e:
                    logger.error(f"Streaming error: {str(e)}")
                    # Send error as SSE
                    error_chunk = {
                        "error": {
                            "message": str(e),
                            "type": "api_error",
                            "code": "streaming_error"
                        }
                    }
                    yield f"data: {json.dumps(error_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                finally:
                    # Ensure cleanup happens
                    logger.info("Streaming generator cleanup completed")

            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "Transfer-Encoding": "chunked",
                    "Keep-Alive": "timeout=5, max=100"
                }
            )

        # Non-streaming request
        # 1. Try 1minAI API (updated to UNIFY_CHAT_WITH_AI format)
        try:
            logger.info(f"Attempting primary provider: 1minAI ({request.model})")
            return await make_1minai_request(
                messages=request.messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                response_format=request.response_format,
                top_p=request.top_p,
                stop=request.stop,
                tools=request.tools,
                tool_choice=request.tool_choice
            )

        except Exception as e_primary:
            logger.error(f"Primary provider (1minAI) failed: {str(e_primary)}")

            # 2. Try Fallbacks
            try:
                logger.info("Attempting fallback providers...")
                result = await make_fallback_request(
                    messages=request.messages,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    response_format=request.response_format
                )

                # Convert dict result to response model
                response = ChatCompletionResponse(
                    id=result.get("id", f"chatcmpl-{datetime.utcnow().timestamp()}"),
                    created=result.get("created", int(datetime.utcnow().timestamp())),
                    model=result.get("model", "fallback-model"),
                    choices=result.get("choices", []),
                    usage=result.get("usage", {})
                )
                return response

            except Exception as e_fallback:
                logger.error(f"All fallbacks failed: {str(e_fallback)}")

                # Return OpenAI-compliant error response
                error_response = OpenAIErrorResponse(
                    error=OpenAIError(
                        message=f"All providers unavailable. Fallback error: {str(e_fallback)[:200]}",
                        type="api_error",
                        param=None,
                        code="service_unavailable"
                    )
                )
                raise HTTPException(status_code=503, detail=error_response.model_dump())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat completions: {str(e)}")
        error_response = OpenAIErrorResponse(
            error=OpenAIError(
                message=f"Internal server error: {str(e)}",
                type="api_error",
                param=None,
                code="internal_error"
            )
        )
        raise HTTPException(status_code=500, detail=error_response.model_dump())

# Models endpoint
@app.get("/v1/models")
async def list_models(api_key: str = Depends(verify_api_key)):
    """List available models from 1minAI. Requires API key authentication."""
    try:
        # Get models
        models = await get_1minai_models()
        
        if models:
            logger.info(f"Retrieved {len(models)} models from 1minAI")
            return {
                "object": "list",
                "data": models
            }
        else:
            # Fallback to default model
            logger.warning("Failed to get models from 1minAI, using fallback")
            return {
                "object": "list",
                "data": [
                    {
                        "id": "gpt-4o-mini",
                        "object": "model",
                        "created": int(datetime.utcnow().timestamp()),
                        "owned_by": "1minai"
                    }
                ]
            }
    except Exception as e:
        logger.error(f"Error getting models: {str(e)}")
        # Return fallback models
        return {
            "object": "list",
            "data": [
                {
                    "id": "gpt-4o-mini",
                    "object": "model",
                    "created": int(datetime.utcnow().timestamp()),
                    "owned_by": "1minai"
                }
            ]
        }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "LiteLLM 1minAI Proxy for RAG Superbot",
        "version": "1.1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "chat_completions": "/v1/chat/completions",
            "models": "/v1/models"
        },
        "features": {
            "primary_provider": "1minAI",
            "fallbacks_enabled": True,
            "fallback_providers": ["OpenRouter", "Mistral", "Gemini"]
        }
    }

if __name__ == "__main__":
    # Configuration
    host = os.getenv("FASTAPI_HOST", "0.0.0.0")
    port = int(os.getenv("FASTAPI_PORT", "8000"))
    
    logger.info(f"Starting LiteLLM 1minAI Proxy server on {host}:{port}")
    logger.info(f"1minAI API Key configured: {bool(ONEMINAI_API_KEY)}")
    
    # Connect and count available keys
    or_count = len([k for k in OPENROUTER_KEYS if k])
    mi_count = len([k for k in MISTRAL_KEYS if k])
    ge_count = len([k for k in GEMINI_KEYS if k])
    logger.info(f"Fallback Keys active: OpenRouter={or_count}/3, Mistral={mi_count}/3, Gemini={ge_count}/3")
    
    # Run the server
    uvicorn.run(
        "fastapi_server:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
        timeout_keep_alive=5,
        limit_concurrency=100,
        limit_max_requests=1000
    )
