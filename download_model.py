import gdown

# Google Drive file ID
file_id = '1_BqAliUogtwouXewY1wGxWvSurLrDRSw'  # Replace with your FILE_ID
url = f"https://drive.google.com/uc?id={file_id}"
output = "emotion_model.ph"  # Desired local filename

# Download the file
gdown.download(url, output, quiet=False)