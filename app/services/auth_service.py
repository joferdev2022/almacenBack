from passlib.context import CryptContext
import jwt
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, timedelta

from app.db.mongo import authDb
from app.models.auth_model import UserModel

SECRET_KEY = "fernando"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# def find_user_by_email(email: str):
#     user = authDb.find_one({"email": email})
#     return user
async def authenticate_user(username: str, password: str):
    user = authDb.find_one({"username": username})
    if user and verify_password(password, user["password"]):
        user["_id"] = str(user["_id"])
        return UserModel(**user)
    return False

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt