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

import base64
import datetime
import json
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.load_memory_tool import load_memory_tool
from google.adk.tools.preload_memory_tool import preload_memory_tool
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback

FIRESTORE_PROJECT = "qwiklabs-gcp-02-68959e46a2d9"
STORAGE_BUCKET = "travel-concierge-assets-qwiklabs-gcp-02-68959e46a2d9"

db = firestore.Client(project=FIRESTORE_PROJECT)
genai_client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT, location="global")
storage_client = storage.Client(project=FIRESTORE_PROJECT)

# Load Agent Engine resource name from deployment_metadata.json if available
metadata_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deployment_metadata.json"
)
agent_engine_resource_name = None
agent_engine_id = None
if os.path.exists(metadata_path):
    try:
        with open(metadata_path, "r") as f:
            meta = json.load(f)
            agent_engine_resource_name = meta.get("remote_agent_runtime_id")
            if agent_engine_resource_name:
                agent_engine_id = agent_engine_resource_name.split("/")[-1]
    except Exception:
        pass

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
)

memory_service = None
if agent_engine_id:
    memory_service = VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT,
        location="us-east1",
        agent_engine_id=agent_engine_id,
    )



def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

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


def calculate(expression: str) -> str:
    """Safely evaluates a basic mathematical expression.

    Args:
        expression: A mathematical expression string, e.g., '12 * 4' or '100 / 4'.

    Returns:
        The numerical result of the calculation.
    """
    try:
        allowed = set("0123456789+-*/(). ")
        if not all(c in allowed for c in expression):
            return "Error: Invalid characters in expression."
        result = eval(expression, {"__builtins__": None}, {})
        return str(result)
    except Exception as e:
        return f"Calculation error: {e}"


def convert_temperature(value: float, from_unit: str, to_unit: str) -> str:
    """Converts temperature between Celsius and Fahrenheit.

    Args:
        value: The numerical temperature value.
        from_unit: Unit to convert from ('C' or 'F').
        to_unit: Unit to convert to ('C' or 'F').

    Returns:
        Converted temperature string.
    """
    from_u = from_unit.strip().upper()
    to_u = to_unit.strip().upper()
    if from_u == "C" and to_u == "F":
        res = (value * 9 / 5) + 32
        return f"{value}°C is {res:.2f}°F"
    elif from_u == "F" and to_u == "C":
        res = (value - 32) * 5 / 9
        return f"{value}°F is {res:.2f}°C"
    return f"{value} {from_unit}"


def get_destinations(category: str = "", max_cost: int = 0) -> str:
    """Retrieves travel destinations from the Firestore database.

    Args:
        category: Optional category filter (e.g. 'Urban & Culture', 'Culture & Heritage', 'Beach & Wellness').
        max_cost: Optional maximum average daily cost in USD to filter destinations.

    Returns:
        A list of matching travel destination records.
    """
    try:
        ref = db.collection("destinations")
        docs = ref.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            if category and category.lower() not in data.get("category", "").lower():
                continue
            if max_cost and max_cost > 0 and data.get("avg_cost_usd", 0) > max_cost:
                continue
            results.append(data)
        if not results:
            return "No matching travel destinations found in database."
        return str(results)
    except Exception as e:
        return f"Error retrieving destinations: {e}"


def add_destination(
    name: str,
    country: str,
    category: str,
    avg_cost_usd: int,
    description: str,
    popular_spots: str,
) -> str:
    """Adds a new travel destination to the Firestore database.

    Args:
        name: Name of the city or destination (e.g., 'Kyoto', 'Barcelona').
        country: Country name (e.g., 'Japan', 'Spain').
        category: Category (e.g., 'Culture & Heritage', 'Beach & Wellness', 'Food & Wine').
        avg_cost_usd: Estimated average daily cost per person in USD.
        description: Brief summary of what makes this destination special.
        popular_spots: Comma-separated list of top attractions or landmarks.

    Returns:
        Confirmation message with doc ID.
    """
    try:
        doc_id = f"{name.lower().replace(' ', '-')}-{country.lower().replace(' ', '-')}"
        spots_list = [s.strip() for s in popular_spots.split(",") if s.strip()]
        doc_data = {
            "id": doc_id,
            "name": name,
            "country": country,
            "category": category,
            "avg_cost_usd": int(avg_cost_usd),
            "description": description,
            "popular_spots": spots_list,
        }
        db.collection("destinations").document(doc_id).set(doc_data)
        return f"Successfully added destination '{name}, {country}' (ID: {doc_id}) to Firestore."
    except Exception as e:
        return f"Error adding destination: {e}"


def book_itinerary_item(
    destination_name: str,
    activity_name: str,
    travel_date: str,
    user_id: str = "default_user",
) -> str:
    """Saves a booked activity or itinerary item for a user into Firestore.

    Args:
        destination_name: Name of the destination city (e.g. 'Tokyo', 'Paris').
        activity_name: Name of the activity, tour, or booking (e.g. 'Senso-ji Temple Tour').
        travel_date: Date of the activity in YYYY-MM-DD format.
        user_id: Optional user identifier (defaults to 'default_user').

    Returns:
        A confirmation message with the booking ID.
    """
    try:
        timestamp_id = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        booking_id = f"book-{destination_name.lower().replace(' ', '-')}-{timestamp_id}"
        doc_data = {
            "booking_id": booking_id,
            "user_id": user_id,
            "destination_name": destination_name,
            "activity_name": activity_name,
            "travel_date": travel_date,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        db.collection("itineraries").document(booking_id).set(doc_data)
        return f"Successfully booked '{activity_name}' in {destination_name} for {travel_date}. Booking ID: {booking_id}"
    except Exception as e:
        return f"Error booking itinerary item: {e}"


def get_exchange_rates(base_currency: str = "USD") -> str:
    """Fetches real-time live currency exchange rates for travel expense planning.

    Args:
        base_currency: 3-letter currency code to get rates for (e.g. 'USD', 'EUR', 'GBP').

    Returns:
        A summary string of live exchange rates.
    """
    try:
        base = base_currency.strip().upper()
        api_key = os.environ.get("EXCHANGE_RATE_API_KEY", "")
        url = f"https://open.er-api.com/v6/latest/{base}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "TravelConciergeAgent/1.0"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("result") == "success":
                rates = data.get("rates", {})
                target_currencies = [
                    "USD",
                    "EUR",
                    "GBP",
                    "JPY",
                    "AUD",
                    "CAD",
                    "CHF",
                    "CNY",
                ]
                filtered_rates = {
                    c: rates[c] for c in target_currencies if c in rates and c != base
                }
                return f"Live exchange rates for 1 {base}: {filtered_rates}"
            return f"Failed to fetch exchange rates: {data.get('error-type', 'Unknown error')}"
    except Exception as e:
        return f"Error fetching exchange rates: {e}"


def geocode_address(address: str) -> str:
    """Converts a street address or location name into geographic coordinates (latitude and longitude).

    Args:
        address: The address or location name to geocode (e.g. 'Shibuya Crossing, Tokyo').

    Returns:
        Formatted string containing coordinates and formatted address.
    """
    try:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
        if not api_key or api_key == "PASTE_KEY_HERE":
            return "Error: GOOGLE_MAPS_API_KEY is not configured in environment."

        params = urllib.parse.urlencode({"address": address, "key": api_key})
        url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "TravelConciergeAgent/1.0"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "OK" and data.get("results"):
                res = data["results"][0]
                loc = res["geometry"]["location"]
                fmt_addr = res["formatted_address"]
                return f"Address: '{fmt_addr}' -> Latitude: {loc['lat']}, Longitude: {loc['lng']}"
            return f"Geocoding failed: {data.get('status', 'NO_RESULTS')}"
    except Exception as e:
        return f"Error geocoding address: {e}"


def search_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "restaurant",
    radius_meters: int = 1000,
) -> str:
    """Finds nearby places of a given type around a latitude/longitude coordinate using Places API (New).

    Args:
        latitude: Center latitude coordinate.
        longitude: Center longitude coordinate.
        place_type: Type of place to search for (e.g. 'restaurant', 'tourist_attraction', 'cafe', 'hotel').
        radius_meters: Radius in meters around center point (default 1000m).

    Returns:
        Formatted list of nearby places with name, address, and location.
    """
    try:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
        if not api_key or api_key == "PASTE_KEY_HERE":
            return "Error: GOOGLE_MAPS_API_KEY is not configured in environment."

        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
            "User-Agent": "TravelConciergeAgent/1.0",
        }
        payload = {
            "includedTypes": [place_type],
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": float(latitude),
                        "longitude": float(longitude),
                    },
                    "radius": float(radius_meters),
                }
            },
        }
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=req_data, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            places = data.get("places", [])
            if not places:
                return f"No nearby '{place_type}' places found within {radius_meters}m."
            results = []
            for p in places[:5]:
                name = p.get("displayName", {}).get("text", "Unknown")
                addr = p.get("formattedAddress", "No address")
                loc = p.get("location", {})
                results.append(
                    f"Name: {name} | Address: {addr} | Location: ({loc.get('latitude')}, {loc.get('longitude')})"
                )
            return "\n".join(results)
    except Exception as e:
        return f"Error searching nearby places: {e}"


