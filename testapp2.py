from flask import Flask, request, render_template, redirect, url_for, send_file, jsonify, flash, session
from pymongo import MongoClient
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
import csv
from pytz import timezone, UTC
import pytz
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
    if isinstance(timestamp, int):
        utc_time = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
    elif isinstance(timestamp, datetime):
        utc_time = timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp
    else:
        raise ValueError("Unsupported timestamp format")
    return utc_time.astimezone(MELBOURNE_TZ)

    # Convert UTC time to Melbourne time
    melbourne_time = utc_time.astimezone(MELBOURNE_TZ)
    return melbourne_time

import os



def get_date_range(filter_option):
    now = datetime.now(MELBOURNE_TZ)
    if filter_option == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)
    elif filter_option == "yesterday":
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=1)
    elif filter_option == "this_week":
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=7)
    elif filter_option == "last_week":
        end_date = now - timedelta(days=now.weekday())
        start_date = end_date - timedelta(days=7)
    elif filter_option == "this_month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = (start_date + timedelta(days=32)).replace(day=1)
    elif filter_option == "last_month":
        start_date = (now.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)  # First day of the current month

    else:
        start_date, end_date = None, None
    return start_date, end_date

@app.route("/api/chats_per_club", methods=["POST"])
def chats_per_club():
    data = request.get_json()
    filter_option = data.get("filter", "")
    start_date = data.get("startDate", "")
    end_date = data.get("endDate", "")

    if filter_option == "custom" and start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ).astimezone(UTC)
        end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ).astimezone(UTC) + timedelta(days=1)
    else:
        start_date, end_date = get_date_range(filter_option)

    if not start_date or not end_date:
        return jsonify({"error": "Invalid date filter"}), 400

    start_date_utc = start_date.astimezone(UTC)
    end_date_utc = end_date.astimezone(UTC)

    try:
        # Load the username-to-club mapping
        username_to_club = pd.read_csv("data/users.csv")
        club_mapping = dict(zip(username_to_club["Email"], username_to_club["Club Name"]))

        # Query MongoDB for chat data
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_date_utc, "$lt": end_date_utc}}},
            {"$project": {"username": "$chats.username"}},
            {"$group": {"_id": "$username", "count": {"$sum": 1}}},
        ]
        chat_data = list(messages_collection.aggregate(pipeline))

        # Map usernames to clubs
        club_counts = {}
        for item in chat_data:
            username = item["_id"]
            count = item["count"]
            club = club_mapping.get(username, "Unknown Club")
            club_counts[club] = club_counts.get(club, 0) + count

        # Format data for the frontend
        formatted_data = [{"club": club, "count": count} for club, count in club_counts.items()]
        return jsonify(formatted_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/filter-charts", methods=["POST"])
def filter_charts():
    data = request.get_json()
    filter_option = data.get("filter", "")
    start_date = data.get("startDate", "")
    end_date = data.get("endDate", "")

    # Get date range
    if filter_option == "custom" and start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ).astimezone(UTC)
        end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ).astimezone(UTC) + timedelta(days=1)
    else:
        start_date, end_date = get_date_range(filter_option)

    if not start_date or not end_date:
        return jsonify({"error": "Invalid date filter"}), 400

    start_date_utc = start_date.astimezone(UTC)
    end_date_utc = end_date.astimezone(UTC)

    try:
        username_filter = {"chats.username": {"$exists": True, "$ne": ""}}

        # Total Chats Counter
        total_chats_count = messages_collection.count_documents({
            "timestamp": {"$gte": start_date_utc, "$lt": end_date_utc},
            **username_filter
        })

        # Ticket Counter
        ticket_count = messages_collection.count_documents({
            "timestamp": {"$gte": start_date_utc, "$lt": end_date_utc},
            "chats.messages.content": {"$regex": "Ticket generated successfully!", "$options": "i"},
            **username_filter
        })

        # Weekly Chat Volume Chart
        weekly_chat_volume_pipeline = [
            {"$match": {"timestamp": {"$gte": start_date_utc, "$lt": end_date_utc}, **username_filter}},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        weekly_chat_volume = list(messages_collection.aggregate(weekly_chat_volume_pipeline))

        # Top Chat Contributors Chart
        top_chat_contributors_pipeline = [
            {"$match": {"timestamp": {"$gte": start_date_utc, "$lt": end_date_utc}, **username_filter}},
            {"$group": {"_id": "$chats.username", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
        top_chat_contributors = list(messages_collection.aggregate(top_chat_contributors_pipeline))

        return jsonify({
            "totalChats": total_chats_count,
            "totalTickets": ticket_count,  # Add the ticket count here
            "weeklyChatVolume": weekly_chat_volume,
            "topChatContributors": top_chat_contributors,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500



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



@app.route("/api/weekly_chat_volume", methods=["GET"])
def weekly_chat_volume():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    try:
        today_melbourne = datetime.now(MELBOURNE_TZ)
        start_of_week_melbourne = today_melbourne - timedelta(days=today_melbourne.weekday())
        start_of_week_melbourne = start_of_week_melbourne.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week_utc = start_of_week_melbourne.astimezone(UTC)

        pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": start_of_week_utc},
                    "chats.username": {"$exists": True, "$ne": ""},
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$timestamp",
                            "timezone": "Australia/Melbourne"
                        }
                    },
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}
        ]

        weekly_data = list(messages_collection.aggregate(pipeline))
        return jsonify(weekly_data)

    except Exception as e:
        print(f"[ERROR] An error occurred in /api/weekly_chat_volume: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/top_chat_contributors", methods=["GET"])
def top_chat_contributors():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    try:
        pipeline = [
            {"$match": {"chats.username": {"$exists": True, "$ne": ""}}},
            {
                "$group": {
                    "_id": "$chats.username",
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]

        top_contributors = list(messages_collection.aggregate(pipeline))
        return jsonify(top_contributors)
    except Exception as e:
        print(f"[ERROR] Error in /api/top_chat_contributors: {str(e)}")
        return jsonify({"error": str(e)}), 500
 #Add username filter to all relevant routes

# Example for /users-with-chats:
@app.route("/users-with-chats", methods=["POST"])
def users_with_chats():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    data = request.get_json()
    filter_option = data.get("filter", "")
    start_date = data.get("startDate", "")
    end_date = data.get("endDate", "")
    username = data.get("username", "").strip()

    if filter_option == "custom" and start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ).astimezone(UTC)
        end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ).astimezone(UTC) + timedelta(days=1)
    else:
        start_date, end_date = get_date_range(filter_option)

    if not start_date or not end_date:
        return jsonify({"error": "Invalid date filter"}), 400

    start_date_utc = start_date.astimezone(UTC)
    end_date_utc = end_date.astimezone(UTC)

    try:
        pipeline = [
            {"$match": {
                "timestamp": {"$gte": start_date_utc, "$lt": end_date_utc},
                "chats.username": {"$exists": True, "$ne": ""}
            }},
        ]

        if username:
            pipeline[0]["$match"]["chats.username"] = {"$regex": f"^{username}$", "$options": "i"}

        pipeline += [
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
            {"$sort": {"days": -1}},
        ]

        users = list(messages_collection.aggregate(pipeline))
        for user in users:
            user["_id"] = str(user["_id"])
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/search-usernames", methods=["GET"])
def search_usernames():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    query = request.args.get("query", "").strip()
    if not query:
        return jsonify([])

    results = messages_collection.distinct(
        "chats.username",
        {
            "chats.username": {"$regex": f"^{query}", "$options": "i", "$ne": ""}
        }
    )
    return jsonify(results)



@app.route("/get-chats-by-date-and-users", methods=["POST", "GET"])
def get_chats_by_date_and_users():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    start_date = request.form.get("start_date", "").strip() if request.method == "POST" else request.args.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip() if request.method == "POST" else request.args.get("end_date", "").strip()
    username = request.form.get("username", "").strip() if request.method == "POST" else request.args.get("username", "").strip()
    page = int(request.args.get("page", 1))
    items_per_page = 15
    skip_items = (page - 1) * items_per_page

    criteria = {"chats.username": {"$exists": True, "$ne": ""}}
    if username:
        criteria["chats.username"] = {"$regex": f"^{username.strip()}$", "$options": "i"}

    try:
        if start_date and end_date:
            date_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ)
            date_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ) + timedelta(days=1)
            criteria["timestamp"] = {"$gte": date_start, "$lt": date_end}
        elif start_date:
            date_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ)
            criteria["timestamp"] = {"$gte": date_start}
        elif end_date:
            date_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ) + timedelta(days=1)
            criteria["timestamp"] = {"$lt": date_end}
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.")
        return redirect(url_for("get_chats_by_date_and_users"))

    all_documents = list(messages_collection.find(criteria).sort("timestamp", -1).skip(skip_items).limit(items_per_page))
    total_chats = messages_collection.count_documents(criteria)

    chats = []
    for document in all_documents:
        chats_data = document.get("chats", {})
        chat_username = chats_data.get("username", "N/A")
        if chat_username == "N/A":
            continue

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
            chats.append({
                "username": chat_username,
                "question": question or "No question",
                "answer": message.get("content", "No answer"),
                "date": formatted_date,
            })

    total_pages = (total_chats + items_per_page - 1) // items_per_page

    return render_template(
        "chats_by_date_and_users.html",
        chats=chats,
        start_date=start_date,
        end_date=end_date,
        username=username,
        page=page,
        total_pages=total_pages,
    )

