from pymongo import MongoClient, DESCENDING
import certifi
import bcrypt
import datetime
import random
import string
from bson import ObjectId

MONGO_URI = 'mongodb+srv://sixeven_db_user:andresjr1234@brazzino01.ba7bkul.mongodb.net/?appName=Brazzino01'

# ─── Conexión Perezosa ─────────────────────────────────────────────────────────
# No conectar al importar — solo cuando se haga la primera query real.
# Esto evita el crash SSL en Python 3.14 durante el startup de Render.

_cliente = None
_base_datos = None

def obtener_base_datos():
    global _cliente, _base_datos
    if _base_datos is None:
        ca = certifi.where()
        _cliente = MongoClient(
            MONGO_URI,
            tlsCAFile=ca,
            tls=True,
            serverSelectionTimeoutMS=30000,
            connectTimeoutMS=30000,
            socketTimeoutMS=30000,
        )
        _base_datos = _cliente['tibiomx']
        try:
            _base_datos['users'].create_index('email', unique=True)
            _base_datos['users'].create_index('username', unique=True)
            _base_datos['bets'].create_index('status')
            _base_datos['bets'].create_index('ends_at')
            _base_datos['wagers'].create_index([('bet_id', 1), ('user_id', 1)])
            _base_datos['groups'].create_index('invite_code', unique=True)
        except Exception:
            pass
    return _base_datos

def Usuarios(): return obtener_base_datos()['users']
def Apuestas(): return obtener_base_datos()['bets']
def Jugadas(): return obtener_base_datos()['wagers']
def Grupos(): return obtener_base_datos()['groups']

# ─── Usuarios ─────────────────────────────────────────────────────────────────

def crear_usuario(nombre_usuario, correo, contrasena):
    hash_contrasena = bcrypt.hashpw(contrasena.encode(), bcrypt.gensalt())
    usuario = {
        'username': nombre_usuario,
        'email': correo,
        'password_hash': hash_contrasena,
        'points': 1000,
        'created_at': datetime.datetime.utcnow(),
        'last_daily_bonus': None,
        'last_ad_reward': None
    }
    resultado = Usuarios().insert_one(usuario)
    usuario['_id'] = resultado.inserted_id
    return usuario

def obtener_usuario_por_correo(correo):
    return Usuarios().find_one({'email': correo.lower()})

def obtener_usuario_por_nombre(nombre_usuario):
    return Usuarios().find_one({'username': nombre_usuario})

def obtener_usuario_por_id(id_usuario):
    try:
        return Usuarios().find_one({'_id': ObjectId(id_usuario)})
    except Exception:
        return None

def actualizar_puntos_usuario(id_usuario, delta):
    Usuarios().update_one({'_id': ObjectId(id_usuario)}, {'$inc': {'points': delta}})
    return Usuarios().find_one({'_id': ObjectId(id_usuario)})

def verificar_bono_diario(id_usuario):
    usuario = obtener_usuario_por_id(id_usuario)
    if not usuario:
        return None
    ahora = datetime.datetime.utcnow()
    ultimo = usuario.get('last_daily_bonus')
    if ultimo and (ahora - ultimo).total_seconds() < 86400:
        return {'bonus': 0, 'message': 'Ya recibiste tu bono de hoy'}
    bono = 100
    Usuarios().update_one(
        {'_id': ObjectId(id_usuario)},
        {'$inc': {'points': bono}, '$set': {'last_daily_bonus': ahora}}
    )
    return {'bonus': bono, 'message': '+100 CuckostaPoints diarios!'}

def recompensa_por_anuncio(id_usuario):
    usuario = obtener_usuario_por_id(id_usuario)
    if not usuario:
        return {'error': 'Usuario no encontrado'}
    ahora = datetime.datetime.utcnow()
    ultimo = usuario.get('last_ad_reward')
    if ultimo and (ahora - ultimo).total_seconds() < 3600:
        tiempo_restante = 3600 - int((ahora - ultimo).total_seconds())
        return {'error': f'Espera {tiempo_restante // 60} min para ver otro anuncio'}
    recompensa = random.randint(10, 50)
    Usuarios().update_one(
        {'_id': ObjectId(id_usuario)},
        {'$inc': {'points': recompensa}, '$set': {'last_ad_reward': ahora}}
    )
    actualizado = obtener_usuario_por_id(id_usuario)
    return {'reward': recompensa, 'new_points': actualizado['points']}

# ─── Apuestas ─────────────────────────────────────────────────────────────────

def crear_apuesta(id_creador, nombre_creador, titulo, descripcion, opciones, fecha_fin, id_grupo=None):
    apuesta = {
        'creator_id': id_creador,
        'creator_username': nombre_creador,
        'title': titulo,
        'description': descripcion,
        'options': opciones,
        'ends_at': fecha_fin,
        'created_at': datetime.datetime.utcnow(),
        'status': 'active',
        'winning_option': None,
        'total_pool': 0,
        'wager_count': 0,
        'group_id': ObjectId(id_grupo) if id_grupo else None,
        'live_participants': []
    }
    resultado = Apuestas().insert_one(apuesta)
    apuesta['_id'] = resultado.inserted_id
    return apuesta


def obtener_apuestas_activas(id_grupo=None):
    consulta = {'status': 'active', 'ends_at': {'$gt': datetime.datetime.utcnow()}}
    if id_grupo:
        consulta['group_id'] = ObjectId(id_grupo)
    else:
        consulta['group_id'] = None
    return list(Apuestas().find(consulta).sort('created_at', DESCENDING))

