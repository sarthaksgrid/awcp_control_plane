from fastapi import APIRouter
import app.api.v1.endpoints.doneapi as doneapi
import app.api.v1.endpoints.testapi as testapi
import app.api.v1.endpoints.agentsapi as agentsapi
import app.api.v1.endpoints.temporalapi as temporalapi

api_router = APIRouter()

api_router.include_router(
    doneapi.router,
    tags=["Done"]
)


api_router.include_router(
    testapi.router,
    tags=["Test"]
)

api_router.include_router(
    agentsapi.router,
    tags=["agents"]
)


api_router.include_router(
    temporalapi.router,
    tags=["Temporal"]
)