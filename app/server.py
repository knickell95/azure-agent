#!/usr/bin/env python3
"""FastAPI web server with WebSocket chat interface."""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".azure-agent")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent import AzureAgent

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=10)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    agent = AzureAgent()
    loop = asyncio.get_running_loop()

    try:
        while True:
            message = await websocket.receive_text()

            if message.strip().lower() == "reset":
                agent.reset()
                await websocket.send_json({"type": "reset"})
                continue

            response = await loop.run_in_executor(executor, agent.chat, message)
            await websocket.send_json({"type": "message", "content": response})
    except WebSocketDisconnect:
        pass
