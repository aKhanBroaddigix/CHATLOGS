from flask import Flask, request, render_template, redirect, url_for, send_file, jsonify, flash, session
from pymongo import MongoClient
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
import csv
from pytz import timezone, UTC

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'dev'  # Needed for session management

# MongoDB connection details
MONGO_URI = "mongodb+srv://adeelkhan:fpJknTuffiw5WPSh@fernwoodcluster1.shk9y.mongodb.net/?retryWrites=true&w=majority&tls=true"
DATABASE_NAME = "chat-history"
COLLECTION_NAME = "chats"

# Initialize MongoDB client
client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
messages_collection = db[COLLECTION_NAME]

# Hardcoded credentials for login
VALID_USERNAME = "admin"
VALID_PASSWORD = "password123"

MELBOURNE_TZ = timezone("Australia/Melbourne")

def adjust_timestamp(timestamp):
    """Convert UTC timestamp to Melbourne time."""
    if isinstance(timestamp, int):
        # Convert epoch timestamp to datetime
        utc_time = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
    elif isinstance(timestamp, datetime):
        # Assume datetime is UTC if not timezone-aware
        if timestamp.tzinfo is None:
            utc_time = timestamp.replace(tzinfo=UTC)
        else:
            utc_time = timestamp
    else:
        raise ValueError("Unsupported timestamp format")

    # Convert UTC time to Melbourne time
    melbourne_time = utc_time.astimezone(MELBOURNE_TZ)
    return melbourne_time


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("home"))
        else:
            flash("Invalid username or password. Please try again.")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/", methods=["GET"])
def home():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/get-chats", methods=["POST", "GET"])
def get_chats():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        page = 1
        start_date = request.form.get("start_date") or "Start Date"
        end_date = request.form.get("end_date") or "End Date"
    else:
        username = request.args.get("username", "").strip()
        page = int(request.args.get("page", 1))
        start_date = request.args.get("start_date") or "Start Date"
        end_date = request.args.get("end_date") or "End Date"

    items_per_page = 10
    skip_items = (page - 1) * items_per_page
    criteria = {"chats.username": username}

    if start_date != "Start Date" and end_date != "End Date":
        try:
            start_date_parsed = datetime.strptime(start_date, "%Y-%m-%d")
            end_date_parsed = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            criteria["timestamp"] = {
                "$gte": start_date_parsed.replace(tzinfo=MELBOURNE_TZ),
                "$lt": end_date_parsed.replace(tzinfo=MELBOURNE_TZ),
            }
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.")
            return redirect(url_for("get_chats"))

    all_documents = list(
        messages_collection.find(criteria).sort("timestamp", -1).skip(skip_items).limit(items_per_page)
    )

    chats = []
    for document in all_documents:
        chats_data = document.get("chats", {})
        chat_id = chats_data.get("id", "N/A")
        questions = chats_data.get("questions", [])
        if isinstance(questions, str):
            questions = [questions]

        messages = chats_data.get("messages", [])
        if isinstance(messages, dict):
            messages = [messages]

        timestamp = document.get("timestamp")
        adjusted_time = adjust_timestamp(timestamp) if timestamp else None
        formatted_date = adjusted_time.strftime("%d-%b-%Y %I:%M %p") if adjusted_time else "Unknown Date"

        for question, message in zip(questions, messages):
            sanitized_question = question if isinstance(question, str) else "No question available"
            sanitized_answer = (
                message.get("content", "No answer available") if isinstance(message, dict) else "No answer available"
            )
            chat_data = {
                "chat_id": chat_id,
                "question": sanitized_question,
                "answer": sanitized_answer,
                "date": formatted_date
            }
            chats.append(chat_data)

    user_found = len(chats) > 0
    total_chats = messages_collection.count_documents(criteria)
    has_next = page * items_per_page < total_chats
    has_previous = page > 1

    return render_template(
        "chats.html",
        username=username,
        user_found=user_found,
        chats=chats,
        page=page,
        has_next=has_next,
        has_previous=has_previous,
        start_date=start_date,
        end_date=end_date
    )

@app.route("/download-chats/<username>", methods=["GET"])
def download_chats(username):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    all_documents = list(messages_collection.find({"chats.username": username}))
    chats = []

    for document in all_documents:
        chats_data = document.get("chats", {})
        chat_id = chats_data.get("id", "N/A")
        questions = chats_data.get("questions", [])
        if isinstance(questions, str):
            questions = [questions]

        messages = chats_data.get("messages", [])
        if isinstance(messages, dict):
            messages = [messages]

        timestamp = document.get("timestamp")
        adjusted_time = adjust_timestamp(timestamp) if timestamp else None
        formatted_date = adjusted_time.strftime("%d-%b-%Y %I:%M %p") if adjusted_time else "Unknown Date"

        for question, message in zip(questions, messages):
            sanitized_question = str(question).replace('\n', ' ').replace('\r', '').strip()
            sanitized_answer = str(message.get("content", "No answer available")).replace('\n', ' ').replace('\r', '').strip()

            chat_data = {
                "username": username,
                "question": sanitized_question,
                "answer": sanitized_answer,
                "timestamp": formatted_date
            }
            chats.append(chat_data)

    df = pd.DataFrame(chats)
    output = BytesIO()
    df.to_csv(output, index=False, encoding='utf-8', quoting=csv.QUOTE_ALL)
    output.seek(0)

    return send_file(output, mimetype="text/csv", as_attachment=True, download_name=f"{username}_chats.csv")

@app.route("/api/weekly_chat_volume", methods=["GET"])
def weekly_chat_volume():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())

    pipeline = [
        {"$match": {"timestamp": {"$gte": start_of_week.astimezone(UTC)}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp", "timezone": "Australia/Melbourne"}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]

    weekly_data = list(messages_collection.aggregate(pipeline))
    for day in weekly_data:
        day["_id"] = (datetime.strptime(day["_id"], "%Y-%m-%d") - timedelta(hours=1)).strftime("%Y-%m-%d")
    return jsonify(weekly_data)


@app.route("/api/top_chat_contributors", methods=["GET"])
def top_chat_contributors():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    pipeline = [
        {"$group": {"_id": "$chats.username", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    top_contributors = list(messages_collection.aggregate(pipeline))
    return jsonify(top_contributors)
@app.route("/users-with-chats", methods=["GET"])
def users_with_chats():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    pipeline = [
        {
            "$match": {"chats.username": {"$ne": None, "$ne": ""}}
        },
        {
            "$group": {
                "_id": "$chats.username",
                "days": {
                    "$addToSet": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp", "timezone": "Australia/Melbourne"}
                    }
                }
            }
        },
        {"$project": {"_id": 1, "days": {"$size": "$days"}}},
        {"$sort": {"days": -1}}
    ]

    users = list(messages_collection.aggregate(pipeline))
    for user in users:
        user["_id"] = str(user["_id"])
    return jsonify(users)
@app.route("/search-usernames", methods=["GET"])
def search_usernames():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    query = request.args.get("query", "").strip()
    if not query:
        return jsonify([])

    # Search for usernames starting with the query
    results = messages_collection.distinct("chats.username", {"chats.username": {"$regex": f"^{query}", "$options": "i"}})
    return jsonify(results)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=True)
