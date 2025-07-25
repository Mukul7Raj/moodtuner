from flask import Blueprint, request, jsonify
import cv2
import numpy as np
from tensorflow.keras.models import load_model

emotion_bp = Blueprint('emotion', __name__)
model = load_model("model.h5")
labels = ['angry', 'disgusted', 'fearful', 'happy', 'neutral', 'sad', 'surprised']

@emotion_bp.route('/detect_emotion', methods=['POST'])
def detect_emotion():
    file = request.files['frame']
    img = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)

    # Preprocess
    face = cv2.resize(img, (48, 48))
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    norm = gray / 255.0
    reshaped = np.reshape(norm, (1, 48, 48, 1))

    prediction = model.predict(reshaped)
    emotion = labels[np.argmax(prediction)]

    return jsonify({"emotion": emotion})
