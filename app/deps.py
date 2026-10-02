from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.security import decode_token
from app.database import get_db

bearer = HTTPBearer(auto_error=False)

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = decode_token(credentials.credentials)
        user_id = int(payload["sub"]); role = payload["role"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"id": user_id, "role": role}

def require_role(role: str):
    def checker(user=Depends(current_user)):
        if user["role"] != role:
            raise HTTPException(status_code=403, detail=f"{role.title()} access required")
        return user
    return checker