@app.route("/download-chats-by-date-and-users", methods=["GET"])
def download_chats_by_date_and_users():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    # Get parameters from request
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    username = request.args.get("username", "").strip()

    # Validate dates
    if not start_date or not end_date:
        flash("Please select both start date and end date", "error")
        return redirect(url_for('get_chats_by_date_and_users', 
                              start_date=start_date,
                              end_date=end_date,
                              username=username))

    try:
        # Convert dates to datetime objects with timezone
        date_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ)
        date_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ) + timedelta(days=1)
        
        # Validate date range
        if date_end <= date_start:
            flash("End date must be after start date", "error")
            return redirect(url_for('get_chats_by_date_and_users',
                                  start_date=start_date,
                                  end_date=end_date,
                                  username=username))

        # Create query criteria
        criteria = {
            "timestamp": {"$gte": date_start, "$lt": date_end}, 
            "chats.username": {"$exists": True, "$ne": ""}
        }
        
        if username:
            criteria["chats.username"] = {"$regex": f"^{username}$", "$options": "i"}

        # Fetch documents
        all_documents = list(messages_collection.find(criteria).sort("timestamp", -1))
        
        if not all_documents:
            flash("No data found for the selected date range", "warning")
            return redirect(url_for('get_chats_by_date_and_users',
                                  start_date=start_date,
                                  end_date=end_date,
                                  username=username))

        # Process documents
        chats = []
        for document in all_documents:
            chats_data = document.get("chats", {})
            chat_username = chats_data.get("username", "N/A")
            if chat_username == "N/A":
                continue

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
                chats.append({
                    "username": chat_username,
                    "date": formatted_date,
                    "question": question or "No question",
                    "answer": message.get("content", "No answer"),
                })

        # Create CSV file
        df = pd.DataFrame(chats)
        output = BytesIO()
        df.to_csv(output, index=False, encoding="utf-8")
        output.seek(0)

        # Generate filename with date range
        filename = f"chats_{start_date}_to_{end_date}.csv"

        return send_file(
            output,
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename
        )

    except ValueError as e:
        flash("Invalid date format. Please use YYYY-MM-DD format", "error")
        return redirect(url_for('get_chats_by_date_and_users',
                              start_date=start_date,
                              end_date=end_date,
                              username=username))
        
    except Exception as e:
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('get_chats_by_date_and_users',
                              start_date=start_date,
                              end_date=end_date,
                              username=username))
