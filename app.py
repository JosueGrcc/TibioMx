from flask import Flask, request, jsonify, render_template_string, send_from_directory
from flask_cors import CORS
from db import (
    create_user, get_user_by_email, get_user_by_username, get_user_by_id,
    create_bet, get_active_bets, get_bet_by_id, place_wager, resolve_bet,
    get_leaderboard, create_group, get_user_groups, get_group_by_id,
    add_member_to_group, get_group_bets, daily_bonus_check, ad_reward,
    get_user_wagers, update_user_points
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

# ─── Auth Middleware ────────────────────────────────────────────────────────────

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token requerido'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = get_user_by_id(data['user_id'])
            if not current_user:
                return jsonify({'error': 'Usuario no encontrado'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except Exception:
            return jsonify({'error': 'Token inválido'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# ─── Auth Routes ────────────────────────────────────────────────────────────────

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not all([username, email, password]):
        return jsonify({'error': 'Todos los campos son requeridos'}), 400
    if len(password) < 6:
        return jsonify({'error': 'La contraseña debe tener al menos 6 caracteres'}), 400
    if get_user_by_email(email):
        return jsonify({'error': 'El correo ya está registrado'}), 409
    if get_user_by_username(username):
        return jsonify({'error': 'El nombre de usuario ya existe'}), 409

    user = create_user(username, email, password)
    token = jwt.encode({
        'user_id': str(user['_id']),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }, app.config['SECRET_KEY'])

    return jsonify({
        'token': token,
        'user': {
            'id': str(user['_id']),
            'username': user['username'],
            'email': user['email'],
            'points': user['points']
        }
    }), 201


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = get_user_by_email(email)
    if not user:
        return jsonify({'error': 'Credenciales incorrectas'}), 401

    import bcrypt
    if not bcrypt.checkpw(password.encode(), user['password_hash']):
        return jsonify({'error': 'Credenciales incorrectas'}), 401

    # Daily bonus
    bonus_result = daily_bonus_check(str(user['_id']))

    token = jwt.encode({
        'user_id': str(user['_id']),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }, app.config['SECRET_KEY'])

    return jsonify({
        'token': token,
        'user': {
            'id': str(user['_id']),
            'username': user['username'],
            'email': user['email'],
            'points': user['points'] + (bonus_result.get('bonus', 0) if bonus_result else 0)
        },
        'daily_bonus': bonus_result
    })


@app.route('/api/me', methods=['GET'])
@token_required
def get_me(current_user):
    return jsonify({
        'id': str(current_user['_id']),
        'username': current_user['username'],
        'email': current_user['email'],
        'points': current_user['points'],
        'created_at': current_user['created_at'].isoformat()
    })

# ─── Bets Routes ────────────────────────────────────────────────────────────────

@app.route('/api/bets', methods=['GET'])
@token_required
def list_bets(current_user):
    group_id = request.args.get('group_id')
    bets = get_active_bets(group_id)
    result = []
    for bet in bets:
        result.append({
            'id': str(bet['_id']),
            'title': bet['title'],
            'description': bet.get('description', ''),
            'creator': bet['creator_username'],
            'options': bet['options'],
            'ends_at': bet['ends_at'].isoformat(),
            'created_at': bet['created_at'].isoformat(),
            'status': bet['status'],
            'total_pool': bet.get('total_pool', 0),
            'wager_count': bet.get('wager_count', 0),
            'group_id': str(bet['group_id']) if bet.get('group_id') else None,
            'live_participants': bet.get('live_participants', [])
        })
    return jsonify(result)


@app.route('/api/bets', methods=['POST'])
@token_required
def create_new_bet(current_user):
    data = request.get_json()
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    options = data.get('options', [])
    ends_at_str = data.get('ends_at')
    group_id = data.get('group_id')

    if not title or len(options) < 2:
        return jsonify({'error': 'Título y al menos 2 opciones requeridos'}), 400

    try:
        ends_at = datetime.datetime.fromisoformat(ends_at_str)
    except Exception:
        return jsonify({'error': 'Fecha inválida'}), 400

    if ends_at <= datetime.datetime.utcnow():
        return jsonify({'error': 'La fecha debe ser futura'}), 400

    bet = create_bet(
        creator_id=str(current_user['_id']),
        creator_username=current_user['username'],
        title=title,
        description=description,
        options=options,
        ends_at=ends_at,
        group_id=group_id
    )

    return jsonify({'id': str(bet['_id']), 'message': '¡Apuesta creada!'}), 201


@app.route('/api/bets/<bet_id>/wager', methods=['POST'])
@token_required
def place_bet_wager(current_user, bet_id):
    data = request.get_json()
    option = data.get('option')
    amount = int(data.get('amount', 0))

    if amount <= 0:
        return jsonify({'error': 'Cantidad inválida'}), 400
    if current_user['points'] < amount:
        return jsonify({'error': 'Puntos insuficientes'}), 400

    bet = get_bet_by_id(bet_id)
    if not bet:
        return jsonify({'error': 'Apuesta no encontrada'}), 404
    if bet['status'] != 'active':
        return jsonify({'error': 'Apuesta cerrada'}), 400
    if option not in bet['options']:
        return jsonify({'error': 'Opción inválida'}), 400
    if datetime.datetime.utcnow() > bet['ends_at']:
        return jsonify({'error': 'La apuesta ya terminó'}), 400

    result = place_wager(
        bet_id=bet_id,
        user_id=str(current_user['_id']),
        username=current_user['username'],
        option=option,
        amount=amount
    )

    if result.get('error'):
        return jsonify(result), 400

    update_user_points(str(current_user['_id']), -amount)
    return jsonify({'message': f'¡Apostaste {amount} CuckostaPoints en "{option}"!', 'new_points': current_user['points'] - amount})


@app.route('/api/bets/<bet_id>/resolve', methods=['POST'])
@token_required
def resolve_bet_route(current_user, bet_id):
    data = request.get_json()
    winning_option = data.get('winning_option')

    bet = get_bet_by_id(bet_id)
    if not bet:
        return jsonify({'error': 'Apuesta no encontrada'}), 404
    if bet['creator_id'] != str(current_user['_id']):
        return jsonify({'error': 'Solo el creador puede resolver'}), 403
    if bet['status'] != 'active':
        return jsonify({'error': 'Ya fue resuelta'}), 400
    if winning_option not in bet['options']:
        return jsonify({'error': 'Opción inválida'}), 400

    winners = resolve_bet(bet_id, winning_option)
    # Send email notifications (best-effort)
    for w in winners:
        try:
            _send_result_email(w['email'], w['username'], bet['title'], w['won'], w['payout'])
        except Exception:
            pass

    return jsonify({'message': f'Apuesta resuelta. Ganadores: {len(winners)}', 'winners': winners})


@app.route('/api/bets/my-wagers', methods=['GET'])
@token_required
def my_wagers(current_user):
    wagers = get_user_wagers(str(current_user['_id']))
    return jsonify(wagers)

# ─── Groups Routes ──────────────────────────────────────────────────────────────

@app.route('/api/groups', methods=['GET'])
@token_required
def list_groups(current_user):
    groups = get_user_groups(str(current_user['_id']))
    return jsonify([{
        'id': str(g['_id']),
        'name': g['name'],
        'description': g.get('description', ''),
        'member_count': len(g.get('members', [])),
        'invite_code': g['invite_code'],
        'created_by': g['created_by_username']
    } for g in groups])


@app.route('/api/groups', methods=['POST'])
@token_required
def create_new_group(current_user):
    data = request.get_json()
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()

    if not name:
        return jsonify({'error': 'Nombre requerido'}), 400

    group = create_group(str(current_user['_id']), current_user['username'], name, description)
    return jsonify({
        'id': str(group['_id']),
        'invite_code': group['invite_code'],
        'message': '¡Grupo creado!'
    }), 201


@app.route('/api/groups/join', methods=['POST'])
@token_required
def join_group(current_user):
    data = request.get_json()
    invite_code = data.get('invite_code', '').strip().upper()

    from db import get_group_by_invite_code
    group = get_group_by_invite_code(invite_code)
    if not group:
        return jsonify({'error': 'Código inválido'}), 404

    result = add_member_to_group(str(group['_id']), str(current_user['_id']), current_user['username'])
    if result.get('error'):
        return jsonify(result), 400

    return jsonify({'message': f'¡Te uniste a {group["name"]}!', 'group_id': str(group['_id'])})

# ─── Leaderboard & Rewards ──────────────────────────────────────────────────────

@app.route('/api/leaderboard', methods=['GET'])
@token_required
def leaderboard(current_user):
    top = get_leaderboard(5)
    return jsonify([{
        'rank': i + 1,
        'username': u['username'],
        'points': u['points']
    } for i, u in enumerate(top)])


@app.route('/api/ad-reward', methods=['POST'])
@token_required
def watch_ad(current_user):
    result = ad_reward(str(current_user['_id']))
    if result.get('error'):
        return jsonify(result), 429
    return jsonify({'message': f'¡Ganaste {result["reward"]} CuckostaPoints por ver el anuncio!', 'reward': result['reward'], 'new_points': result['new_points']})

# ─── Email Helper ────────────────────────────────────────────────────────────────

def _send_result_email(email, username, bet_title, won, payout):
    # Configure with real SMTP in production
    pass

# ─── Serve Frontend ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
