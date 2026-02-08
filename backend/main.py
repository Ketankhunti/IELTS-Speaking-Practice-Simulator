import asyncio
import base64
import io
import json
import os
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - handled for local runs without deps
    AsyncOpenAI = None

SYSTEM_PROMPT = (
    "You are a strict, professional IELTS Speaking Examiner. "
    "Your name is Mr./Ms. Patel. You are NOT a helpful assistant. "
    "You are an examiner. Keep responses short, formal, and ask one question."
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass
class SessionState:
    audio_bytes: bytearray
    transcript: str = ""
    assistant_text: str = ""


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _client() -> Optional[AsyncOpenAI]:
    if AsyncOpenAI is None:
        return None
    if not os.getenv("OPENAI_API_KEY"):
        return None
    return AsyncOpenAI()


async def _transcribe_audio(audio_bytes: bytes) -> str:
    client = _client()
    if client is None:
        return "I am practicing speaking about my hometown and work."

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "audio.webm"
    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
    )
    return response.text


async def _stream_assistant_response(transcript: str) -> AsyncGenerator[str, None]:
    client = _client()
    if client is None:
        canned = "Thank you. Do you work or are you a student?"
        for chunk in canned.split(" "):
            yield f"{chunk} "
            await asyncio.sleep(0.05)
        return

    stream = await client.chat.completions.create(
        model="gpt-4o-mini",
        stream=True,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
    )

    async for event in stream:
        delta = event.choices[0].delta.content
        if delta:
            yield delta


async def _stream_tts_audio(text: str) -> AsyncGenerator[bytes, None]:
    client = _client()
    if client is None:
        # No TTS available; return empty generator.
        return

    async with client.audio.speech.with_streaming_response.create(
        model="tts-1",
        voice="onyx",
        input=text,
        response_format="mp3",
    ) as response:
        async for chunk in response.iter_bytes():
            if chunk:
                yield chunk


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    state = SessionState(audio_bytes=bytearray())

    async def send_event(payload: dict) -> None:
        await websocket.send_text(json.dumps(payload))

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                state.audio_bytes.extend(message["bytes"])
                await send_event({"type": "audio_chunk_received", "size": len(message["bytes"])})
                continue

            if "text" in message and message["text"]:
                payload = json.loads(message["text"])
                msg_type = payload.get("type")
                if msg_type == "reset":
                    state = SessionState(audio_bytes=bytearray())
                    await send_event({"type": "reset_ack"})
                if msg_type == "stop":
                    await send_event({"type": "processing"})
                    transcript = await _transcribe_audio(bytes(state.audio_bytes))
                    state.transcript = transcript
                    await send_event({"type": "transcript", "text": transcript})

                    assistant_parts = []
                    async for delta in _stream_assistant_response(transcript):
                        assistant_parts.append(delta)
                        await send_event({"type": "assistant_delta", "text": delta})

                    state.assistant_text = "".join(assistant_parts).strip()

                    if state.assistant_text:
                        async for audio_chunk in _stream_tts_audio(state.assistant_text):
                            await send_event(
                                {
                                    "type": "audio_chunk",
                                    "data": base64.b64encode(audio_chunk).decode("utf-8"),
                                }
                            )

                    await send_event({"type": "done"})
    except WebSocketDisconnect:
        return
    except Exception as exc:  # pragma: no cover - best effort
        await send_event({"type": "error", "message": str(exc)})
