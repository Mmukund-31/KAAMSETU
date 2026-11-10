from fastapi import APIRouter

from app.api.v1 import auth, health, management, voice, work_orders

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(voice.router)
# management before work_orders: its fixed path /checklists/templates must be matched before
# the parameterised /checklists/{checklist_id}.
api_router.include_router(management.router)
api_router.include_router(work_orders.router)
