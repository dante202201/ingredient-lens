"""管理接口鉴权"""

from typing import Optional

from fastapi import Header, HTTPException

from config.settings import get_settings


def verify_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    token = get_settings().admin_token
    if not token:
        return
    if x_admin_token != token:
        raise HTTPException(status_code=401, detail="无效的管理员 Token")
