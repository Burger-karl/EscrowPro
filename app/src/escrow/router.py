import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from app.core.dependencies import CurrentUser, DbSession
from 