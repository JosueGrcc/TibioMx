from flask import Flask, request, jsonify, render_template_string, send_from_directory
from flask_cors import CORS
from db import (
    crear_usuario, obtener_usuario_por_correo, obtener_usuario_por_nombre, obtener_usuario_por_id,
    crear_apuesta, obtener_apuestas_activas, obtener_apuesta_por_id, realizar_jugada, resolver_apuesta,
    obtener_tabla_de_posiciones, crear_grupo, obtener_grupos_de_usuario, obtener_grupo_por_id,
    agregar_miembro_a_grupo, obtener_apuestas_de_grupo, verificar_bono_diario, recompensa_por_anuncio,
    obtener_jugadas_de_usuario, actualizar_puntos_usuario, borrar_apuesta
)
import jwt
import datetime
import os
from functools import wraps
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'tibiomx_secret_2024'

# ─── Middleware de Autenticación ───────────────────────────────────────────────

def requiere_token(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token requerido'}), 401
        try:
            datos = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            usuario_actual = obtener_usuario_por_id(datos['user_id'])
            if not usuario_actual:
                return jsonify({'error': 'Usuario no encontrado'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except Exception:
            return jsonify({'error': 'Token inválido'}), 401
        return f(usuario_actual, *args, **kwargs)
    return decorador

# ─── Rutas de Autenticación ────────────────────────────────────────────────────

@app.route('/api/register', methods=['POST'])
def registrar():
    datos = request.get_json()
    nombre_usuario = datos.get('username', '').strip()
    correo = datos.get('email', '').strip().lower()
    contrasena = datos.get('password', '')

    if not all([nombre_usuario, correo, contrasena]):
        return jsonify({'error': 'Todos los campos son requeridos'}), 400
    if len(contrasena) < 6:
        return jsonify({'error': 'La contraseña debe tener al menos 6 caracteres'}), 400
    if obtener_usuario_por_correo(correo):
        return jsonify({'error': 'El correo ya está registrado'}), 409
    if obtener_usuario_por_nombre(nombre_usuario):
        return jsonify({'error': 'El nombre de usuario ya existe'}), 409

    usuario = crear_usuario(nombre_usuario, correo, contrasena)
    token = jwt.encode({
        'user_id': str(usuario['_id']),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }, app.config['SECRET_KEY'])

    return jsonify({
        'token': token,
        'user': {
            'id': str(usuario['_id']),
            'username': usuario['username'],
            'email': usuario['email'],
            'points': usuario['points']
        }
    }), 201


@app.route('/api/login', methods=['POST'])
def iniciar_sesion():
    datos = request.get_json()
    correo = datos.get('email', '').strip().lower()
    contrasena = datos.get('password', '')

    usuario = obtener_usuario_por_correo(correo)
    if not usuario:
        return jsonify({'error': 'Credenciales incorrectas'}), 401

    import bcrypt
    if not bcrypt.checkpw(contrasena.encode(), usuario['password_hash']):
        return jsonify({'error': 'Credenciales incorrectas'}), 401

    # Bono diario
    resultado_bono = verificar_bono_diario(str(usuario['_id']))

    token = jwt.encode({
        'user_id': str(usuario['_id']),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }, app.config['SECRET_KEY'])

    return jsonify({
        'token': token,
        'user': {
            'id': str(usuario['_id']),
            'username': usuario['username'],
            'email': usuario['email'],
            'points': usuario['points'] + (resultado_bono.get('bonus', 0) if resultado_bono else 0)
        },
        'daily_bonus': resultado_bono
    })


@app.route('/api/me', methods=['GET'])
@requiere_token
def obtener_mi_perfil(usuario_actual):
    return jsonify({
        'id': str(usuario_actual['_id']),
        'username': usuario_actual['username'],
        'email': usuario_actual['email'],
        'points': usuario_actual['points'],
        'created_at': usuario_actual['created_at'].isoformat()
    })

# ─── Rutas de Apuestas ─────────────────────────────────────────────────────────

@app.route('/api/bets', methods=['GET'])
@requiere_token
def listar_apuestas(usuario_actual):
    id_grupo = request.args.get('group_id')
    apuestas = obtener_apuestas_activas(id_grupo)
    resultado = []
    for apuesta in apuestas:
        resultado.append({
            'id': str(apuesta['_id']),
            'title': apuesta['title'],
            'description': apuesta.get('description', ''),
            'creator': apuesta['creator_username'],
            'options': apuesta['options'],
            'ends_at': apuesta['ends_at'].isoformat(),
            'created_at': apuesta['created_at'].isoformat(),
            'status': apuesta['status'],
            'total_pool': apuesta.get('total_pool', 0),
            'wager_count': apuesta.get('wager_count', 0),
            'group_id': str(apuesta['group_id']) if apuesta.get('group_id') else None,
            'live_participants': apuesta.get('live_participants', [])
        })
    return jsonify(resultado)


@app.route('/api/bets', methods=['POST'])
@requiere_token
def crear_nueva_apuesta(usuario_actual):
    datos = request.get_json()
    titulo = datos.get('title', '').strip()
    descripcion = datos.get('description', '').strip()
    opciones = datos.get('options', [])
    fecha_fin_str = datos.get('ends_at')
    id_grupo = datos.get('group_id')

    if not titulo or len(opciones) < 2:
        return jsonify({'error': 'Título y al menos 2 opciones requeridos'}), 400

    try:
        fecha_fin = datetime.datetime.fromisoformat(fecha_fin_str)
    except Exception:
        return jsonify({'error': 'Fecha inválida'}), 400

    if fecha_fin <= datetime.datetime.utcnow():
        return jsonify({'error': 'La fecha debe ser futura'}), 400

    apuesta = crear_apuesta(
        id_creador=str(usuario_actual['_id']),
        nombre_creador=usuario_actual['username'],
        titulo=titulo,
        descripcion=descripcion,
        opciones=opciones,
        fecha_fin=fecha_fin,
        id_grupo=id_grupo
    )

    return jsonify({'id': str(apuesta['_id']), 'message': '¡Apuesta creada!'}), 201



@app.route('/api/bets/<id_apuesta>/wager', methods=['POST'])
@requiere_token
def realizar_nueva_jugada(usuario_actual, id_apuesta):
    datos = request.get_json()
    opcion = datos.get('option')
    cantidad = int(datos.get('amount', 0))

    if cantidad <= 0:
        return jsonify({'error': 'Cantidad inválida'}), 400
    if usuario_actual['points'] < cantidad:
        return jsonify({'error': 'Puntos insuficientes'}), 400

    apuesta = obtener_apuesta_por_id(id_apuesta)
    if not apuesta:
        return jsonify({'error': 'Apuesta no encontrada'}), 404
    if apuesta['status'] != 'active':
        return jsonify({'error': 'Apuesta cerrada'}), 400
    if opcion not in apuesta['options']:
        return jsonify({'error': 'Opción inválida'}), 400
    if datetime.datetime.utcnow() > apuesta['ends_at']:
        return jsonify({'error': 'La apuesta ya terminó'}), 400

    resultado = realizar_jugada(
        id_apuesta=id_apuesta,
        id_usuario=str(usuario_actual['_id']),
        nombre_usuario=usuario_actual['username'],
        opcion=opcion,
        cantidad=cantidad
    )

    if resultado.get('error'):
        return jsonify(resultado), 400

    actualizar_puntos_usuario(str(usuario_actual['_id']), -cantidad)
    return jsonify({'message': f'¡Apostaste {cantidad} CuckostaPoints en "{opcion}"!', 'new_points': usuario_actual['points'] - cantidad})


@app.route('/api/bets/<id_apuesta>/resolve', methods=['POST'])
@requiere_token
def resolver_apuesta_ruta(usuario_actual, id_apuesta):
    datos = request.get_json()
    opcion_ganadora = datos.get('winning_option')

    apuesta = obtener_apuesta_por_id(id_apuesta)
    if not apuesta:
        return jsonify({'error': 'Apuesta no encontrada'}), 404
    if apuesta['creator_id'] != str(usuario_actual['_id']):
        return jsonify({'error': 'Solo el creador puede resolver'}), 403
    if apuesta['status'] != 'active':
        return jsonify({'error': 'Ya fue resuelta'}), 400
    if opcion_ganadora not in apuesta['options']:
        return jsonify({'error': 'Opción inválida'}), 400

    ganadores = resolver_apuesta(id_apuesta, opcion_ganadora)
    # Enviar notificaciones por correo (mejor esfuerzo)
    for g in ganadores:
        try:
            _enviar_correo_resultado(g['email'], g['username'], apuesta['title'], g['won'], g['payout'])
        except Exception:
            pass

    return jsonify({'message': f'Apuesta resuelta. Ganadores: {len(ganadores)}', 'winners': ganadores})


@app.route('/api/bets/my-wagers', methods=['GET'])
@requiere_token
def mis_jugadas(usuario_actual):
    jugadas = obtener_jugadas_de_usuario(str(usuario_actual['_id']))
    return jsonify(jugadas)

# ─── Rutas de Grupos ──────────────────────────────────────────────────────────

@app.route('/api/groups', methods=['GET'])
@requiere_token
def listar_grupos(usuario_actual):
    grupos = obtener_grupos_de_usuario(str(usuario_actual['_id']))
    return jsonify([{
        'id': str(g['_id']),
        'name': g['name'],
        'description': g.get('description', ''),
        'member_count': len(g.get('members', [])),
        'invite_code': g['invite_code'],
        'created_by': g['created_by_username']
    } for g in grupos])


@app.route('/api/groups', methods=['POST'])
@requiere_token
def crear_nuevo_grupo(usuario_actual):
    datos = request.get_json()
    nombre = datos.get('name', '').strip()
    descripcion = datos.get('description', '').strip()

    if not nombre:
        return jsonify({'error': 'Nombre requerido'}), 400

    grupo = crear_grupo(str(usuario_actual['_id']), usuario_actual['username'], nombre, descripcion)
    return jsonify({
        'id': str(grupo['_id']),
        'invite_code': grupo['invite_code'],
        'message': '¡Grupo creado!'
    }), 201


@app.route('/api/groups/join', methods=['POST'])
@requiere_token
def unirse_a_grupo(usuario_actual):
    datos = request.get_json()
    codigo_invitacion = datos.get('invite_code', '').strip().upper()

    from db import obtener_grupo_por_codigo_invitacion
    grupo = obtener_grupo_por_codigo_invitacion(codigo_invitacion)
    if not grupo:
        return jsonify({'error': 'Código inválido'}), 404

    resultado = agregar_miembro_a_grupo(str(grupo['_id']), str(usuario_actual['_id']), usuario_actual['username'])
    if resultado.get('error'):
        return jsonify(resultado), 400

    return jsonify({'message': f'¡Te uniste a {grupo["name"]}!', 'group_id': str(grupo['_id'])})

# ─── Tabla de Posiciones y Recompensas ────────────────────────────────────────

@app.route('/api/leaderboard', methods=['GET'])
@requiere_token
def tabla_de_posiciones(usuario_actual):
    top = obtener_tabla_de_posiciones(5)
    return jsonify([{
        'rank': i + 1,
        'username': u['username'],
        'points': u['points']
    } for i, u in enumerate(top)])


@app.route('/api/ad-reward', methods=['POST'])
@requiere_token
def ver_anuncio(usuario_actual):
    resultado = recompensa_por_anuncio(str(usuario_actual['_id']))
    if resultado.get('error'):
        return jsonify(resultado), 429
    return jsonify({'message': f'¡Ganaste {resultado["reward"]} CuckostaPoints por ver el anuncio!', 'reward': resultado['reward'], 'new_points': resultado['new_points']})

# ─── Ayudante de Correo ───────────────────────────────────────────────────────

def _enviar_correo_resultado(correo, nombre_usuario, titulo_apuesta, gano, pago):
    # Configurar con SMTP real en producción
    pass

# ─── Servir el Frontend ───────────────────────────────────────────────────────

@app.route('/')
def pagina_principal():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    import os
    puerto = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=puerto, debug=False)