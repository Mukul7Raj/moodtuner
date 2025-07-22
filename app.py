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


#  Emotion-Based Music Recommender . 
#     Idea ye hai ki webcam se face dekhu, emotion pata karu aur uske hisaab se YouTube aur Spotify se music suggest karu. 
#     Thoda basic cheez Grok se uthaunga, jaise Flask ka setup, aur API kaise connect karte hai. 
#     Mai decide karra hu ki yaha pe OpenCV use karunga face detect karne ke liye, aur pretrained model (emotion_model.h5) load karunga. 
#     YouTube aur Spotify API yaha se milegi – Google Cloud aur Spotify Developer Dashboard se key lunga.


load_dotenv()


    # Logging setup karra hu taki pata chale kya ho raha hai jab code chalega. Ye thodi debugging ke liye helpful hai.

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# /* 
#     Yaha pe emotion model load karne ka plan hai. Agar load nahi hua toh error handle karunga, taki app crash na ho.
# */
try:
    model = load_model('emotion_model.h5')
    logger.info("Emotion model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load emotion model: {e}")
    model = None


    # Webcam ke liye variables banara hu. Camera on/off ka state rakhna padega aur last capture ka time bhi track karunga.

cap = None
camera_running = False
last_capture_time = None


    # Face detection ke liye OpenCV ka Haar Cascade use karunga. Ye already available hai OpenCV me, bas load karna hai.
    # Agar load nahi hua toh error message dikhayenge.

try:
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    if face_cascade.empty():
        raise Exception("Failed to load Haar Cascade file")
    logger.info("Haar Cascade loaded successfully")
except Exception as e:
    logger.error(f"Error loading Haar Cascade: {e}")
    face_cascade = None

 # YouTube API setup karna hai. API key .env file se lunga, environment variables me store karunga. 
    # Agar key nahi mili toh error log karunga.

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

    # Spotify API bhi setup karunga. Client ID aur Secret .env se lunga. 
    # Agar credentials nahi mile toh skip kar dunga, error log karunga.


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

    # Ye emotion labels hai jo model detect karega. Inke basis pe music suggest karunga.


emotion_labels = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']

# /* 
#     Global variables banara hu taki current emotion, videos, aur tracks store kar saku. 
#     Liked videos ka list bhi rakhunga jo JSON file me save hoga.

current_emotion = "None"
current_videos = []
current_spotify_tracks = []
liked_videos = []


    # Liked videos ko JSON file se load karunga. Agar file nahi hai toh empty list rahega.

LIKED_VIDEOS_FILE = 'liked_videos.json'
if os.path.exists(LIKED_VIDEOS_FILE):
    with open(LIKED_VIDEOS_FILE, 'r') as f:
        liked_videos = json.load(f)

 
    # Liked videos save karne ka function banaya. Jab bhi user like karega, yaha save hoga.

def save_liked_videos():
    with open(LIKED_VIDEOS_FILE, 'w') as f:
        json.dump(liked_videos, f)

#  Webcam se frames generate karne ka function hai. Ye live video feed ke liye hai. 
#     30 second baad auto close kar dunga agar capture nahi hua.

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


    # YouTube se videos fetch karne ka plan hai. Query ke basis pe search karunga aur 10 videos return karunga.
    # Region restriction bhi check karunga taki India me playable ho.

def fetch_youtube_videos(query):
    if not youtube:
        return []
    try:
        search_response = youtube.search().list(q=query, part="id,snippet", maxResults=20).execute()
        video_ids = [item['id']['videoId'] for item in search_response['items'] if item['id'].get('kind') == 'youtube#video']
        
        videos = []
        if video_ids:
            video_response = youtube.videos().list(id=','.join(video_ids), part="contentDetails,snippet,status").execute()
            for item in video_response['items']:
                video_id = item['id']
                title = item['snippet']['title']
                status = item['status']
                if status['uploadStatus'] != 'processed' or status['privacyStatus'] != 'public' or not status.get('embeddable', False):
                    continue
                region = os.getenv("USER_REGION", "US")
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
        
        while len(videos) < 10 and video_ids and 'nextPageToken' in search_response:
            search_response = youtube.search().list(q=query, part="id,snippet", maxResults=20, pageToken=search_response.get('nextPageToken')).execute()
            video_ids = [item['id']['videoId'] for item in search_response['items'] if item['id'].get('kind') == 'youtube#video']
            if video_ids:
                video_response = youtube.videos().list(id=','.join(video_ids), part="contentDetails,snippet,status").execute()
                for item in video_response['items']:
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
        
        return videos[:10]
    except Exception as e:
        logger.error(f"Error fetching YouTube videos: {e}")
        return []

# /* 
#     Spotify se tracks fetch karne ka function hai. Emotion ke basis pe genre map karunga, jaise happy ke liye pop.
#     Agar query song ya artist ka hai toh direct search karunga.
# */
def fetch_spotify_tracks(query):
    if not spotify:
        logger.error("Spotify API not initialized")
        return []
    try:
        emotion_to_genre = {
            'angry': 'rock',
            'disgust': 'electronic',
            'fear': 'ambient',
            'happy': 'pop',
            'sad': 'blues',
            'surprise': 'dance',
            'neutral': 'lo-fi'
        }
        
        if query.lower() in emotion_to_genre:
            search_query = f"genre:{emotion_to_genre[query.lower()]}"
            logger.info(f"Searching Spotify for genre: {search_query}")
        else:
            search_query = query
            logger.info(f"Searching Spotify for song/artist: {search_query}")
        
        results = spotify.search(q=search_query, type='track', limit=10)
        logger.info(f"Spotify API response: {results}")
        
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
        logger.info(f"Found {len(tracks)} Spotify tracks for query: {search_query}")
        return tracks
    except Exception as e:
        logger.error(f"Error fetching Spotify tracks: {e}")
        return []


    # Main page ka route hai. Yaha pe HTML render karunga aur liked videos pass kar dunga.

