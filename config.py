import os
from dotenv import load_dotenv
from pathlib import Path




# env_path = Path('.env')
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)


class Settings:
    # PROJECT_NAME: str = "Login Api"
    PROJECT_VERSION:str = "1.0"
    
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    JWT_SECRET = os.getenv('JWT_SECRET')
    JWT_ALGORITHM = os.getenv('JWT_ALGORITHM')
    JWT_TOKEN_EXPIRE_MINUTES: int = os.getenv('JWT_TOKEN_EXPIRE_MINUTES')          
    PROJECT_NAME = os.getenv('PROJECT_NAME')               

    MONGO_INITDB_ROOT_USERNAME="tesistool"
    MONGO_INITDB_ROOT_PASSWORD="tesistool"
    MONGO_INITDB_DATABASE="almacen"
# MONGO_CLUSTER_NAME="cluster0.3omflck"
# MONGO_CLUSTER_NAME="cluster0.dbg3vmh"
    MONGO_CLUSTER_NAME="cluster0.jbhkfhy"


settings = Settings()