def generate_destination_image(
    prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generates a scenic travel destination image using gemini-3.1-flash-lite-image model in global region,
    saves it with tool_context.save_artifact for Playground Artifacts, and uploads it to Cloud Storage.

    Args:
        prompt: Description of the travel destination image to generate (e.g. 'A scenic photo of Eiffel Tower in Paris at sunset').
        tool_context: Injected ADK ToolContext.

    Returns:
        The public HTTPS URL of the uploaded image.
    """
    try:
        resp = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )
        parts = [
            p
            for p in resp.candidates[0].content.parts
            if getattr(p, "inline_data", None)
        ]
        if not parts:
            return "Failed to generate image from model."

        image_bytes = parts[0].inline_data.data
        mime_type = parts[0].inline_data.mime_type or "image/jpeg"

        timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        safe_name = "".join(c if c.isalnum() else "_" for c in prompt[:20].lower())
        filename = f"gen_{safe_name}_{timestamp}.jpg"

        # 1. Save artifact for Playground Artifacts panel
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename, artifact_part)

        # 2. Upload directly to public Cloud Storage bucket without writing local file
        bucket = storage_client.bucket(STORAGE_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{STORAGE_BUCKET}/{filename}"
        return f"Successfully generated image. Public URL: {public_url}"
    except Exception as e:
        return f"Error generating image: {e}"


def generate_destination_video(
    prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generates a short destination video using Google's Omni model (gemini-omni-flash-preview) in global region,
    saves it with tool_context.save_artifact for Playground Artifacts, and uploads it to Cloud Storage.

    Args:
        prompt: Description of the destination video to generate (e.g. 'A scenic short video of Kyoto cherry blossoms in spring').
        tool_context: Injected ADK ToolContext.

    Returns:
        The public HTTPS URL of the uploaded video.
    """
    try:
        resp = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )
        video_bytes = None
        mime_type = "video/mp4"

        output_vid = getattr(resp, "output_video", None)
        if output_vid:
            if isinstance(output_vid, dict):
                raw_data = output_vid.get("data") or output_vid.get("bytes")
                mime_type = output_vid.get("mime_type") or mime_type
            else:
                raw_data = getattr(output_vid, "data", None) or getattr(output_vid, "bytes", None)
                mime_type = getattr(output_vid, "mime_type", None) or mime_type

            if isinstance(raw_data, str):
                video_bytes = base64.b64decode(raw_data)
            elif isinstance(raw_data, bytes):
                video_bytes = raw_data

        if not video_bytes:
            return "Failed to extract video bytes from gemini-omni-flash-preview response."

        timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        safe_name = "".join(c if c.isalnum() else "_" for c in prompt[:20].lower())
        filename = f"vid_{safe_name}_{timestamp}.mp4"

        # 1. Save artifact for Playground Artifacts panel
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename, artifact_part)

        # 2. Upload directly to public Cloud Storage bucket without writing local file
        bucket = storage_client.bucket(STORAGE_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{STORAGE_BUCKET}/{filename}"
        return f"Successfully generated video. Public URL: {public_url}"
    except Exception as e:
        return f"Error generating video: {e}"


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are a helpful Travel Concierge AI assistant. You can generate scenic destination images, geocode locations, search nearby places, "
        "look up travel destinations, fetch live currency exchange rates, book itinerary items, add new destinations to Firestore database, check weather, calculate costs, and convert temperatures. "
        "You can also safely execute Python code in a secure Agent Engine sandbox when needed. "
        "IMPORTANT: Always remember and track user preferences, especially all food allergies and dietary restrictions (e.g. peanuts, gluten, shellfish, dairy). "
        "Use your memory tools to recall and check for user allergies before suggesting restaurants, planning meals, or booking activities, ensuring all recommendations strictly comply with their health requirements."
    ),
    workflow_description="Analyze the request, execute necessary tools if needed, and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=code_executor,
    after_model_callback=a2ui_callback,
    tools=[
        preload_memory_tool,
        load_memory_tool,
        get_weather,
        get_current_time,
        calculate,
        convert_temperature,
        get_destinations,
        add_destination,
        book_itinerary_item,
        get_exchange_rates,
        geocode_address,
        search_nearby_places,
        generate_destination_image,
        generate_destination_video,
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)






