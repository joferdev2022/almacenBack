from fastapi import APIRouter,HTTPException, status, Depends, Query
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordRequestForm

from app.services.auth_service import authenticate_user, create_access_token
from app.models.auth_model import ResponseAuthModel

router = APIRouter()

@router.post("/auth", tags=["authentication"])
async def login(data: OAuth2PasswordRequestForm = Depends()):
    user = await authenticate_user(data.username, data.password)
    print(user)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.username, "local":user.local}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "user": user.username, "local": user.local, "permissions":user.permissions, "token_type": "bearer"}
        