from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.services.system_settings import branding_logo_document, public_branding_response


router = APIRouter(prefix="/branding", tags=["Branding"])


@router.get("")
async def get_branding(request: Request):
    return await public_branding_response(request.app.state.database)


@router.get("/logo", include_in_schema=False)
async def get_branding_logo(request: Request):
    document = await branding_logo_document(request.app.state.database)
    if not document:
        raise HTTPException(status_code=404)

    return Response(
        content=bytes(document["data"]),
        media_type=document["content_type"],
        headers={"Cache-Control": "public, max-age=3600"},
    )
