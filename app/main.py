from fastapi import FastAPI, Request


from app.api.router import api_router


app = FastAPI(
    title="AWCP Temporal Control Plane",
    description="Starts Temporal workflows from HTTP requests.",
    version="1.0.0",
)


app.include_router(api_router)


# Default route
@app.get("/health")
def root(request: Request):
    return {"message": "AWCP Temporal Control Plane is healthy!"}