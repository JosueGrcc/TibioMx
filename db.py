from pymongo import MongoClient, DESCENDING
import certifi
import bcrypt
import datetime
import random
import string
import ssl
from bson import ObjectId

MONGO_URI = 'mongodb+srv://sixeven_db_user:andresjr1234@brazzino01.ba7bkul.mongodb.net/?appName=Brazzino01'

_cliente = None
_base_datos = None

ADMIN_USERNAME = 'admin'
ADMIN_EMAIL    = 'admin@tibiomx.com'
ADMIN_PASSWORD = 'Admin1234!'   # cámbialo en producción

BET_CREATION_COST = 100          # CuckostaPoints para crear una apuesta

def obtener_base_datos():
    global _cliente, _base_datos
    if _base_datos is None:
        intentos = [
            lambda: MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=20000,
            ),
            lambda: MongoClient(
                MONGO_URI,
                tlsCAFile=certifi.where(),
                tls=True,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=20000,
            ),
            lambda: MongoClient(
                MONGO_URI,
                tlsAllowInvalidCertificates=True,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=20000,
            ),
        ]

        ultimo_error = None
        for construir_cliente in intentos:
            try:
                c = construir_cliente()
                c['tibiomx'].command('ping')
                _cliente = c
                _base_datos = _cliente['tibiomx']
                break
            except Exception as e:
                ultimo_error = e
                try:
                    c.close()
                except Exception:
                    pass
                continue

        if _base_datos is None:
            raise RuntimeError(
                f'No se pudo conectar a MongoDB Atlas después de 3 intentos.\n'
                f'Último error: {ultimo_error}'
            )

        try:
            _base_datos['users'].create_index('email', unique=True)
            _base_datos['users'].create_index('username', unique=True)
            _base_datos['bets'].create_index('status')
            _base_datos['bets'].create_index('ends_at')
            _base_datos['wagers'].create_index([('bet_id', 1), ('user_id', 1)])
            _base_datos['groups'].create_index('invite_code', unique=True)
            _base_datos['site_config'].create_index('key', unique=True)
        except Exception:
            pass

        # Asegurar que exista la cuenta admin
        _asegurar_admin()
        # Asegurar config inicial de videos de anuncios
        _asegurar_config_anuncios()

    return _base_datos


def _asegurar_admin():
    col = _base_datos['users']
    if col.find_one({'username': ADMIN_USERNAME}):
        return
    hash_pw = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt())
    col.insert_one({
        'username': ADMIN_USERNAME,
        'email': ADMIN_EMAIL,
        'password_hash': hash_pw,
        'points': 999999,
        'is_admin': True,
        'created_at': datetime.datetime.utcnow(),
        'last_daily_bonus': None,
        'last_ad_reward': None,
    })


def _asegurar_config_anuncios():
    col = _base_datos['site_config']
    if col.find_one({'key': 'ad_videos'}):
        return
    col.insert_one({
        'key': 'ad_videos',
        'videos': [
            # Ejemplos por defecto — el admin puede cambiarlos
            {
                'id': _nuevo_id_video(),
                'title': 'Anuncio de bienvenida',
                'url': 'https://www.w3schools.com/html/mov_bbb.mp4',
                'reward_min': 10,
                'reward_max': 50,
                'active': True,
            }
        ],
        'updated_at': datetime.datetime.utcnow(),
    })


def _nuevo_id_video():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


# ─── Colecciones ──────────────────────────────────────────────────────────────

def Usuarios():    return obtener_base_datos()['users']
def Apuestas():    return obtener_base_datos()['bets']
def Jugadas():     return obtener_base_datos()['wagers']
def Grupos():      return obtener_base_datos()['groups']
def SiteConfig():  return obtener_base_datos()['site_config']


# ─── Usuarios ─────────────────────────────────────────────────────────────────

