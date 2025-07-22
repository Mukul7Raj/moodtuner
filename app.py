import cv2
import numpy as np
from tensorflow.keras.models import load_model
from flask import Flask, render_template, Response, jsonify, request
import googleapiclient.discovery
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import logging
import json
import os
from isodate import parse_duration
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Global variables
emotion_labels = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']
current_emotion = "None"
current_videos = []
current_spotify_tracks = []
liked_videos = []
camera_running = False
last_capture_time = None
cap = None

# Load emotion detection model
try:
    model = load_model('emotion_model.h5')
    logger.info("Emotion model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load emotion model: {e}")
    model = None

# Load Haar Cascade for face detection
try:
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    if face_cascade.empty():
        raise Exception("Failed to load Haar Cascade file")
    logger.info("Haar Cascade loaded successfully")
except Exception as e:
    logger.error(f"Error loading Haar Cascade: {e}")
    face_cascade = None

# Initialize YouTube API
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    logger.error("YouTube API key not found in environment variables")
    youtube = None
else:
    try:
        youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        logger.info("YouTube API initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize YouTube API: {e}")
        youtube = None

# Initialize Spotify API
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    logger.error("Spotify API credentials not found in environment variables")
    spotify = None
else:
    try:
        sp_credentials = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
        spotify = spotipy.Spotify(client_credentials_manager=sp_credentials)
        logger.info("Spotify API initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Spotify API: {e}")
        spotify = None

# Load liked videos from JSON file
LIKED_VIDEOS_FILE = 'liked_videos.json'
if os.path.exists(LIKED_VIDEOS_FILE):
    try:
        with open(LIKED_VIDEOS_FILE, 'r') as f:
            liked_videos = json.load(f)
        logger.info("Liked videos loaded successfully")
    except Exception as e:
        logger.error(f"Error loading liked videos: {e}")

# Save liked videos to JSON file
def save_liked_videos():
    try:
        with open(LIKED_VIDEOS_FILE, 'w') as f:
            json.dump(liked_videos, f)
        logger.info("Liked videos saved successfully")
    except Exception as e:
        logger.error(f"Error saving liked videos: {e}")

# Generate webcam frames for video feed
def gen_frames():
    global camera_running, last_capture_time
    last_capture_time = time.time()
    while camera_running:
        if cap is None or not cap.isOpened():
            logger.error("Camera is not opened")
            camera_running = False
            break
        
        ret, frame = cap.read()
        if not ret:
            logger.error("Failed to capture frame from webcam")
            camera_running = False
            break
        
        if time.time() - last_capture_time > 30:
            stop_camera()
            break
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# Fetch YouTube videos based on query
def fetch_youtube_videos(query):
    if not youtube:
        logger.error("YouTube API not initialized")
        return []
    try:
        search_response = youtube.search().list(q=query, part="id,snippet", maxResults=20).execute()
        video_ids = [item['id']['videoId'] for item in search_response['items'] if item['id'].get('kind') == 'youtube#video']
        
        videos = []
        region = os.getenv("USER_REGION", "US")
        while len(videos) < 10 and video_ids:
            video_response = youtube.videos().list(id=','.join(video_ids), part="contentDetails,snippet,status").execute()
            for item in video_response['items']:
                if len(videos) >= 10:
                    break
                video_id = item['id']
                title = item['snippet']['title']
                status = item['status']
                if status['uploadStatus'] != 'processed' or status['privacyStatus'] != 'public' or not status.get('embeddable', False):
                    continue
                if 'regionRestriction' in item['contentDetails']:
                    region_restriction = item['contentDetails']['regionRestriction']
                    if 'blocked' in region_restriction and region in region_restriction['blocked']:
                        continue
                    if 'allowed' in region_restriction and region not in region_restriction['allowed']:
                        continue
                
                duration = parse_duration(item['contentDetails']['duration']).total_seconds()
                duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
                embed_link = f"https://www.youtube.com/embed/{video_id}?autoplay=1"
                thumbnail = item['snippet']['thumbnails']['default']['url']
                videos.append({
                    'title': title,
                    'embed_link': embed_link,
                    'duration': duration_str,
                    'thumbnail': thumbnail,
                    'source': 'YouTube'
                })
            
            if len(videos) < 10 and 'nextPageToken' in search_response:
                search_response = youtube.search().list(q=query, part="id,snippet", maxResults=20, pageToken=search_response['nextPageToken']).execute()
                video_ids = [item['id']['videoId'] for item in search_response['items'] if item['id'].get('kind') == 'youtube#video']
        
        return videos[:10]
    except Exception as e:
        logger.error(f"Error fetching YouTube videos: {e}")
        return []

