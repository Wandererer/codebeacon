from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    email = db.Column(db.String(120), unique=True)


@app.route("/users", methods=["GET"])
def get_users():
    return jsonify([])


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    return jsonify({"id": user_id})


@app.route("/users", methods=["POST"])
def create_user():
    data = request.json
    return jsonify(data), 201


@app.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    data = request.json
    return jsonify(data)


@app.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    return jsonify({"deleted": user_id})
