import json
from functools import lru_cache

from google.cloud import firestore
from google.oauth2 import service_account

from app.core.config import settings

@lru_cache
def get_firestore_client() -> firestore.Client:
    if settings.FIRESTORE_CREDENTIALS_JSON:
        info = json.loads(settings.FIRESTORE_CREDENTIALS_JSON)
        credentials = service_account.Credentials.from_service_account_info(info)
        return firestore.Client(project=settings.FIRESTORE_PROJECT_ID, credentials=credentials)

    if settings.GOOGLE_APPLICATION_CREDENTIALS:
        return firestore.Client.from_service_account_json(settings.GOOGLE_APPLICATION_CREDENTIALS, project=settings.FIRESTORE_PROJECT_ID)

    return firestore.Client(project=settings.FIRESTORE_PROJECT_ID)