@app.route("/export-filtered-data", methods=["POST"])
def export_filtered_data():
    # Parse filter parameters from the request
    data = request.get_json()
    filter_option = data.get("filter", "")
    start_date = data.get("startDate", "")
    end_date = data.get("endDate", "")
    username = data.get("username", "").strip()
    total_chats = data.get("totalChats", 0)
    total_tickets = data.get("totalTickets", 0)

    # Determine the date range
    if filter_option == "custom" and start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ).astimezone(UTC)
        end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ).astimezone(UTC) + timedelta(days=1)
    else:
        start_date, end_date = get_date_range(filter_option)

    if not start_date or not end_date:
        return jsonify({"error": "Invalid date filter"}), 400

    start_date_utc = start_date.astimezone(UTC)
    end_date_utc = end_date.astimezone(UTC)

    # Create query criteria to only get documents with valid usernames
    criteria = {
        "timestamp": {"$gte": start_date_utc, "$lt": end_date_utc},
        "chats.username": {"$exists": True, "$ne": ""},  # Username must exist and not be empty
    }

    if username:
        criteria["chats.username"] = {"$regex": f"^{username}$", "$options": "i"}

    try:
        # Fetch data from MongoDB
        all_documents = list(messages_collection.find(criteria))

        # Format the data for CSV
        rows = []
        for document in all_documents:
            chats_data = document.get("chats", {})

            # Get username and skip if not present or empty
            chat_username = chats_data.get("username")
            if not chat_username or chat_username.strip() == "":
                continue

            questions = chats_data.get("questions", [])
            messages = chats_data.get("messages", [])

            # Handle different data formats
            if isinstance(questions, str):
                questions = [questions]

            if isinstance(messages, dict):
                messages = [messages]

            timestamp = document.get("timestamp")
            adjusted_time = adjust_timestamp(timestamp) if timestamp else None
            formatted_date = adjusted_time.strftime("%d-%b-%Y %I:%M %p") if adjusted_time else "Unknown Date"

            # Add only valid chat entries
            for question, message in zip(questions, messages):
                # Skip if question or message is empty/None
                if not question or not message:
                    continue

                answer_content = message.get("content")
                if not answer_content:
                    continue

                rows.append({
                    "username": chat_username,
                    "date": formatted_date,
                    "question": question,
                    "answer": answer_content,
                    "totalChats": total_chats,
                    "totalTickets": total_tickets,
                })

        # Check if we have any data
        if not rows:
            return jsonify({"error": "No chat data found with valid usernames"}), 404

        # Convert to CSV
        df = pd.DataFrame(rows)

        # Create CSV file
        output = BytesIO()
        df.to_csv(output, index=False, encoding="utf-8")
        output.seek(0)

        # Generate filename with date range
        filename = f"chat_data_{start_date_utc.strftime('%Y%m%d')}_{end_date_utc.strftime('%Y%m%d')}.csv"

        return send_file(
            output,
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        print(f"Error in export_filtered_data: {str(e)}")  # For debugging
        return jsonify({"error": f"An error occurred while exporting data: {str(e)}"}), 500

@app.route("/export-all-data", methods=["GET"])
def export_all_data():
    try:
        # Fetch all documents from MongoDB
        all_documents = list(messages_collection.find({}))

        # Format the data for CSV
        rows = []
        for document in all_documents:
            chats_data = document.get("chats", {})

            # Get username and skip if not present or empty
            chat_username = chats_data.get("username")
            if not chat_username or chat_username.strip() == "":
                continue

            questions = chats_data.get("questions", [])
            messages = chats_data.get("messages", [])

            # Handle different data formats
            if isinstance(questions, str):
                questions = [questions]

            if isinstance(messages, dict):
                messages = [messages]

            timestamp = document.get("timestamp")
            adjusted_time = adjust_timestamp(timestamp) if timestamp else None
            formatted_date = adjusted_time.strftime("%d-%b-%Y %I:%M %p") if adjusted_time else "Unknown Date"

            # Add only valid chat entries
            for question, message in zip(questions, messages):
                # Skip if question or message is empty/None
                if not question or not message:
                    continue

                answer_content = message.get("content")
                if not answer_content:
                    continue

                rows.append({
                    "username": chat_username,
                    "date": formatted_date,
                    "question": question,
                    "answer": answer_content,
                })

        # Check if we have any data
        if not rows:
            return jsonify({"error": "No chat data found with valid usernames"}), 404

        # Convert to CSV
        df = pd.DataFrame(rows)

        # Create CSV file
        output = BytesIO()
        df.to_csv(output, index=False, encoding="utf-8")
        output.seek(0)

        # Generate filename with current date
        filename = f"all_chat_data_{datetime.now().strftime('%Y%m%d')}.csv"

        return send_file(
            output,
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        print(f"Error in export_all_data: {str(e)}")  # For debugging
        return jsonify({"error": f"An error occurred while exporting data: {str(e)}"}), 500
@app.route("/get-all-chats", methods=["GET"])
def get_all_chats():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized access"}), 403

    try:
        # Fetch all documents from the collection
        all_documents = list(messages_collection.find({"chats.username": {"$exists": True, "$ne": ""}}))

        # Process data for frontend
        chats = []
        for document in all_documents:
            chats_data = document.get("chats", {})
            chat_username = chats_data.get("username", "N/A")
            questions = chats_data.get("questions", [])
            messages = chats_data.get("messages", [])

            # Normalize questions/messages for consistency
            if isinstance(questions, str):
                questions = [questions]
            if isinstance(messages, dict):
                messages = [messages]

            timestamp = document.get("timestamp")
            adjusted_time = adjust_timestamp(timestamp) if timestamp else None
            formatted_date = adjusted_time.strftime("%d-%b-%Y %I:%M %p") if adjusted_time else "Unknown Date"

            for question, message in zip(questions, messages):
                chats.append({
                    "username": chat_username,
                    "date": formatted_date,
                    "question": question or "No question",
                    "answer": message.get("content", "No answer"),
                })

        return jsonify({"chats": chats})
    except Exception as e:
        print(f"Error fetching all chats: {str(e)}")
        return jsonify({"error": "Failed to fetch all chats"})



@app.route("/api/line_chart_data", methods=["POST"])
def line_chart_data():
    data = request.get_json()
    filter_option = data.get("filter", "")
    start_date = data.get("startDate", "")
    end_date = data.get("endDate", "")

    if filter_option == "custom" and start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ).astimezone(UTC)
        end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=MELBOURNE_TZ).astimezone(UTC) + timedelta(days=1)

    else:
        start_date, end_date = get_date_range(filter_option)

    if not start_date or not end_date:
        return jsonify({"error": "Invalid date filter"}), 400

    start_date_utc = start_date.astimezone(UTC)
    end_date_utc = end_date.astimezone(UTC)

    try:
        pipeline = [
            {"$match": {
                "timestamp": {"$gte": start_date_utc, "$lt": end_date_utc},
                "chats.username": {"$exists": True, "$ne": ""}
            }},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]

        line_chart_data = list(messages_collection.aggregate(pipeline))
        return jsonify(line_chart_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=True)
