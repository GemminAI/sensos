from fastapi import APIRouter

from .routes import router as v1_router
from .routes_browser import generate_router, states_router

api_router = APIRouter()
api_router.include_router(v1_router)
