# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import os
import uuid
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google import genai
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback


MODEL = "gemini-3.6-flash"
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-03-63911e77f35b"
COLLECTION_NAME = "experiences"
ASSETS_BUCKET_NAME = "next-time-assets-xv7djl"
MEMORY_BANK_ID = "7898414345896329216"
SANDBOX_RESOURCE_NAME = (
    "projects/998359341118/locations/us-east1/reasoningEngines/7898414345896329216/sandboxEnvironments/2339136221302751232"
)

# Initialize Firestore and Storage clients with hardcoded project ID
db = firestore.Client(project=FIRESTORE_PROJECT_ID)
storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: after each turn, send the session to Memory Bank for extraction."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


def list_experiences(
    category: Optional[str] = None, tag: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieves logged past experiences and learnings from Firestore.

    Args:
        category: Optional category filter, e.g. 'travel', 'health', 'food'.
        tag: Optional tag filter, e.g. 'packing', 'sleep', 'clothing', 'usa'.

    Returns:
        A list of matching past experiences with lessons and next time advice.
    """
    col = db.collection(COLLECTION_NAME)
    docs = col.stream()
    results = []

    for d in docs:
        data = d.to_dict()
        if category and data.get("category", "").lower() != category.lower():
            continue
        if tag:
            tags = [t.lower() for t in data.get("tags", [])]
            if tag.lower() not in tags:
                continue
        results.append(data)

    return results


def log_experience(
    title: str,
    situation: str,
    lesson: str,
    next_time_advice: str,
    category: str = "general",
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Records a new past experience and takeaway to Firestore so it can be recalled next time.

    Args:
        title: Short title of the experience or lesson.
        situation: What happened or what situation the user was in.
        lesson: What was learned or what went well/poorly.
        next_time_advice: Practical recommendation or reminder for the next time this situation occurs.
        category: Category such as 'travel', 'health', 'food', 'work', or 'general'.
        tags: List of descriptive keyword tags, e.g. ['packing', 'usa'].

    Returns:
        The created experience record confirmation.
    """
    doc_id = f"exp-{uuid.uuid4().hex[:8]}"
    item = {
        "id": doc_id,
        "title": title,
        "situation": situation,
        "lesson": lesson,
        "next_time_advice": next_time_advice,
        "category": category,
        "tags": tags or [],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db.collection(COLLECTION_NAME).document(doc_id).set(item)
    return {"status": "success", "id": doc_id, "data": item}


def compute_packing_recommendations(
    trip_days: int,
    has_laundry: bool = True,
    planned_shopping: bool = True,
) -> Dict[str, Any]:
    """Computes recommended packing quantities and luggage reserve space based on past lessons learned.

    Args:
        trip_days: Total number of days for the trip.
        has_laundry: Whether laundry facilities are available at the destination (default True).
        planned_shopping: Whether shopping for new clothes/souvenirs is planned (default True).

    Returns:
        A dictionary with recommended item counts, laundry cycle advice, and reserved luggage space.
    """
    if has_laundry or trip_days > 7:
        shirts = min(trip_days, 5)
        pants = min(max(2, trip_days // 4), 3)
        underwear = min(trip_days, 6)
    else:
        shirts = trip_days
        pants = max(2, trip_days // 3)
        underwear = trip_days

    suitcase_reserve_pct = 30 if planned_shopping else 10

    return {
        "trip_days": trip_days,
        "has_laundry": has_laundry,
        "planned_shopping": planned_shopping,
        "recommended_items": {
            "shirts": shirts,
            "pants": pants,
            "underwear": underwear,
            "shoes_pairs": 2,
        },
        "suitcase_reserve_pct": suitcase_reserve_pct,
        "advice": (
            f"Based on your USA trip learnings: For a {trip_days}-day trip with laundry, "
            f"pack at most {shirts} shirts and reserve {suitcase_reserve_pct}% suitcase space for purchases."
        ),
    }


import urllib.parse
import urllib.request
import json


def get_destination_weather_forecast(city: str) -> Dict[str, Any]:
    """Fetches real current weather and a multi-day forecast for a travel destination.
    Uses the free public Open-Meteo API (no API key required).

    Args:
        city: The name of the city or destination, e.g. 'San Diego', 'New York', 'Paris'.

    Returns:
        A dictionary containing real temperature in Celsius, precipitation, and daily highs/lows.
    """
    try:
        # Step 1: Geocode city name to lat/long
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "NextTimeApp/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            geo_data = json.loads(resp.read().decode("utf-8"))

        results = geo_data.get("results")
        if not results:
            return {"error": f"Could not find coordinates for city: {city}"}

        match = results[0]
        lat, lon = match["latitude"], match["longitude"]
        city_name = f"{match.get('name')}, {match.get('admin1', '')} ({match.get('country_code', '')})"

        # Step 2: Fetch real weather & 3-day forecast
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,precipitation,weather_code"
            f"&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=3"
        )
        w_req = urllib.request.Request(weather_url, headers={"User-Agent": "NextTimeApp/1.0"})
        with urllib.request.urlopen(w_req, timeout=5) as w_resp:
            weather_data = json.loads(w_resp.read().decode("utf-8"))

        current = weather_data.get("current", {})
        daily = weather_data.get("daily", {})

        return {
            "destination": city_name,
            "current_temperature_celsius": current.get("temperature_2m"),
            "current_precipitation_mm": current.get("precipitation"),
            "forecast_days": [
                {
                    "date": d,
                    "max_temp_celsius": max_t,
                    "min_temp_celsius": min_t,
                }
                for d, max_t, min_t in zip(
                    daily.get("time", []),
                    daily.get("temperature_2m_max", []),
                    daily.get("temperature_2m_min", []),
                )
            ],
        }
    except Exception as e:
        return {"error": f"Failed to retrieve weather for {city}: {str(e)}"}


def search_google_maps_place(query: str) -> Dict[str, Any]:
    """Searches for a place, hotel, or attraction using Google Maps REST API.
    Reads the API key from the GOOGLE_MAPS_API_KEY environment variable.

    Args:
        query: The name or query for the place/hotel, e.g. 'Pacific Beach, San Diego' or 'Hotel del Coronado'.

    Returns:
        A dictionary with key fields: name, address, location (lat/lng), and google_maps_url.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not configured."}

    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={encoded_query}&key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "NextTimeApp/1.0"})

        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("results", [])
        if not results:
            return {"error": f"No places found matching '{query}'."}

        top_match = results[0]
        geometry_loc = top_match.get("geometry", {}).get("location", {})
        lat = geometry_loc.get("lat")
        lng = geometry_loc.get("lng")

        # Static map image URL preview using the same key
        static_map_url = (
            f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lng}&zoom=14&size=400x250"
            f"&markers=color:red%7C{lat},{lng}&key={api_key}"
        )

        return {
            "name": top_match.get("name"),
            "address": top_match.get("formatted_address"),
            "location": {"latitude": lat, "longitude": lng},
            "rating": top_match.get("rating"),
            "user_ratings_total": top_match.get("user_ratings_total"),
            "google_maps_url": f"https://www.google.com/maps/search/?api=1&query={encoded_query}",
            "static_map_url": static_map_url,
        }
    except Exception as e:
        return {"error": f"Failed to search place on Google Maps: {str(e)}"}


def create_multi_location_map(
    locations: List[str],
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates a combined Google Maps static map image showing multiple locations, spots, or attractions simultaneously.
    Use this whenever an answer recommends or references multiple places, stops, or highlights.

    Args:
        locations: List of place names, addresses, or queries, e.g. ['Santa Monica Pier, LA', 'Griffith Observatory, LA', 'Venice Beach, LA'].
        title: Optional title for this route or list of spots.

    Returns:
        A dictionary containing the combined static_map_url, google_maps_url, and the resolved locations list.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY is not configured."}

    resolved = []
    markers_params = []
    colors = ["red", "blue", "green", "orange", "purple", "yellow"]

    for idx, loc in enumerate(locations[:8]):
        try:
            encoded_query = urllib.parse.quote(loc)
            url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={encoded_query}&key={api_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "NextTimeApp/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            if results:
                match = results[0]
                lat = match.get("geometry", {}).get("location", {}).get("lat")
                lng = match.get("geometry", {}).get("location", {}).get("lng")
                name = match.get("name", loc)
                resolved.append({"name": name, "address": match.get("formatted_address"), "lat": lat, "lng": lng})
                color = colors[idx % len(colors)]
                label = str(idx + 1)
                markers_params.append(f"&markers=color:{color}%7Clabel:{label}%7C{lat},{lng}")
        except Exception:
            continue

    if not resolved:
        return {"error": "Could not resolve any of the provided locations on Google Maps."}

    markers_str = "".join(markers_params)
    static_map_url = (
        f"https://maps.googleapis.com/maps/api/staticmap?size=600x350"
        f"{markers_str}&key={api_key}"
    )
    query_str = urllib.parse.quote(" + ".join([r["name"] for r in resolved]))
    google_maps_url = f"https://www.google.com/maps/search/?api=1&query={query_str}"

    return {
        "title": title or "Map of Places",
        "resolved_locations": resolved,
        "static_map_url": static_map_url,
        "google_maps_url": google_maps_url,
    }


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


async def generate_and_upload_visual_reminder(
    prompt: str,
    item_title: str,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """Generates an illustrative visual reminder image for an activity, item, or memory
    using the gemini-3.1-flash-lite-image model in the global region.
    Saves the image as an artifact in the session and uploads it to the public Cloud Storage bucket.

    Args:
        prompt: Detailed visual prompt describing the scene, packing item, hotel, or memory illustration.
        item_title: Short identifier/title for the file name (e.g., 'san_diego_beach' or 'tshirt_packing').

    Returns:
        A dictionary with the public Cloud Storage URL and the saved artifact filename.
    """
    try:
        # Initialize Google GenAI client pointing to Vertex AI in global location
        client = genai.Client()
        gen_response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=dict(
                response_modalities=["IMAGE"],
            ),
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if gen_response.candidates and gen_response.candidates[0].content.parts:
            for part in gen_response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return {"error": "Model did not return any image bytes."}

        extension = "png" if "png" in mime_type else "jpg"
        clean_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in item_title.lower()).strip("_")
        unique_suffix = uuid.uuid4().hex[:8]
        filename = f"{clean_title}_{unique_suffix}.{extension}"

        # 1. Save with tool_context.save_artifact so it shows up in Playground's Artifacts panel
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload the same image bytes to the public Cloud Storage bucket
        bucket = storage_client.bucket(ASSETS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{ASSETS_BUCKET_NAME}/{filename}"

        return {
            "artifact_filename": filename,
            "public_url": public_url,
            "mime_type": mime_type,
            "message": f"Successfully generated visual reminder and uploaded to {public_url}",
        }
    except Exception as e:
        return {"error": f"Failed to generate or upload visual reminder: {str(e)}"}


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are 'Next Time', an intelligent assistant that helps users learn from their past experiences "
        "and avoid making the same mistakes twice. "
        "You maintain a clear separation between long-term user memory (Memory Bank) and specific experiences (Firestore):\n"
        "1. USER PROFILE & PREFERENCES (Memory Bank): Automatically remember general user traits, habits, and preferences "
        "(e.g., travel style like 'carry-on only', dietary restrictions, morning habits, noise sensitivity, preferred units like Celsius). "
        "Actively acknowledge and apply these cross-session memories in every recommendation you give.\n"
        "2. CONCRETE EXPERIENCES & LESSONS (Firestore): Query list_experiences when discussing past trips, specific events, "
        "or specific items/destinations to retrieve detailed historical lessons and 'next time' takeaways. "
        "When the user shares a specific event lesson or mistake (e.g. '7 t-shirts were too many in USA'), store it using log_experience.\n"
        "When planning packing for a trip, combine their general habits from Memory Bank with past lessons from Firestore, "
        "use get_destination_weather_forecast to check real weather conditions, "
        "and compute_packing_recommendations to calculate realistic quantities and luggage buffer space. "
        "MAPS & VISUAL LOCATIONS (MANDATORY REQUIREMENT):\n"
        "- When any user question or response touches, lists, recommends, or mentions MULTIPLE places, sights, cities, or stops (for example: highlights in LA, visited places in California, coastal stops, or an itinerary), you MUST call create_multi_location_map with all those places.\n"
        "- Always embed the returned static_map_url as an Image in your A2UI Card so the user sees all locations plotted together on a map.\n"
        "- When referencing only a single place, use search_google_maps_place and embed its static_map_url.\n"
        "VISUAL HIERARCHY & RICH FORMATTING (MANDATORY REQUIREMENT):\n"
        "- Structure every response with bold titles, clear section headers, and formatted bullet lists.\n"
        "- In A2UI Cards, use usageHint 'h1' for the main card title, 'h2' or 'h3' for section headers and takeaway advice, and 'body' for descriptive bullet points.\n"
        "- You CAN and SHOULD use markdown inside the Text literalString (e.g. **Bold Highlight:** or *italics* or bullets) because the UI renders it cleanly!\n"
        "When the user wants a visual reminder, illustration, or graphic card for a memory or packing list, "
        "use generate_and_upload_visual_reminder to create an image, save it to session artifacts, and return its public URL. "
        "You can execute Python code safely in your sandboxed environment to perform precise calculations, data analysis, "
        "or simulations whenever needed. "
        "Always express temperatures in Celsius instead of Fahrenheit."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You MUST include an Image component whenever places/locations are involved, setting url to the "
        "static_map_url from create_multi_location_map or search_google_maps_place. "
        "Set the Image url to that exact https link: {\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. "
        "Never point an Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "Use the usageHint property ('h1', 'h2', 'h3', 'body') for headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=AgentEngineSandboxCodeExecutor(
        sandbox_resource_name=SANDBOX_RESOURCE_NAME,
    ),
    tools=[
        PreloadMemoryTool(),
        list_experiences,
        log_experience,
        compute_packing_recommendations,
        get_destination_weather_forecast,
        search_google_maps_place,
        create_multi_location_map,
        generate_and_upload_visual_reminder,
        get_current_time,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

