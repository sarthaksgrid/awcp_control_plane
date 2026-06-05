from fastapi import APIRouter
from enum import Enum

router = APIRouter()

@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}





# class Color(str, Enum):
#     red = "red"
#     blue = "blue"
#     green = "green"

# @router.get("/items/")
# def get_items(color: Color):
#     return {"selected_color": color}



