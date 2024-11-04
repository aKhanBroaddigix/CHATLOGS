from flask import Flask, request, render_template_string, url_for
from pymongo import MongoClient

# Initialize Flask app
app = Flask(__name__)

# MongoDB connection details
MONGO_URI = "mongodb+srv://mawaisqureshi645:0SFbhLnLHjQ8eXTP@cluster0.mt5s1ef.mongodb.net/?retryWrites=true&w=majority&tls=true"
DATABASE_NAME = "chat-history"
COLLECTION_NAME = "chats"

# Initialize MongoDB client
client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
messages_collection = db[COLLECTION_NAME]

# HTML template for the home page with the username input form
home_page_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat Retrieval</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        /* Fernwood Fitness theme with background image */
        body { 
            background: url("{{ url_for('static', filename='fernwood_bg.jpg') }}") no-repeat center center fixed; 
            background-size: cover; 
            color: #333; 
            font-family: Arial, sans-serif; 
        }
        h1 { color: #ffff; }
        .card { border-color: #c71585; background-color: rgba(255, 255, 255, 0.8); }
        .btn-primary { background-color: #c71585; border: none; }
        .btn-primary:hover { background-color: #a5146d; }
        .form-label { font-weight: bold; }
    </style>
</head>
<body>
    <div class="container my-5">
        <h1 class="text-center mb-4">Retrieve User Chats</h1>
        <div class="row justify-content-center">
            <div class="col-md-6">
                <div class="card p-4 shadow-sm">
                    <form action="/get-chats" method="post">
                        <div class="mb-3">
                            <label for="username" class="form-label">Enter Username</label>
                            <input type="text" id="username" name="username" class="form-control" required>
                        </div>
                        <button type="submit" class="btn btn-primary w-100">Retrieve Chats</button>
                    </form>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

# HTML template for displaying all chats without pagination
chats_page_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chats for {{ username }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        /* Fernwood Fitness theme with background image */
        body { 
            background: url("{{ url_for('static', filename='fernwood_bg.jpg') }}") no-repeat center center fixed; 
            background-size: cover; 
            color: #333; 
            font-family: Arial, sans-serif; 
        }
        h1 { color: #ffff; }
        .card { border-color: #c71585; background-color: rgba(255, 255, 255, 0.8); }
        .btn-primary { background-color: #c71585; border: none; }
        .btn-primary:hover { background-color: #a5146d; }
        .form-label { font-weight: bold; }
    </style>
</head>
<body>
    <div class="container my-5">
        <h1 class="text-center mb-4" color:white>All Chats for {{ username }}</h1>
        
        {% if user_found %}
            {% for chat in chats %}
                <div class="card mb-4 shadow-sm">
                    <div class="card-body">
                        <h5 class="card-title">Chat ID: {{ chat.chat_id }}</h5>
                        <p class="card-text"><strong>Question:</strong> {{ chat.question }}</p>
                        <p class="card-text"><strong>Answer:</strong> {{ chat.answer }}</p>
                    </div>
                </div>
            {% endfor %}
        {% else %}
            <div class="alert alert-warning text-center">
                No chats found for username: <strong>{{ username }}</strong>
            </div>
        {% endif %}
        
        <div class="text-center mt-4">
            <a href="/" class="btn btn-secondary">Search Again</a>
        </div>
    </div>
</body>
</html>
"""

# Route for the home page
@app.route("/", methods=["GET"])
def home():
    return render_template_string(home_page_html)

# Route to retrieve all data and display results without pagination
@app.route("/get-chats", methods=["POST", "GET"])
def get_chats():
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

            # Handle `questions` and `messages` being either arrays or single entries
            questions = chats_data.get("questions", [])
            if isinstance(questions, str):  # If it's a single string, wrap it in a list
                questions = [questions]

            messages = chats_data.get("messages", [])
            if isinstance(messages, dict):  # If it's a single dict, wrap it in a list
                messages = [messages]

            # Process each question and its corresponding answer
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

    # Render the page with all chat data for the username
    return render_template_string(chats_page_html, username=username, user_found=user_found, chats=chats)

# Run the app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
