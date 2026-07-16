from fastapi import APIRouter

from rafeeq_backend.modules.auth.api.router import router as auth_router
from rafeeq_backend.modules.activities.api.router import router as activities_router
from rafeeq_backend.modules.doctors.api.router import router as doctors_router
from rafeeq_backend.modules.devices.api.router import router as devices_router
from rafeeq_backend.modules.emergencies.api.router import router as emergencies_router
from rafeeq_backend.modules.patients.api.router import router as patients_router
from rafeeq_backend.modules.memories.api.router import router as memories_router
from rafeeq_backend.modules.reports.api.router import router as reports_router
from rafeeq_backend.modules.routines.api.router import router as routines_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(activities_router)
api_router.include_router(auth_router)
api_router.include_router(doctors_router)
api_router.include_router(devices_router)
api_router.include_router(emergencies_router)
api_router.include_router(memories_router)
api_router.include_router(patients_router)
api_router.include_router(reports_router)
api_router.include_router(routines_router)


@api_router.get("/meta", tags=["meta"])
async def api_metadata() -> dict[str, object]:
    return {"name": "RAFEEQ API", "version": 1, "primary_locale": "ar"}
