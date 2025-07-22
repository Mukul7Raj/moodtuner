![image](https://github.com/user-attachments/assets/a94dea24-811b-42cf-a244-b839ead335b1)
# Emotion-Based Music Recommender

This is a Flask-based web application that detects a user’s emotion using facial recognition through a webcam and recommends music from YouTube and Spotify based on the detected emotion. It includes additional features such as a focus timer, to-do list, voice search, and the ability to save liked songs.

## Project Overview
The Emotion-Based Music Recommender is a web application designed to analyze a user’s emotional state using a webcam and suggest music that matches their mood. It employs a pre-trained deep learning model to detect emotions such as happiness, sadness, or anger from facial expressions. The application integrates with YouTube and Spotify APIs to fetch relevant music recommendations. Additional utilities like a focus timer, to-do list, and voice search enhance its functionality.

## Key Features
- **Emotion Detection**: Utilizes a webcam to capture facial expressions and a pre-trained model (`emotion_model.h5`) to classify emotions.
- **Music Recommendations**: Retrieves playlists from YouTube and Spotify based on the detected emotion or user queries.
- **Webcam Integration**: Provides real-time video feed for emotion analysis.
- **Voice Search**: Enables song searches through voice commands using the Web Speech API.
- **Focus Timer**: Tracks time for productivity or study sessions.
- **To-Do List**: Supports task management with add, edit, and delete functionalities.
- **Liked Songs**: Allows users to save favorite songs in a persistent list.
- **Theme Switching**: Offers dark and light themes for user preference.
- **Emotion History**: Displays a graphical representation of detected emotions over time using Chart.js.

## Environment Configuration
The `.env` file must include:
- `YOUTUBE_API_KEY`: API key for YouTube integration.
- `SPOTIFY_CLIENT_ID`: Client ID for Spotify API.
- `SPOTIFY_CLIENT_SECRET`: Client Secret for Spotify API.
- `USER_REGION`: Optional region code (e.g., `IN` for India).

## Usage Instructions
1. **Launch the Application**:
   Run the Flask server with:
   ```bash
   python app.py
   ```
   The application will be accessible at `https://localhost:5000`. Accept the self-signed certificate warning in your browser.

2. **Access the Application**:
   Open a browser and navigate to `https://localhost:5000`.


## Directory Structure
```
emotion-based-music-recommender/
├── static/                     # Static assets
│   ├── face_logo.jpg           # Webcam placeholder image
│   ├── face_logo.png           # Alternative placeholder
│   ├── josh_emo_musics_logo.png # Application logo
│   └── style.css               # Styling rules
├── templates/                  # HTML templates
│   └── index.html              # Primary webpage
├── .env                        # Environment variables
├── app.py                      # Core Flask application
├── cert.pem                    # SSL certificate
├── emotion_model.h5            # Emotion detection model
├── haarcascade_frontalface_default.xml # Face detection classifier
├── key.pem                     # SSL private key
├── liked_videos.json           # Liked songs storage
└── requirements.txt            # Dependency list
```

