from flask import Blueprint, request, jsonify
from services.Spotipy import get_playlist_for_emotion

playlist_bp = Blueprint('playlist', __name__)

@playlist_bp.route('/get_playlist', methods=['GET'])
def get_playlist():
    emotion = request.args.get('emotion')
    if not emotion:
        return jsonify({'error': 'No emotion provided'}), 400

    playlist = get_playlist_for_emotion(emotion)
    return jsonify({"playlist": playlist})
