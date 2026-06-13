from fastapi import APIRouter

from app.api.contract import include_contract_routes
from app.api.v1.router import api_v1_router

legacy_api_router = include_contract_routes(APIRouter(prefix="/api"))

api_router = APIRouter()
api_router.include_router(api_v1_router)
api_router.include_router(legacy_api_router)
