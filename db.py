from pymongo import MongoClient, DESCENDING
import certifi
import bcrypt
import datetime
import random
import string
from bson import ObjectId

MONGO_URI = 'mongodb+srv://sixeven_db_user:andresjr1234@brazzino01.ba7bkul.mongodb.net/?appName=Brazzino01'
ca = certifi.where()

# ─── Connection ─────────────────────────────────────────────────────────────────

def get_db():
    client = MongoClient(MONGO_URI, tlsCAFile=ca)
    return client['tibiomx']

db = get_db()

# Collections
users_col     = db['users']
bets_col      = db['bets']
wagers_col    = db['wagers']
groups_col    = db['groups']
ad_log_col    = db['ad_log']

# Indexes
users_col.create_index('email', unique=True)
users_col.create_index('username', unique=True)
bets_col.create_index('status')
bets_col.create_index('ends_at')
wagers_col.create_index([('bet_id', 1), ('user_id', 1)])
groups_col.create_index('invite_code', unique=True)

# ─── Users ──────────────────────────────────────────────────────────────────────

def create_user(username, email, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    user = {
        'username': username,
        'email': email,
        'password_hash': hashed,
        'points': 1000,
        'created_at': datetime.datetime.utcnow(),
        'last_daily_bonus': None,
        'last_ad_reward': None
    }
    result = users_col.insert_one(user)
    user['_id'] = result.inserted_id
    return user


def get_user_by_email(email):
    return users_col.find_one({'email': email.lower()})


def get_user_by_username(username):
    return users_col.find_one({'username': username})


def get_user_by_id(user_id):
    try:
        return users_col.find_one({'_id': ObjectId(user_id)})
    except Exception:
        return None


def update_user_points(user_id, delta):
    users_col.update_one(
        {'_id': ObjectId(user_id)},
        {'$inc': {'points': delta}}
    )
    return users_col.find_one({'_id': ObjectId(user_id)})


def daily_bonus_check(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return None
    now = datetime.datetime.utcnow()
    last = user.get('last_daily_bonus')
    if last and (now - last).total_seconds() < 86400:
        return {'bonus': 0, 'message': 'Ya recibiste tu bono de hoy'}
    bonus = 100
    users_col.update_one(
        {'_id': ObjectId(user_id)},
        {'$inc': {'points': bonus}, '$set': {'last_daily_bonus': now}}
    )
    return {'bonus': bonus, 'message': '¡+100 CuckostaPoints diarios!'}


def ad_reward(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return {'error': 'Usuario no encontrado'}
    now = datetime.datetime.utcnow()
    last = user.get('last_ad_reward')
    # 1 ad per hour
    if last and (now - last).total_seconds() < 3600:
        remaining = 3600 - int((now - last).total_seconds())
        return {'error': f'Espera {remaining // 60} min para ver otro anuncio'}
    reward = random.randint(10, 50)
    users_col.update_one(
        {'_id': ObjectId(user_id)},
        {'$inc': {'points': reward}, '$set': {'last_ad_reward': now}}
    )
    updated = get_user_by_id(user_id)
    return {'reward': reward, 'new_points': updated['points']}

# ─── Bets ───────────────────────────────────────────────────────────────────────

def create_bet(creator_id, creator_username, title, description, options, ends_at, group_id=None):
    bet = {
        'creator_id': creator_id,
        'creator_username': creator_username,
        'title': title,
        'description': description,
        'options': options,
        'ends_at': ends_at,
        'created_at': datetime.datetime.utcnow(),
        'status': 'active',  # active | resolved | expired
        'winning_option': None,
        'total_pool': 0,
        'wager_count': 0,
        'group_id': ObjectId(group_id) if group_id else None,
        'live_participants': []  # list of {username, option, amount, timestamp}
    }
    result = bets_col.insert_one(bet)
    bet['_id'] = result.inserted_id
    return bet


def get_active_bets(group_id=None):
    query = {'status': 'active', 'ends_at': {'$gt': datetime.datetime.utcnow()}}
    if group_id:
        query['group_id'] = ObjectId(group_id)
    else:
        query['group_id'] = None
    return list(bets_col.find(query).sort('created_at', DESCENDING))


def get_bet_by_id(bet_id):
    try:
        return bets_col.find_one({'_id': ObjectId(bet_id)})
    except Exception:
        return None


def place_wager(bet_id, user_id, username, option, amount):
    existing = wagers_col.find_one({'bet_id': bet_id, 'user_id': user_id})
    if existing:
        return {'error': 'Ya apostaste en esta apuesta'}

    wager = {
        'bet_id': bet_id,
        'user_id': user_id,
        'username': username,
        'option': option,
        'amount': amount,
        'timestamp': datetime.datetime.utcnow()
    }
    wagers_col.insert_one(wager)

    # Update bet stats + live feed
    live_entry = {
        'username': username,
        'option': option,
        'amount': amount,
        'timestamp': datetime.datetime.utcnow().isoformat()
    }
    bets_col.update_one(
        {'_id': ObjectId(bet_id)},
        {
            '$inc': {'total_pool': amount, 'wager_count': 1},
            '$push': {'live_participants': {'$each': [live_entry], '$slice': -20}}
        }
    )
    return {'ok': True}


def resolve_bet(bet_id, winning_option):
    bets_col.update_one(
        {'_id': ObjectId(bet_id)},
        {'$set': {'status': 'resolved', 'winning_option': winning_option, 'live_participants': []}}
    )

    # Get all wagers
    all_wagers = list(wagers_col.find({'bet_id': bet_id}))
    winning_wagers = [w for w in all_wagers if w['option'] == winning_option]
    total_pool = sum(w['amount'] for w in all_wagers)
    winning_pool = sum(w['amount'] for w in winning_wagers)

    winners = []
    for w in all_wagers:
        user = get_user_by_id(w['user_id'])
        if not user:
            continue
        if w['option'] == winning_option and winning_pool > 0:
            payout = int((w['amount'] / winning_pool) * total_pool)
            update_user_points(w['user_id'], payout)
            winners.append({
                'username': w['username'],
                'email': user['email'],
                'payout': payout,
                'won': True
            })
        else:
            winners.append({
                'username': w['username'],
                'email': user['email'],
                'payout': 0,
                'won': False
            })

    # Mark wagers as resolved
    wagers_col.update_many({'bet_id': bet_id}, {'$set': {'resolved': True, 'winning_option': winning_option}})
    return winners


def get_user_wagers(user_id):
    wagers = list(wagers_col.find({'user_id': user_id}).sort('timestamp', DESCENDING).limit(50))
    result = []
    for w in wagers:
        bet = get_bet_by_id(w['bet_id'])
        result.append({
            'bet_title': bet['title'] if bet else 'Apuesta eliminada',
            'option': w['option'],
            'amount': w['amount'],
            'timestamp': w['timestamp'].isoformat(),
            'status': bet['status'] if bet else 'unknown',
            'winning_option': bet.get('winning_option') if bet else None,
            'won': w['option'] == bet.get('winning_option') if bet and bet.get('winning_option') else None
        })
    return result

# ─── Groups ─────────────────────────────────────────────────────────────────────

def _gen_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def create_group(creator_id, creator_username, name, description):
    code = _gen_invite_code()
    while groups_col.find_one({'invite_code': code}):
        code = _gen_invite_code()
    group = {
        'name': name,
        'description': description,
        'created_by': creator_id,
        'created_by_username': creator_username,
        'invite_code': code,
        'members': [{'user_id': creator_id, 'username': creator_username}],
        'created_at': datetime.datetime.utcnow()
    }
    result = groups_col.insert_one(group)
    group['_id'] = result.inserted_id
    return group


def get_group_by_id(group_id):
    try:
        return groups_col.find_one({'_id': ObjectId(group_id)})
    except Exception:
        return None


def get_group_by_invite_code(code):
    return groups_col.find_one({'invite_code': code.upper()})


def get_user_groups(user_id):
    return list(groups_col.find({'members.user_id': user_id}))


def add_member_to_group(group_id, user_id, username):
    group = get_group_by_id(group_id)
    if not group:
        return {'error': 'Grupo no encontrado'}
    if any(m['user_id'] == user_id for m in group.get('members', [])):
        return {'error': 'Ya eres miembro de este grupo'}
    groups_col.update_one(
        {'_id': ObjectId(group_id)},
        {'$push': {'members': {'user_id': user_id, 'username': username}}}
    )
    return {'ok': True}


def get_group_bets(group_id):
    return list(bets_col.find({'group_id': ObjectId(group_id)}).sort('created_at', DESCENDING))

# ─── Leaderboard ────────────────────────────────────────────────────────────────

def get_leaderboard(limit=5):
    return list(users_col.find({}, {'username': 1, 'points': 1}).sort('points', DESCENDING).limit(limit))