from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_session import Session
from db import (
    crear_usuario, obtener_usuario_por_correo, obtener_usuario_por_nombre, obtener_usuario_por_id,
    crear_apuesta, obtener_apuestas_activas, obtener_apuesta_por_id, realizar_jugada, resolver_apuesta,
    obtener_tabla_de_posiciones, crear_grupo, obtener_grupos_de_usuario, obtener_grupo_por_id,
    agregar_miembro_a_grupo, verificar_bono_diario, recompensa_por_anuncio,
    obtener_jugadas_de_usuario, actualizar_puntos_usuario, obtener_grupo_por_codigo_invitacion
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
    return render_template('apuestas.html', usuario=u, apuestas=lista, grupos=grupos, id_grupo_sel=id_grupo, active='bets')

@app.route('/apuestas/crear', methods=['POST'])
def crear_apuesta_ruta():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    titulo = request.form.get('title', '').strip()
    descripcion = request.form.get('description', '').strip()
    opciones_raw = request.form.getlist('options')
    opciones = [o.strip() for o in opciones_raw if o.strip()]
    fecha_fin_str = request.form.get('ends_at', '')
    id_grupo = request.form.get('group_id') or None

    if not titulo or len(opciones) < 2 or not fecha_fin_str:
        flash('Completa todos los campos y al menos 2 opciones', 'error')
        return redirect(url_for('apuestas'))
    try:
        fecha_fin = datetime.datetime.fromisoformat(fecha_fin_str)
    except Exception:
        flash('Fecha inválida', 'error')
        return redirect(url_for('apuestas'))
    if fecha_fin <= datetime.datetime.utcnow():
        flash('La fecha debe ser futura', 'error')
        return redirect(url_for('apuestas'))

    crear_apuesta(
        id_creador=str(u['_id']),
        nombre_creador=u['username'],
        titulo=titulo,
        descripcion=descripcion,
        opciones=opciones,
        fecha_fin=fecha_fin,
        id_grupo=id_grupo
    )
    flash('¡Apuesta creada! 🎉', 'win')
    return redirect(url_for('apuestas'))

@app.route('/apuestas/<id_apuesta>/apostar', methods=['POST'])
def apostar(id_apuesta):
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
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

    apuesta = obtener_apuesta_por_id(id_apuesta)
    if not apuesta or apuesta['status'] != 'active':
        flash('Apuesta no disponible', 'error')
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
        cantidad=cantidad
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
    if apuesta['creator_id'] != str(u['_id']):
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
    return render_template('recompensas.html', usuario=u, active='rewards')

@app.route('/recompensas/anuncio', methods=['POST'])
def ver_anuncio():
    redir = requiere_login()
    if redir: return redir
    u = usuario_actual()
    resultado = recompensa_por_anuncio(str(u['_id']))
    if resultado.get('error'):
        flash(resultado['error'], 'error')
    else:
        flash(f'💰 ¡Ganaste {resultado["reward"]} CuckostaPoints por ver el anuncio!', 'win')
    return redirect(url_for('recompensas'))

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