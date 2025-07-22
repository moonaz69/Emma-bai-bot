# gdrive.py

import os
import io
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Читаем ключ из переменной окружения
creds_info = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))

SCOPES = ["https://www.googleapis.com/auth/drive"]
creds = service_account.Credentials.from_service_account_info(
    creds_info, scopes=SCOPES
)

drive_service = build("drive", "v3", credentials=creds)

def upload_file_local(filepath: str, folder_id: str) -> dict:
    """
    Загружает локальный файл в указанную папку на Google Drive.
    Возвращает метаданные созданного файла (id, webViewLink).
    """
    file_metadata = {
        "name": os.path.basename(filepath),
        "parents": [folder_id],
    }
    media = MediaIoBaseUpload(
        io.FileIO(filepath, "rb"), mimetype="application/octet-stream"
    )
    created = (
        drive_service.files()
        .create(body=file_metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )
    return created
