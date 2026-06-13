from fastapi import APIRouter

from app.api.contract import include_contract_routes

api_v1_router = include_contract_routes(APIRouter(prefix="/api/v1"))
