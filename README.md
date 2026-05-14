# TibioMx 🎲

Plataforma de apuestas cotidianas universitarias con CuckostaPoints — la moneda virtual del campus.

---

## ¿Qué es TibioMx?

TibioMx permite a estudiantes crear y participar en apuestas del día a día universitario: si el profe llega tarde, si hay examen sorpresa, o cualquier evento cotidiano. Todo con puntos virtuales (CuckostaPoints), sin dinero real de por medio.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Python · Flask · Flask-Session |
| Base de datos | MongoDB Atlas (pymongo) |
| Auth | bcrypt |
| Frontend | Jinja2 · HTML/CSS vanilla |
| Deploy | Gunicorn |

---

## Instalación

### Requisitos

- Python 3.10+
- Cuenta en MongoDB Atlas (o URI de conexión propia)

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/tibiomx.git
cd tibiomx

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar la URI de MongoDB en db.py
# Edita la variable MONGO_URI con tu cadena de conexión

# 5. Correr la app
python app.py
```

La app corre en `http://localhost:5000` por defecto.

### Para producción

```bash
gunicorn app:app --bind 0.0.0.0:8000
```

---

## Estructura del proyecto

```
tibiomx/
├── app.py            # Rutas y lógica de Flask
├── db.py             # Modelos y operaciones con MongoDB
├── requirements.txt
├── style.css         # Estilos globales (dark theme)
├── base.html         # Layout base con sidebar
├── login.html
├── register.html
├── inicio.html       # Dashboard principal
├── apuestas.html     # Crear y participar en apuestas
├── grupos.html       # Grupos privados
├── historial.html    # Historial de jugadas del usuario
├── leaderboard.html  # Top 5 por puntos
├── recompensas.html  # Bono diario y anuncios en video
└── Admin.html        # Panel de administración
```

---

## Funcionalidades

### Usuarios
- Registro e inicio de sesión con contraseña hasheada (bcrypt)
- Bono diario de **+100 pts** al iniciar sesión (una vez cada 24 h)
- Ver y ganar puntos viendo anuncios en video (una vez por hora)

### Apuestas
- Crear apuestas con 2–4 opciones y fecha de cierre
- Costo de creación: **100 CuckostaPoints**
- No puedes apostar en tus propias apuestas
- El creador (o un admin) resuelve la apuesta eligiendo la opción ganadora
- Pago proporcional: `pago = (tu apuesta / pool ganadores) × pool total`
- Feed en vivo con las últimas jugadas de cada apuesta

### Grupos
- Crear grupos privados con código de invitación de 6 caracteres
- Unirse con código
- Las apuestas pueden ser públicas o restringidas a un grupo

### Leaderboard
- Top 5 usuarios con más CuckostaPoints

### Panel de administración (`/admin`)
- Gestión de usuarios: editar puntos, dar/quitar rol admin, eliminar
- Gestión de apuestas: resolver o eliminar cualquier apuesta
- Gestión de videos de anuncios: agregar, activar/desactivar, eliminar

---

## Cuenta admin por defecto

| Campo | Valor |
|-------|-------|
| Usuario | `admin` |
| Email | `admin@tibiomx.com` |
| Contraseña | `Admin1234!` |

> ⚠️ Cambia la contraseña antes de desplegar en producción. Edita `ADMIN_PASSWORD` en `db.py`.

---

## Variables a configurar en `db.py`

```python
MONGO_URI = 'tu_uri_de_mongodb_atlas'
ADMIN_PASSWORD = 'nueva_contraseña_segura'
BET_CREATION_COST = 100  # Costo en pts para crear una apuesta
```

---

## Colecciones en MongoDB

| Colección | Descripción |
|-----------|-------------|
| `users` | Usuarios registrados |
| `bets` | Apuestas creadas |
| `wagers` | Jugadas individuales |
| `groups` | Grupos privados |
| `site_config` | Configuración global (videos de anuncios) |

---

## Licencia

Proyecto universitario — uso educativo y personal.