# Fetch Spotify tracks based on query
def fetch_spotify_tracks(query):
    if not spotify:
        logger.error("Spotify API not initialized")
        return []
    try:
        emotion_to_genre = {
            'angry': 'rock', 'disgust': 'electronic', 'fear': 'ambient',
            'happy': 'pop', 'sad': 'blues', 'surprise': 'dance', 'neutral': 'lo-fi'
        }
        
        search_query = f"genre:{emotion_to_genre[query.lower()]}" if query.lower() in emotion_to_genre else query
        logger.info(f"Searching Spotify for: {search_query}")
        
        results = spotify.search(q=search_query, type='track', limit=10)
        tracks = []
        if not results['tracks']['items']:
            logger.warning(f"No Spotify tracks found for query: {search_query}")
            return tracks
        
        for item in results['tracks']['items']:
            track_id = item['id']
            title = item['name']
            artist = item['artists'][0]['name']
            duration = item['duration_ms'] // 1000
            duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
            embed_link = f"https://open.spotify.com/embed/track/{track_id}?autoplay=1"
            thumbnail = item['album']['images'][2]['url'] if len(item['album']['images']) > 2 else ''
            tracks.append({
                'title': f"{title} by {artist}",
                'embed_link': embed_link,
                'duration': duration_str,
                'thumbnail': thumbnail,
                'source': 'Spotify'
            })
        logger.info(f"Found {len(tracks)} Spotify tracks")
        return tracks
    except Exception as e:
        logger.error(f"Error fetching Spotify tracks: {e}")
        return []

# Routes
@app.route('/')
def index():
    return render_template('index.html', liked_videos=liked_videos)

@app.route('/start_camera', methods=['POST'])
def start_camera():
    global cap, camera_running
    if camera_running:
        stop_camera()
    
    cap = cv2.VideoCapture(0)
    for _ in range(10):
        if cap.isOpened():
            break
        time.sleep(0.1)
    if not cap.isOpened():
        logger.error("Failed to open camera")
        return jsonify({'status': 'error', 'message': 'Camera could not be opened. Check webcam or other apps.'})
    
    for _ in range(5):
        cap.read()
    
    camera_running = True
    logger.info("Camera started")
    return jsonify({'status': 'success'})

@app.route('/stop_camera', methods=['POST'])
def stop_camera():
    global cap, camera_running
    if camera_running:
        if cap is not None:
            cap.release()
            cap = None
        camera_running = False
        logger.info("Camera stopped")
    return jsonify({'status': 'success'})

@app.route('/capture_image', methods=['POST'])
def capture_image():
    global current_emotion, current_videos, current_spotify_tracks, camera_running
    
    if model is None:
        logger.error("Emotion model not loaded")
        stop_camera()
        return jsonify({'status': 'error', 'message': 'Emotion model not loaded. Restart the app.'})
    
    if not camera_running or cap is None or not cap.isOpened():
        logger.error("Camera not running during capture")
        return jsonify({'status': 'error', 'message': 'Camera not running. Click "Start Camera" again.'})
    
    for _ in range(5):
        ret, frame = cap.read()
        if not ret:
            logger.error("Failed to clear camera buffer")
            stop_camera()
            return jsonify({'status': 'error', 'message': 'Image capture failed. Try "Start Camera" again.'})
    
    ret, frame = cap.read()
    if not ret:
        logger.error("Failed to capture image")
        stop_camera()
        return jsonify({'status': 'error', 'message': 'Image capture failed. Try "Start Camera" again.'})
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if face_cascade is None:
        logger.error("Face cascade not loaded")
        stop_camera()
        return jsonify({'status': 'error', 'message': 'Face detection model not loaded. Restart the app.'})
    
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
    
    if len(faces) == 0:
        logger.warning("No faces detected in captured image")
        stop_camera()
        return jsonify({'status': 'error', 'message': 'No face detected. Adjust lighting or position and try again.'})
    
    for (x, y, w, h) in faces:
        roi = gray[y:y+h, x:x+w]
        roi = cv2.resize(roi, (48, 48)) / 255.0
        roi = np.expand_dims(roi, axis=(0, -1))
        
        try:
            emotion_probs = model.predict(roi)
            emotion_idx = np.argmax(emotion_probs)
            current_emotion = emotion_labels[emotion_idx]
        except Exception as e:
            logger.error(f"Error predicting emotion: {e}")
            stop_camera()
            return jsonify({'status': 'error', 'message': 'Emotion prediction failed. Try again.'})
        
        search_query = f"{current_emotion} music playlist"
        current_videos = fetch_youtube_videos(search_query)
        current_spotify_tracks = fetch_spotify_tracks(current_emotion)
        break
    
    stop_camera()
    return jsonify({
        'status': 'success',
        'emotion': current_emotion,
        'youtube_videos': current_videos,
        'spotify_tracks': current_spotify_tracks
    })

@app.route('/search', methods=['POST'])
def search():
    query = request.json.get('query', '')
    if not query:
        return jsonify({'status': 'error', 'message': 'Search query cannot be empty'})
    
    youtube_results = fetch_youtube_videos(query)
    spotify_results = fetch_spotify_tracks(query)
    
    return jsonify({
        'status': 'success',
        'youtube_videos': youtube_results,
        'spotify_tracks': spotify_results
    })

@app.route('/video_feed')
def video_feed():
    if not camera_running:
        return Response("Camera is not running", mimetype='text/plain')
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_emotion')
def get_emotion():
    return jsonify({
        'emotion': current_emotion,
        'youtube_videos': current_videos,
        'spotify_tracks': current_spotify_tracks
    })

@app.route('/like_video', methods=['POST'])
def like_video():
    try:
        video = request.get_json()
        if not video or 'title' not in video or 'embed_link' not in video:
            return jsonify({'status': 'error', 'message': 'Invalid video data'})
        if video not in liked_videos:
            liked_videos.append(video)
            save_liked_videos()
            logger.info(f"Liked video: {video['title']}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error liking video: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to like video'})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, ssl_context=('cert.pem', 'key.pem'))
