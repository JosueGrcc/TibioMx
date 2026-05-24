from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_session import Session
from db import (
    crear_usuario, obtener_usuario_por_correo, obtener_usuario_por_nombre, obtener_usuario_por_id,
    crear_apuesta, obtener_apuestas_activas, obtener_apuesta_por_id, realizar_jugada, resolver_apuesta,
    obtener_tabla_de_posiciones, crear_grupo, obtener_grupos_de_usuario, obtener_grupo_por_id,
    agregar_miembro_a_grupo, verificar_bono_diario, recompensa_por_anuncio,
    obtener_jugadas_de_usuario, actualizar_puntos_usuario, obtener_grupo_por_codigo_invitacion,
    borrar_apuesta, es_admin,
    # Admin usuarios
    obtener_todos_usuarios, borrar_usuario, actualizar_puntos_admin, toggle_admin,
    # Admin apuestas
    obtener_todas_apuestas,
    # Anuncios
    obtener_videos_anuncios, obtener_todos_videos_anuncios,
    agregar_video_anuncio, actualizar_video_anuncio, borrar_video_anuncio,
    BET_CREATION_COST,
)
import bcrypt
import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tibiomx_secret_2024'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_sessions'
app.config['SESSION_PERMANENT'] = False
Session(app)

os.makedirs('/tmp/flask_sessions', exist_ok=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def usuario_actual():
    uid = session.get('user_id')
    if not uid:
        return None
    return obtener_usuario_por_id(uid)


def requiere_login():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return None


def requiere_admin():
    uid = session.get('user_id')
    if not uid or not es_admin(uid):
        flash('Acceso denegado — se requieren privilegios de administrador.', 'error')
        return redirect(url_for('inicio'))
    return None


# ─── Auth ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if session.get('user_id'):
        return redirect(url_for('inicio'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('inicio'))
    error = None
    if request.method == 'POST':
        correo = request.form.get('email', '').strip().lower()
        contrasena = request.form.get('password', '')
        usuario = obtener_usuario_por_correo(correo)
        if not usuario or not bcrypt.checkpw(contrasena.encode(), usuario['password_hash']):
            error = 'Credenciales incorrectas'
        else:
            session['user_id'] = str(usuario['_id'])
            bono = verificar_bono_diario(str(usuario['_id']))
            if bono and bono.get('bonus', 0) > 0:
                flash(f"🌅 +{bono['bonus']} CuckostaPoints de bono diario!", 'win')
            return redirect(url_for('inicio'))
    return render_template('login.html', error=error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('inicio'))
    error = None
    if request.method == 'POST':
        nombre = request.form.get('username', '').strip()
        correo = request.form.get('email', '').strip().lower()
        contrasena = request.form.get('password', '')
        if not all([nombre, correo, contrasena]):
            error = 'Todos los campos son requeridos'
        elif len(contrasena) < 6:
            error = 'La contraseña debe tener al menos 6 caracteres'
        elif obtener_usuario_por_correo(correo):
            error = 'El correo ya está registrado'
        elif obtener_usuario_por_nombre(nombre):
            error = 'El nombre de usuario ya existe'
        else:
            usuario = crear_usuario(nombre, correo, contrasena)
            session['user_id'] = str(usuario['_id'])
            flash('¡Cuenta creada! Bienvenido con 1,000 CuckostaPoints 🎉', 'win')
            return redirect(url_for('inicio'))
    return render_template('register.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── Inicio ───────────────────────────────────────────────────────────────────

@app.route('/inicio')
def inicio():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    apuestas = obtener_apuestas_activas()
    en_vivo = [b for b in apuestas if b.get('live_participants')][:3]
    return render_template('inicio.html', usuario=u, apuestas=apuestas, en_vivo=en_vivo, active='home')


# ─── Apuestas ─────────────────────────────────────────────────────────────────

@app.route('/apuestas')
def apuestas():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    id_grupo = request.args.get('group_id')
    lista = obtener_apuestas_activas(id_grupo)
    grupos = obtener_grupos_de_usuario(str(u['_id']))
    return render_template(
        'apuestas.html',
        usuario=u, apuestas=lista, grupos=grupos,
        id_grupo_sel=id_grupo,
        bet_cost=BET_CREATION_COST,
        active='bets',
    )


@app.route('/apuestas/crear', methods=['POST'])
def crear_apuesta_ruta():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()

    # ── COSTO de creación ────────────────────────────────────────────────────
    if u['points'] < BET_CREATION_COST:
        flash(f'Necesitas al menos {BET_CREATION_COST} CuckostaPoints para crear una apuesta.', 'error')
        return redirect(url_for('apuestas'))

    titulo = request.form.get('title', '').strip()
    descripcion = request.form.get('description', '').strip()
    opciones_raw = request.form.getlist('options')
    opciones = [o.strip() for o in opciones_raw if o.strip()]
    fecha_fin_str = request.form.get('ends_at', '')
    id_grupo = request.form.get('group_id') or None

    # Offset de zona horaria enviado por el browser (minutos para llegar a UTC)
    try:
        tz_offset_min = int(request.form.get('tz_offset', 0))
    except (ValueError, TypeError):
        tz_offset_min = 0

    if not titulo or len(opciones) < 2 or not fecha_fin_str:
        flash('Completa todos los campos y al menos 2 opciones', 'error')
        return redirect(url_for('apuestas'))
    try:
        fecha_fin_local = datetime.datetime.fromisoformat(fecha_fin_str)
        # Convertir hora local del usuario a UTC sumando el offset
        fecha_fin = fecha_fin_local + datetime.timedelta(minutes=tz_offset_min)
    except Exception:
        flash('Fecha inválida', 'error')
        return redirect(url_for('apuestas'))
    if fecha_fin <= datetime.datetime.utcnow():
        flash('La fecha debe ser futura', 'error')
        return redirect(url_for('apuestas'))

    # Cobrar los puntos ANTES de crear
    actualizar_puntos_usuario(str(u['_id']), -BET_CREATION_COST)

    crear_apuesta(
        id_creador=str(u['_id']),
        nombre_creador=u['username'],
        titulo=titulo,
        descripcion=descripcion,
        opciones=opciones,
        fecha_fin=fecha_fin,
        id_grupo=id_grupo,
    )
    flash(f'¡Apuesta creada! Se cobraron {BET_CREATION_COST} CuckostaPoints 🎉', 'win')
    return redirect(url_for('apuestas'))


@app.route('/apuestas/<id_apuesta>/apostar', methods=['POST'])
def apostar(id_apuesta):
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()

    apuesta = obtener_apuesta_por_id(id_apuesta)
    if not apuesta or apuesta['status'] != 'active':
        flash('Apuesta no disponible', 'error')
        return redirect(url_for('apuestas'))

    # ── No puedes apostar en tu propia apuesta ────────────────────────────────
    if apuesta['creator_id'] == str(u['_id']):
        flash('No puedes apostar en tu propia apuesta 🚫', 'error')
        return redirect(url_for('apuestas'))

    opcion = request.form.get('option', '')
    try:
        cantidad = int(request.form.get('amount', 0))
    except ValueError:
        flash('Cantidad inválida', 'error')
        return redirect(url_for('apuestas'))

    if cantidad <= 0:
        flash('Cantidad inválida', 'error')
        return redirect(url_for('apuestas'))
    if u['points'] < cantidad:
        flash('Puntos insuficientes', 'error')
        return redirect(url_for('apuestas'))
    if opcion not in apuesta['options']:
        flash('Opción inválida', 'error')
        return redirect(url_for('apuestas'))
    if datetime.datetime.utcnow() > apuesta['ends_at']:
        flash('La apuesta ya terminó', 'error')
        return redirect(url_for('apuestas'))

    resultado = realizar_jugada(
        id_apuesta=id_apuesta,
        id_usuario=str(u['_id']),
        nombre_usuario=u['username'],
        opcion=opcion,
        cantidad=cantidad,
    )
    if resultado.get('error'):
        flash(resultado['error'], 'error')
    else:
        actualizar_puntos_usuario(str(u['_id']), -cantidad)
        flash(f'🎲 ¡Apostaste {cantidad} pts en "{opcion}"!', 'win')

    return redirect(url_for('apuestas'))


@app.route('/apuestas/<id_apuesta>/resolver', methods=['POST'])
def resolver(id_apuesta):
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    apuesta = obtener_apuesta_por_id(id_apuesta)
    if not apuesta:
        flash('Apuesta no encontrada', 'error')
        return redirect(url_for('apuestas'))
    if apuesta['creator_id'] != str(u['_id']) and not u.get('is_admin'):
        flash('Solo el creador puede resolver', 'error')
        return redirect(url_for('apuestas'))
    opcion_ganadora = request.form.get('winning_option', '')
    if opcion_ganadora not in apuesta['options']:
        flash('Opción inválida', 'error')
        return redirect(url_for('apuestas'))

    ganadores = resolver_apuesta(id_apuesta, opcion_ganadora)
    n_ganadores = len([g for g in ganadores if g['won']])
    flash(f'✅ Apuesta resuelta. {n_ganadores} ganadores.', 'win')
    return redirect(url_for('apuestas'))


@app.route('/apuestas/<id_apuesta>/borrar', methods=['POST'])
def borrar_apuesta_ruta(id_apuesta):
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    apuesta = obtener_apuesta_por_id(id_apuesta)
    if not apuesta:
        flash('Apuesta no encontrada', 'error')
        return redirect(url_for('apuestas'))
    if apuesta['creator_id'] != str(u['_id']) and not u.get('is_admin'):
        flash('Sin permiso para borrar esta apuesta', 'error')
        return redirect(url_for('apuestas'))
    borrar_apuesta(id_apuesta)
    flash('🗑️ Apuesta eliminada.', 'win')
    redir_after = request.form.get('redirect', 'apuestas')
    return redirect(url_for(redir_after) if redir_after in ('apuestas', 'admin_panel') else url_for('apuestas'))


# ─── Grupos ───────────────────────────────────────────────────────────────────

@app.route('/grupos')
def grupos():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    lista = obtener_grupos_de_usuario(str(u['_id']))
    return render_template('grupos.html', usuario=u, grupos=lista, active='groups')


@app.route('/grupos/crear', methods=['POST'])
def crear_grupo_ruta():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    nombre = request.form.get('name', '').strip()
    descripcion = request.form.get('description', '').strip()
    if not nombre:
        flash('Nombre requerido', 'error')
        return redirect(url_for('grupos'))
    grupo = crear_grupo(str(u['_id']), u['username'], nombre, descripcion)
    flash(f'¡Grupo creado! Código de invitación: {grupo["invite_code"]} 🎉', 'win')
    return redirect(url_for('grupos'))


@app.route('/grupos/unirse', methods=['POST'])
def unirse_grupo():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    codigo = request.form.get('invite_code', '').strip().upper()
    grupo = obtener_grupo_por_codigo_invitacion(codigo)
    if not grupo:
        flash('Código inválido', 'error')
        return redirect(url_for('grupos'))
    resultado = agregar_miembro_a_grupo(str(grupo['_id']), str(u['_id']), u['username'])
    if resultado.get('error'):
        flash(resultado['error'], 'error')
    else:
        flash(f'¡Te uniste a {grupo["name"]}! 🎉', 'win')
    return redirect(url_for('grupos'))


# ─── Historial ────────────────────────────────────────────────────────────────

@app.route('/historial')
def historial():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    jugadas = obtener_jugadas_de_usuario(str(u['_id']))
    return render_template('historial.html', usuario=u, jugadas=jugadas, active='history')


# ─── Tabla de posiciones ──────────────────────────────────────────────────────

@app.route('/leaderboard')
def leaderboard():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    top = obtener_tabla_de_posiciones(5)
    return render_template('leaderboard.html', usuario=u, top=top, active='leaderboard')


# ─── Recompensas ─────────────────────────────────────────────────────────────

@app.route('/recompensas')
def recompensas():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    videos = obtener_videos_anuncios()
    return render_template('recompensas.html', usuario=u, videos=videos, active='rewards')


@app.route('/recompensas/anuncio', methods=['POST'])
def ver_anuncio():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    id_video = request.form.get('video_id')
    resultado = recompensa_por_anuncio(str(u['_id']), id_video)
    if resultado.get('error'):
        flash(resultado['error'], 'error')
    else:
        flash(f'💰 ¡Ganaste {resultado["reward"]} CuckostaPoints por ver el anuncio!', 'win')
    return redirect(url_for('recompensas'))


# ─── Panel Admin ──────────────────────────────────────────────────────────────

@app.route('/admin')
def admin_panel():
    redir = requiere_login()
    if redir: return redir
    bloqueo = requiere_admin()
    if bloqueo: return bloqueo

    u = usuario_actual()
    usuarios = obtener_todos_usuarios()
    apuestas_all = obtener_todas_apuestas()
    videos = obtener_todos_videos_anuncios()
    return render_template(
        'admin.html',
        usuario=u,
        usuarios=usuarios,
        apuestas_all=apuestas_all,
        videos=videos,
        active='admin',
    )


# Admin — usuarios

@app.route('/admin/usuario/<id_u>/borrar', methods=['POST'])
def admin_borrar_usuario(id_u):
    redir = requiere_login()
    if redir: return redir
    bloqueo = requiere_admin()
    if bloqueo: return bloqueo
    u_actual = usuario_actual()
    if id_u == str(u_actual['_id']):
        flash('No puedes borrarte a ti mismo.', 'error')
        return redirect(url_for('admin_panel'))
    borrar_usuario(id_u)
    flash('Usuario eliminado.', 'win')
    return redirect(url_for('admin_panel'))


@app.route('/admin/usuario/<id_u>/puntos', methods=['POST'])
def admin_actualizar_puntos(id_u):
    redir = requiere_login()
    if redir: return redir
    bloqueo = requiere_admin()
    if bloqueo: return bloqueo
    try:
        nuevos = int(request.form.get('points', 0))
    except ValueError:
        flash('Valor inválido', 'error')
        return redirect(url_for('admin_panel'))
    actualizar_puntos_admin(id_u, nuevos)
    flash('Puntos actualizados ✅', 'win')
    return redirect(url_for('admin_panel'))


@app.route('/admin/usuario/<id_u>/toggle-admin', methods=['POST'])
def admin_toggle_admin(id_u):
    redir = requiere_login()
    if redir: return redir
    bloqueo = requiere_admin()
    if bloqueo: return bloqueo
    u_actual = usuario_actual()
    if id_u == str(u_actual['_id']):
        flash('No puedes quitarte los privilegios a ti mismo.', 'error')
        return redirect(url_for('admin_panel'))
    toggle_admin(id_u)
    flash('Privilegios actualizados.', 'win')
    return redirect(url_for('admin_panel'))


# Admin — apuestas

@app.route('/admin/apuesta/<id_apuesta>/borrar', methods=['POST'])
def admin_borrar_apuesta(id_apuesta):
    redir = requiere_login()
    if redir: return redir
    bloqueo = requiere_admin()
    if bloqueo: return bloqueo
    borrar_apuesta(id_apuesta)
    flash('🗑️ Apuesta eliminada.', 'win')
    return redirect(url_for('admin_panel'))


@app.route('/admin/apuesta/<id_apuesta>/resolver', methods=['POST'])
def admin_resolver_apuesta(id_apuesta):
    redir = requiere_login()
    if redir: return redir
    bloqueo = requiere_admin()
    if bloqueo: return bloqueo
    apuesta = obtener_apuesta_por_id(id_apuesta)
    if not apuesta:
        flash('Apuesta no encontrada', 'error')
        return redirect(url_for('admin_panel'))
    opcion_ganadora = request.form.get('winning_option', '')
    if opcion_ganadora not in apuesta['options']:
        flash('Opción inválida', 'error')
        return redirect(url_for('admin_panel'))
    ganadores = resolver_apuesta(id_apuesta, opcion_ganadora)
    n = len([g for g in ganadores if g['won']])
    flash(f'✅ Apuesta resuelta. {n} ganadores.', 'win')
    return redirect(url_for('admin_panel'))


# Admin — videos anuncios

@app.route('/admin/video/agregar', methods=['POST'])
def admin_agregar_video():
    redir = requiere_login()
    if redir: return redir
    bloqueo = requiere_admin()
    if bloqueo: return bloqueo
    title = request.form.get('title', '').strip()
    url = request.form.get('url', '').strip()
    try:
        rmin = int(request.form.get('reward_min', 10))
        rmax = int(request.form.get('reward_max', 50))
    except ValueError:
        rmin, rmax = 10, 50
    if not title or not url:
        flash('Título y URL son requeridos', 'error')
        return redirect(url_for('admin_panel'))
    agregar_video_anuncio(title, url, rmin, rmax)
    flash('Video de anuncio agregado ✅', 'win')
    return redirect(url_for('admin_panel') + '#videos')


@app.route('/admin/video/<video_id>/borrar', methods=['POST'])
def admin_borrar_video(video_id):
    redir = requiere_login()
    if redir: return redir
    bloqueo = requiere_admin()
    if bloqueo: return bloqueo
    borrar_video_anuncio(video_id)
    flash('Video eliminado.', 'win')
    return redirect(url_for('admin_panel') + '#videos')


@app.route('/admin/video/<video_id>/toggle', methods=['POST'])
def admin_toggle_video(video_id):
    redir = requiere_login()
    if redir: return redir
    bloqueo = requiere_admin()
    if bloqueo: return bloqueo
    videos = obtener_todos_videos_anuncios()
    actual = next((v for v in videos if v['id'] == video_id), None)
    if actual:
        actualizar_video_anuncio(video_id, active=not actual.get('active', True))
    flash('Estado del video actualizado.', 'win')
    return redirect(url_for('admin_panel') + '#videos')


# ─── Template filters ─────────────────────────────────────────────────────────

@app.template_filter('formato_puntos')
def formato_puntos(n):
    return f"{n:,} pts".replace(',', ',')


@app.template_filter('tiempo_restante')
def tiempo_restante(fecha_fin):
    ahora = datetime.datetime.utcnow()
    diff = fecha_fin - ahora
    if diff.total_seconds() <= 0:
        return 'Terminó'
    horas = diff.total_seconds() / 3600
    if horas < 1:
        return f"{int(diff.total_seconds() / 60)}min"
    return f"{int(horas)}h"


if __name__ == '__main__':
    puerto = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=puerto, debug=False)