def crear_usuario(nombre_usuario, correo, contrasena):
    hash_contrasena = bcrypt.hashpw(contrasena.encode(), bcrypt.gensalt())
    usuario = {
        'username': nombre_usuario,
        'email': correo,
        'password_hash': hash_contrasena,
        'points': 1000,
        'is_admin': False,
        'created_at': datetime.datetime.utcnow(),
        'last_daily_bonus': None,
        'last_ad_reward': None,
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


def es_admin(id_usuario):
    u = obtener_usuario_por_id(id_usuario)
    return bool(u and u.get('is_admin'))


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


def recompensa_por_anuncio(id_usuario, id_video=None):
    usuario = obtener_usuario_por_id(id_usuario)
    if not usuario:
        return {'error': 'Usuario no encontrado'}
    ahora = datetime.datetime.utcnow()
    ultimo = usuario.get('last_ad_reward')
    if ultimo and (ahora - ultimo).total_seconds() < 3600:
        tiempo_restante = 3600 - int((ahora - ultimo).total_seconds())
        return {'error': f'Espera {tiempo_restante // 60} min para ver otro anuncio'}

    # Obtener rango de recompensa según el video seleccionado
    reward_min, reward_max = 10, 50
    if id_video:
        videos = obtener_videos_anuncios()
        for v in videos:
            if v.get('id') == id_video and v.get('active'):
                reward_min = v.get('reward_min', 10)
                reward_max = v.get('reward_max', 50)
                break

    recompensa = random.randint(reward_min, reward_max)
    Usuarios().update_one(
        {'_id': ObjectId(id_usuario)},
        {'$inc': {'points': recompensa}, '$set': {'last_ad_reward': ahora}}
    )
    actualizado = obtener_usuario_por_id(id_usuario)
    return {'reward': recompensa, 'new_points': actualizado['points']}


# ─── Admin: gestión de usuarios ───────────────────────────────────────────────

def obtener_todos_usuarios(limite=200):
    return list(Usuarios().find({}).sort('created_at', DESCENDING).limit(limite))


def borrar_usuario(id_usuario):
    """Elimina usuario y todas sus jugadas."""
    Jugadas().delete_many({'user_id': id_usuario})
    Usuarios().delete_one({'_id': ObjectId(id_usuario)})


def actualizar_puntos_admin(id_usuario, nuevos_puntos):
    Usuarios().update_one({'_id': ObjectId(id_usuario)}, {'$set': {'points': nuevos_puntos}})


def toggle_admin(id_usuario):
    u = obtener_usuario_por_id(id_usuario)
    if not u:
        return
    Usuarios().update_one(
        {'_id': ObjectId(id_usuario)},
        {'$set': {'is_admin': not u.get('is_admin', False)}}
    )


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
        'live_participants': [],
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


def obtener_todas_apuestas(limite=300):
    return list(Apuestas().find({}).sort('created_at', DESCENDING).limit(limite))


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
        'timestamp': datetime.datetime.utcnow(),
    }
    Jugadas().insert_one(jugada)
    entrada_en_vivo = {
        'username': nombre_usuario,
        'option': opcion,
        'amount': cantidad,
        'timestamp': datetime.datetime.utcnow().isoformat(),
    }
    Apuestas().update_one(
        {'_id': ObjectId(id_apuesta)},
        {
            '$inc': {'total_pool': cantidad, 'wager_count': 1},
            '$push': {'live_participants': {'$each': [entrada_en_vivo], '$slice': -20}},
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
            'won': j['option'] == apuesta.get('winning_option') if apuesta and apuesta.get('winning_option') else None,
        })
    return resultado


def borrar_apuesta(id_apuesta):
    Apuestas().delete_one({'_id': ObjectId(id_apuesta)})
    Jugadas().delete_many({'bet_id': id_apuesta})


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
        'created_at': datetime.datetime.utcnow(),
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


# ─── Tabla de posiciones ──────────────────────────────────────────────────────

def obtener_tabla_de_posiciones(limite=5):
    return list(Usuarios().find({}, {'username': 1, 'points': 1}).sort('points', DESCENDING).limit(limite))


# ─── Anuncios / videos ────────────────────────────────────────────────────────

def obtener_config_anuncios():
    return SiteConfig().find_one({'key': 'ad_videos'})


def obtener_videos_anuncios():
    cfg = obtener_config_anuncios()
    if not cfg:
        return []
    return [v for v in cfg.get('videos', []) if v.get('active', True)]


def obtener_todos_videos_anuncios():
    """Para panel admin (incluye inactivos)."""
    cfg = obtener_config_anuncios()
    if not cfg:
        return []
    return cfg.get('videos', [])


def agregar_video_anuncio(title, url, reward_min=10, reward_max=50):
    nuevo = {
        'id': _nuevo_id_video(),
        'title': title,
        'url': url,
        'reward_min': reward_min,
        'reward_max': reward_max,
        'active': True,
    }
    SiteConfig().update_one(
        {'key': 'ad_videos'},
        {'$push': {'videos': nuevo}, '$set': {'updated_at': datetime.datetime.utcnow()}}
    )
    return nuevo


def actualizar_video_anuncio(video_id, title=None, url=None, reward_min=None, reward_max=None, active=None):
    cfg = obtener_config_anuncios()
    if not cfg:
        return False
    videos = cfg.get('videos', [])
    for v in videos:
        if v['id'] == video_id:
            if title is not None:      v['title'] = title
            if url is not None:        v['url'] = url
            if reward_min is not None: v['reward_min'] = reward_min
            if reward_max is not None: v['reward_max'] = reward_max
            if active is not None:     v['active'] = active
            break
    SiteConfig().update_one(
        {'key': 'ad_videos'},
        {'$set': {'videos': videos, 'updated_at': datetime.datetime.utcnow()}}
    )
    return True


def borrar_video_anuncio(video_id):
    cfg = obtener_config_anuncios()
    if not cfg:
        return False
    videos = [v for v in cfg.get('videos', []) if v['id'] != video_id]
    SiteConfig().update_one(
        {'key': 'ad_videos'},
        {'$set': {'videos': videos, 'updated_at': datetime.datetime.utcnow()}}
    )
    return True