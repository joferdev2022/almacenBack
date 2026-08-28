from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

from config import settings

MONGO_INITDB_ROOT_USERNAME = settings.MONGO_INITDB_ROOT_USERNAME
MONGO_INITDB_ROOT_PASSWORD = settings.MONGO_INITDB_ROOT_PASSWORD
MONGO_CLUSTER_NAME = settings.MONGO_CLUSTER_NAME 

# uri = f"mongodb+srv://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_CLUSTER_NAME}.mongodb.net/?retryWrites=true&w=majority"
uri = "mongodb+srv://almacen:almacen@cluster0.3omflck.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(uri, server_api=ServerApi('1'))
# client = MongoClient(uri)
# Send a ping to confirm a successful connection


try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
    db = client.almacen
    db_liquor = client.licoreria

    # Items = db["usuarios"]
    productsDb = db["products"]
    salesDb = db["sales"]
    authDb = db["auth"]
    sellersDb = db["salenMan"]
    providersDb = db["providers"]
    expensesDb = db["expenses"]
    # categories = db["categories"]
    
    #licoreria bd
    auth_liquorDb = db_liquor["auth"]
    products_liquorDb = db_liquor["products"]
    sales_liquorDb = db_liquor["sales"]
    providers_liquorDb = db_liquor["providers"]
    expenses_liquorDb = db_liquor["expenses"]
    
    
except Exception as e:
    print(e)

