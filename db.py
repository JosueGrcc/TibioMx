from pymongo import MongoClient
import certifi

MONGO_URI = 'mongodb+srv://sixeven_db_user:andresjr1234@brazzino01.ba7bkul.mongodb.net/?appName=Brazzino01'
ca = certifi.where()

def db_connection():
    try:
        client = MongoClient(MONGO_URI, tlsCAFile=ca)
        db = client['db_appuestas']
    except ConnectionError as e:
        print('Error de conexion con la base de datos')
    else:
        print('Conexion exitosa')
        return db