def obtener_apuesta_por_id(id_apuesta):
    try:
        return Apuestas().find_one({'_id': ObjectId(id_apuesta)})
    except Exception:
        return None

def realizar_jugada(id_apuesta, id_usuario, nombre_usuario, opcion, cantidad):
    jugada_existente = Jugadas().find_one({'bet_id': id_apuesta, 'user_id': id_usuario})
    if jugada_existente:
        return {'error': 'Ya apostaste en esta apuesta'}
    jugada = {
        'bet_id': id_apuesta,
        'user_id': id_usuario,
        'username': nombre_usuario,
        'option': opcion,
        'amount': cantidad,
        'timestamp': datetime.datetime.utcnow()
    }
    Jugadas().insert_one(jugada)
    entrada_en_vivo = {
        'username': nombre_usuario,
        'option': opcion,
        'amount': cantidad,
        'timestamp': datetime.datetime.utcnow().isoformat()
    }
    Apuestas().update_one(
        {'_id': ObjectId(id_apuesta)},
        {
            '$inc': {'total_pool': cantidad, 'wager_count': 1},
            '$push': {'live_participants': {'$each': [entrada_en_vivo], '$slice': -20}}
        }
    )
    return {'ok': True}

def resolver_apuesta(id_apuesta, opcion_ganadora):
    Apuestas().update_one(
        {'_id': ObjectId(id_apuesta)},
        {'$set': {'status': 'resolved', 'winning_option': opcion_ganadora, 'live_participants': []}}
    )
    todas_las_jugadas = list(Jugadas().find({'bet_id': id_apuesta}))
    jugadas_ganadoras = [j for j in todas_las_jugadas if j['option'] == opcion_ganadora]
    pool_total = sum(j['amount'] for j in todas_las_jugadas)
    pool_ganadores = sum(j['amount'] for j in jugadas_ganadoras)
    ganadores = []
    for j in todas_las_jugadas:
        usuario = obtener_usuario_por_id(j['user_id'])
        if not usuario:
            continue
        if j['option'] == opcion_ganadora and pool_ganadores > 0:
            pago = int((j['amount'] / pool_ganadores) * pool_total)
            actualizar_puntos_usuario(j['user_id'], pago)
            ganadores.append({'username': j['username'], 'email': usuario['email'], 'payout': pago, 'won': True})
        else:
            ganadores.append({'username': j['username'], 'email': usuario['email'], 'payout': 0, 'won': False})
    Jugadas().update_many({'bet_id': id_apuesta}, {'$set': {'resolved': True, 'winning_option': opcion_ganadora}})
    return ganadores

def obtener_jugadas_de_usuario(id_usuario):
    jugadas = list(Jugadas().find({'user_id': id_usuario}).sort('timestamp', DESCENDING).limit(50))
    resultado = []
    for j in jugadas:
        apuesta = obtener_apuesta_por_id(j['bet_id'])
        resultado.append({
            'bet_title': apuesta['title'] if apuesta else 'Apuesta eliminada',
            'option': j['option'],
            'amount': j['amount'],
            'timestamp': j['timestamp'].isoformat(),
            'status': apuesta['status'] if apuesta else 'unknown',
            'winning_option': apuesta.get('winning_option') if apuesta else None,
            'won': j['option'] == apuesta.get('winning_option') if apuesta and apuesta.get('winning_option') else None
        })
    return resultado

# ─── Grupos ───────────────────────────────────────────────────────────────────

def _generar_codigo_invitacion():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def crear_grupo(id_creador, nombre_creador, nombre, descripcion):
    codigo = _generar_codigo_invitacion()
    while Grupos().find_one({'invite_code': codigo}):
        codigo = _generar_codigo_invitacion()
    grupo = {
        'name': nombre,
        'description': descripcion,
        'created_by': id_creador,
        'created_by_username': nombre_creador,
        'invite_code': codigo,
        'members': [{'user_id': id_creador, 'username': nombre_creador}],
        'created_at': datetime.datetime.utcnow()
    }
    resultado = Grupos().insert_one(grupo)
    grupo['_id'] = resultado.inserted_id
    return grupo

def obtener_grupo_por_id(id_grupo):
    try:
        return Grupos().find_one({'_id': ObjectId(id_grupo)})
    except Exception:
        return None

def obtener_grupo_por_codigo_invitacion(codigo):
    return Grupos().find_one({'invite_code': codigo.upper()})

def obtener_grupos_de_usuario(id_usuario):
    return list(Grupos().find({'members.user_id': id_usuario}))

def agregar_miembro_a_grupo(id_grupo, id_usuario, nombre_usuario):
    grupo = obtener_grupo_por_id(id_grupo)
    if not grupo:
        return {'error': 'Grupo no encontrado'}
    if any(m['user_id'] == id_usuario for m in grupo.get('members', [])):
        return {'error': 'Ya eres miembro de este grupo'}
    Grupos().update_one(
        {'_id': ObjectId(id_grupo)},
        {'$push': {'members': {'user_id': id_usuario, 'username': nombre_usuario}}}
    )
    return {'ok': True}

def obtener_apuestas_de_grupo(id_grupo):
    return list(Apuestas().find({'group_id': ObjectId(id_grupo)}).sort('created_at', DESCENDING))

# ─── Tabla de Posiciones ──────────────────────────────────────────────────────

def obtener_tabla_de_posiciones(limite=5):
    return list(Usuarios().find({}, {'username': 1, 'points': 1}).sort('points', DESCENDING).limit(limite))