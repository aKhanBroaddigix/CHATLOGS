from flask import Flask, request, render_template, redirect, url_for, send_file, jsonify, flash, session
from pymongo import MongoClient
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
import csv

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

# Route for login page
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # Check against hardcoded credentials
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("home"))
        else:
            flash("Invalid username or password. Please try again.")
            return redirect(url_for("login"))

    return render_template("login.html")

# Home route that requires login
@app.route("/", methods=["GET"])
def home():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("index.html")

# Route to retrieve all data and display results without pagination
@app.route("/get-chats", methods=["POST", "GET"])
def get_chats():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    username = request.form.get("username").strip()
    print(f"Searching for user with username: '{username}'")  # Debugging output

    # Retrieve all data for the specific user
    all_documents = list(messages_collection.find({"chats.username": username}))
    print(f"Total documents retrieved for user '{username}': {len(all_documents)}")  # Debugging output

    # Filter data by username and format the chats
    chats = []
    for document in all_documents:
        try:
            chats_data = document.get("chats", {})
            chat_id = chats_data.get("id", "N/A")

            questions = chats_data.get("questions", [])
            if isinstance(questions, str):
                questions = [questions]

            messages = chats_data.get("messages", [])
            if isinstance(messages, dict):
                messages = [messages]

            for question, message in zip(questions, messages):
                sanitized_question = question if isinstance(question, str) else "No question available"
                sanitized_answer = (
                    message.get("content", "No answer available") if isinstance(message, dict) else "No answer available"
                )

                chat_data = {
                    "chat_id": chat_id,
                    "question": sanitized_question,
                    "answer": sanitized_answer
                }
                chats.append(chat_data)

        except Exception as e:
            print(f"Error processing document with ID {document.get('_id')}: {e}")

    user_found = len(chats) > 0

    return render_template("chats.html", username=username, user_found=user_found, chats=chats)

# Route to download chat data as CSV
@app.route("/download-chats/<username>", methods=["GET"])
def download_chats(username):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    # Retrieve all chat data for the specific user
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

        for question, message in zip(questions, messages):
            sanitized_question = str(question).replace('\n', ' ').replace('\r', '').strip() if isinstance(question, str) else "No question available"
            sanitized_answer = str(message.get("content", "No answer available")).replace('\n', ' ').replace('\r', '').strip() if isinstance(message, dict) else "No answer available"

            chat_data = {
                "username": username,
                "question": sanitized_question,
                "answer": sanitized_answer
            }
            chats.append(chat_data)

    # Convert chat data to CSV in binary format with proper quoting
    df = pd.DataFrame(chats)
    output = BytesIO()
    df.to_csv(output, index=False, encoding='utf-8', quoting=csv.QUOTE_ALL)  # Use quoting for all fields
    output.seek(0)

    return send_file(output, mimetype="text/csv", as_attachment=True, download_name=f"{username}_chats.csv")

# Route for weekly chat volume data
@app.route("/api/weekly_chat_volume", methods=["GET"])
def weekly_chat_volume():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    today = datetime.now()
    start_of_week = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())

    pipeline = [
        {"$match": {"timestamp": {"$gte": start_of_week}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]

    weekly_data = list(messages_collection.aggregate(pipeline))
    return jsonify(weekly_data)

# Route for top chat contributors data
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

# Run the app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
