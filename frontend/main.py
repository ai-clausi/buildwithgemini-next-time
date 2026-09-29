"""FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.
"""

import os
import uuid
from typing import Any

from dotenv import load_dotenv
import google.auth
import google.auth.transport.requests
from google.protobuf import json_format
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    Message,
    Part,
    Role,
    SendMessageConfiguration,
    SendMessageRequest,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore

load_dotenv()

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-03-63911e77f35b")
RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/998359341118/locations/us-east1/reasoningEngines/7898414345896329216",
)
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"
_A2UI_MIME = "application/json+a2ui"

_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


_contexts: dict[str, str] = {}
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard()
        json_format.ParseDict(resp.json(), card, ignore_unknown_fields=True)
        _card = card
    return _card


def _extract_dict_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        # Plain text
        if "text" in p and p["text"]:
            out.append({"kind": "text", "text": p["text"]})
        # Data / A2UI
        data_obj = p.get("data")
        if isinstance(data_obj, dict):
            # Check if this is wrapped like {'metadata': {'mimeType': ...}, 'data': {...}}
            meta = data_obj.get("metadata") or p.get("metadata") or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else None
            payload = data_obj.get("data", data_obj)
            if mime == _A2UI_MIME or (isinstance(payload, dict) and any(k in payload for k in ["beginRendering", "surfaceUpdate", "dataModelUpdate"])):
                out.append({"kind": "a2ui", "data": payload})
            elif isinstance(payload, dict) and "text" in payload:
                out.append({"kind": "text", "text": payload["text"]})
        elif p.get("url"):
            out.append({"kind": "text", "text": p["url"]})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict[str, Any]] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(ClientConfig(httpx_client=client))
        a2a_client = factory.create(card)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.ROLE_USER,
            parts=[Part(text=message)],
            context_id=_contexts.get(user_id, ""),
        )
        send_req = SendMessageRequest(
            message=msg,
            configuration=SendMessageConfiguration(),
        )

        async for event in a2a_client.send_message(send_req):
            d = json_format.MessageToDict(event, preserving_proto_field_name=True)
            # Track context_id
            for top_key in ["task", "status_update", "artifact_update"]:
                if top_key in d:
                    ctx = d[top_key].get("context_id")
                    if ctx:
                        _contexts[user_id] = ctx

            # Extract parts from artifact_update
            if "artifact_update" in d:
                art = d["artifact_update"].get("artifact", {})
                parts.extend(_extract_dict_parts(art.get("parts", [])))

            # Extract parts from task.artifacts (if completed or non-streaming)
            if "task" in d:
                for art in d["task"].get("artifacts", []):
                    parts.extend(_extract_dict_parts(art.get("parts", [])))

            # Extract direct message parts if present
            if "message" in d:
                parts.extend(_extract_dict_parts(d["message"].get("parts", [])))

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


@app.get("/api/experiences")
async def get_experiences():
    try:
        db = firestore.Client(project=PROJECT_ID)
        docs = db.collection("experiences").stream()
        results = [d.to_dict() for d in docs]
        return JSONResponse({"experiences": results})
    except Exception as e:
        return JSONResponse({"experiences": [], "error": str(e)})


# Serve the chat UI (keep this mount last so /chat wins).
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
