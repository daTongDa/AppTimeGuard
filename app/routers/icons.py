"""应用图标 API"""
from urllib.parse import unquote

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.services.icons import extract_icon_png

router = APIRouter(prefix="/api/icons", tags=["icons"])


@router.get("")
def get_icon(
    path: str = Query(..., min_length=1, description="exe 绝对路径"),
    size: int = Query(32, ge=16, le=128),
):
    exe = unquote(path).strip().strip('"')
    data, _src = extract_icon_png(exe, size=size)
    return Response(
        content=data,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Icon-Source": _src,
        },
    )
