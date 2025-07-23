import os
import io
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Читаем из ENV
CLIENT_ID     = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"]
FOLDER_ID     = os.environ["DRIVE_FOLDER_ID"]  # добавьте эту переменную, если не сделали ранее

SCOPES = ["https://www.googleapis.com/auth/drive.file",
          "https://www.googleapis.com/auth/drive.metadata"]

def get_drive_service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)

def upload_file_bytes(name: str, data_bytes: bytes) -> dict:
    """
    Заливает данные (bytes) как файл name в папку FOLDER_ID.
    Возвращает метаданные созданного файла.
    """
    service = get_drive_service()
    metadata = {"name": name, "parents": [FOLDER_ID]}
    media = MediaIoBaseUpload(io.BytesIO(data_bytes), mimetype="text/plain")
    created = service.files().create(
        body=metadata, media_body=media, fields="id, webViewLink"
    ).execute()
    return created