@app.route('/')
def index():
    return render_template('index.html', liked_videos=liked_videos)

 
    # Camera start karne ka route hai. Agar already on hai toh pehle off karunga, phir naya start karunga.

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
        return jsonify({
            'status': 'error',
            'message': 'Camera open nahi hua. Webcam check karo ya koi aur app use kar raha hai kya.'
        })
    
    for _ in range(5):
        cap.read()
    
    camera_running = True
    logger.info("Camera started")
    return jsonify({'status': 'success'})

 
    # Camera stop karne ka function hai. Global variables update karunga taki camera free ho jaye.

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


    # Yaha pe image capture karunga aur emotion detect karunga. Face detect karne ke baad model se emotion predict karunga.
    # Phir YouTube aur Spotify se music fetch karunga.

@app.route('/capture_image', methods=['POST'])
def capture_image():
    global current_emotion, current_videos, current_spotify_tracks, camera_running
    
    if model is None:
        logger.error("Emotion model not loaded")
        stop_camera()
        return jsonify({
            'status': 'error',
            'message': 'Emotion model load nahi hua. App restart karo.'
        })
    
    if not camera_running or cap is None or not cap.isOpened():
        logger.error("Camera not running during capture")
        return jsonify({
            'status': 'error',
            'message': 'Camera nahi chal raha. "Start Camera" click karo phir se.'
        })
    
    for _ in range(5):
        ret, frame = cap.read()
        if not ret:
            logger.error("Failed to clear camera buffer")
            stop_camera()
            return jsonify({
                'status': 'error',
                'message': 'Image capture nahi hua. "Start Camera" try karo.'
            })
    
    ret, frame = cap.read()
    if not ret:
        logger.error("Failed to capture image")
        stop_camera()
        return jsonify({
            'status': 'error',
            'message': 'Image capture fail hua. "Start Camera" phir se try karo.'
        })
    
    logger.info("Captured a fresh frame for processing")
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if face_cascade is None:
        logger.error("Face cascade not loaded")
        stop_camera()
        return jsonify({
            'status': 'error',
            'message': 'Face detection model nahi load hua. App restart karo.'
        })
    
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
    
    if len(faces) == 0:
        logger.warning("No faces detected in captured image")
        stop_camera()
        return jsonify({
            'status': 'error',
            'message': 'Face detect nahi hua. Light thik karo ya position change karo aur try karo.'
        })
    
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
            return jsonify({
                'status': 'error',
                'message': 'Emotion predict nahi hua. Phir se try karo.'
            })
        
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


    # Search ka route banaya. User jo type karega ya voice se bolega, uske basis pe YouTube aur Spotify se results lunga.

@app.route('/search', methods=['POST'])
def search():
    query = request.json.get('query', '')
    if not query:
        return jsonify({
            'status': 'error',
            'message': 'Search query khali nahi hona chahiye'
        })
    
    youtube_results = fetch_youtube_videos(query)
    spotify_results = fetch_spotify_tracks(query)
    
    return jsonify({
        'status': 'success',
        'youtube_videos': youtube_results,
        'spotify_tracks': spotify_results
    })


    # Video feed ke liye route hai. Live webcam stream yaha se frontend pe jayega.

@app.route('/video_feed')
def video_feed():
    if not camera_running:
        return Response("Camera is not running", mimetype='text/plain')
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

 
    # Current emotion aur music suggestions frontend ko bhejna hai jab bhi chahiye.

@app.route('/get_emotion')
def get_emotion():
    return jsonify({
        'emotion': current_emotion,
        'youtube_videos': current_videos,
        'spotify_tracks': current_spotify_tracks
    })


    # Like video ka feature add karra hu. User jo video like karega, woh JSON file me save hoga.

@app.route('/like_video', methods=['POST'])
def like_video():
    try:
        video = request.get_json()
        if not video or 'title' not in video or 'embed_link' not in video:
            return jsonify({'status': 'error', 'message': 'Video data thik nahi hai'})
        if video not in liked_videos:
            liked_videos.append(video)
            save_liked_videos()
            logger.info(f"Liked video: {video['title']}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error liking video: {e}")
        return jsonify({'status': 'error', 'message': 'Video like nahi hua'})

if __name__ == '__main__':
  
    #     App ko HTTPS pe chalayenge SSL certificates ke saath. Debug off rakha hai production ke liye.

    app.run(debug=False, host='0.0.0.0', port=5000, ssl_context=('cert.pem', 'key.pem'))

 
    # Okay toh abhi ye pura code likh diya hai. Thodi UI ke liye to-do list wagarah left side pe Grok se dalwa diya tha pehle.
    # Ab ye pura code Grok ko dunga, usse bolunga ki formatting thik kare, proper spacing dale, aur agar kuch better suggestion ho toh bataye.
    # Final version banane ke baad test karunga aur agar kuch galti hui toh fix karunga!
