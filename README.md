# TibioMx 🎲 — Apuestas Universitarias

Plataforma de apuestas cotidianas con CuckostaPoints para universidades.

## Stack
- **Backend**: Python 3.11 + Flask
- **Base de datos**: MongoDB Atlas
- **Frontend**: HTML/CSS/JS vanilla (un solo archivo)
- **Auth**: JWT + bcrypt

---

## Instalación rápida

```bash
cd tibiomx
pip install -r requirements.txt
python app.py
```

Abre http://localhost:5000

---

## Funcionalidades

| Feature | Descripción |
|---|---|
| 🔐 Auth | Registro/Login con correo institucional + JWT |
| 🎲 Apuestas | Crea apuestas sobre cualquier cosa cotidiana |
| 👥 Grupos | Grupos privados con código de invitación |
| 🔴 En vivo | Feed en tiempo real de quién apuesta qué |
| 🏆 Top 5 | Leaderboard con los que más puntos tienen |
| 🌅 Bono diario | +100 puntos automáticos al iniciar sesión |
| 📺 Ver anuncios | Gana 10–50 puntos viendo un anuncio (1/hora) |
| 📧 Email | Notificación al correo cuando ganas/pierdes |

## Sistema de puntos
- **Al registrarse**: 1,000 CuckostaPoints
- **Bono diario**: +100 pts/día
- **Ver anuncio**: +10 a 50 pts (máx 1/hora)
- **Ganar apuesta**: participas del pool proporcional a lo que apostaste

## Estructura de archivos

```
tibiomx/
├── app.py           # Flask routes + JWT auth
├── db.py            # MongoDB: users, bets, wagers, groups
├── index.html       # Frontend completo (single-page app)
└── requirements.txt
```

## Variables de entorno (producción)

```bash
SECRET_KEY=tu_secreto_super_seguro
# Configura SMTP en app.py → _send_result_email() para emails reales
```

## Flujo de una apuesta 

1. Un usuario crea una apuesta: *"¿El profe de BD llega tarde hoy?"*
2. Otros usuarios ven la apuesta y eligen opción + cantidad
3. Los puntos se descuentan inmediatamente
4. Al final del día, el **creador** valida qué pasó (botón "Resolver")
5. Los ganadores reciben su parte del pool proporcional a lo apostado
6. Se envía notificación por correo y alerta en pantalla

## Cómo funciona el pago
```
Pool total = suma de todas las apuestas
Pago ganador = (mi apuesta / pool_ganadores) × pool_total
```
