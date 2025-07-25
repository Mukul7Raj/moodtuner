const video = document.getElementById('webcam');
const emotionBox = document.getElementById('emotion-result');
const playlistBox = document.getElementById('playlist');

// Get webcam stream
navigator.mediaDevices.getUserMedia({ video: true }).then(stream => {
  video.srcObject = stream;
});

// Send frame to backend every 5 seconds
setInterval(() => {
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);

  canvas.toBlob(blob => {
    const formData = new FormData();
    formData.append('frame', blob, 'frame.jpg');

    fetch('/detect_emotion', {
      method: 'POST',
      body: formData
    })
    .then(res => res.json())
    .then(data => {
      emotionBox.innerText = `Detected Emotion: ${data.emotion}`;
      fetch(`/get_playlist?emotion=${data.emotion}`)
        .then(res => res.json())
        .then(data => {
          playlistBox.innerHTML = "";
          data.playlist.forEach(url => {
            const li = document.createElement('li');
            const a = document.createElement('a');
            a.href = url;
            a.textContent = url;
            a.target = "_blank";
            li.appendChild(a);
            playlistBox.appendChild(li);
          });
        });
    });
  }, 'image/jpeg');
}, 5000);
