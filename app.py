import os

from dotenv import load_dotenv
import httpx
from flask import Flask, jsonify, request
from postgrest import APIError
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in the environment.")

app = Flask(__name__)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.errorhandler(httpx.RequestError)
def handle_upstream_connection_error(_error):
    return jsonify(error="Supabase is unreachable from the app server"), 503


def database_error(error):
    return jsonify(error=getattr(error, "message", "Database request failed")), 500


@app.get("/")
def index():
    return jsonify(message="Events API", endpoints=[
        "/api/events",
        "/api/events/<id>",
        "/api/registrations",
        "/api/me/registrations",
        "/api/events/<id>/registrations",
    ])


@app.get("/api/events")
def list_events():
    try:
        result = supabase.table("events").select("*").execute()
        return jsonify(result.data)
    except APIError as error:
        return database_error(error)


@app.get("/api/events/<event_id>")
def get_event(event_id):
    try:
        result = (
            supabase.table("events")
            .select("*")
            .eq("id", event_id)
            .maybe_single()
            .execute()
        )
        if result.data is None:
            return jsonify(error="Event not found"), 404
        return jsonify(result.data)
    except APIError as error:
        return database_error(error)


@app.post("/api/registrations")
def create_registration():
    payload = request.get_json(silent=True) or {}
    event_id = payload.get("event_id")
    user_id = payload.get("user_id")
    if not event_id or not user_id:
        return jsonify(error="event_id and user_id are required"), 400

    try:
        event_result = (
            supabase.table("events")
            .select("id,capacity")
            .eq("id", event_id)
            .maybe_single()
            .execute()
        )
        event = event_result.data
        if event is None:
            return jsonify(error="Event not found"), 404
        existing = (
            supabase.table("registrations")
            .select("id")
            .eq("event_id", event_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return jsonify(error="You are already registered for this event"), 409

        registrations = (
            supabase.table("registrations")
            .select("id", count="exact")
            .eq("event_id", event_id)
            .execute()
        )
        capacity = event.get("capacity")
        if capacity is not None and (registrations.count or 0) >= capacity:
            return jsonify(error="Event is full"), 409

        created = (
            supabase.table("registrations")
            .insert({"event_id": event_id, "user_id": user_id})
            .execute()
        )
        return jsonify(created.data[0]), 201
    except APIError as error:
        return database_error(error)


@app.get("/api/me/registrations")
def my_registrations():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify(error="user_id query parameter is required"), 400

    try:
        result = (
            supabase.table("registrations")
            .select("*, events(*)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return jsonify(result.data)
    except APIError as error:
        return database_error(error)


@app.get("/api/events/<event_id>/registrations")
def event_registrations(event_id):
    try:
        result = (
            supabase.table("registrations")
            .select("*, users(id,email)")
            .eq("event_id", event_id)
            .order("created_at")
            .execute()
        )
        return jsonify(result.data)
    except APIError as error:
        return database_error(error)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
