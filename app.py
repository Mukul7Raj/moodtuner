from flask import Flask, jsonify
from config import Config
from models import db, User, EmotionLog
from utils.spotify import get_spotify_token, get_playlist_for_emotion

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

@app.route('/')
def home():
    return jsonify({"message": "API is live!"})

@app.route('/create_user/<email>')
def create_user(email):
    user = User(email=email, consent_given=True)
    db.session.add(user)
    db.session.commit()
    return jsonify({"user_id": user.id})

@app.route('/log_emotion/<int:user_id>/<emotion>')
def log_emotion(user_id, emotion):
    db.session.add(EmotionLog(user_id=user_id, emotion=emotion))
    db.session.commit()
    playlist_id = get_playlist_for_emotion(emotion)
    return jsonify({"message": f"Logged {emotion}", "spotify_playlist": playlist_id})

with app.app_context():
    db.create_all()
    print("Database initialized!")

if __name__ == '__main__':
    app.run(debug=True)
