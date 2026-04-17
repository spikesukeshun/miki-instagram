from flask import Flask, request, jsonify
import json, sys

app = Flask(__name__)
captured_users = []

@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    body = request.get_data(as_text=True)
    with open("/tmp/line_bodies.log", "a") as f:
        f.write(f"\n=== {request.method} ===\n{body}\n")

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        for event in data.get("events", []):
            user_id = event.get("source", {}).get("userId")
            if user_id and user_id not in captured_users:
                captured_users.append(user_id)
    return jsonify({"status": "ok"})

@app.route("/users")
def get_users():
    return jsonify({"users": captured_users})

if __name__ == "__main__":
    open("/tmp/line_bodies.log", "w").close()
    app.run(port=8080, debug=False)
