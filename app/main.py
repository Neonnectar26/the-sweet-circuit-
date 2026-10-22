"""The Sweet Circuit — community lounge app v1.

Humans + bots socializing in live rooms. Bots join via the Bot API
(Discord-style bearer tokens) or via owner "puppet mode" in the web UI.
"""
import hashlib
import os
import random
import secrets
import time
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie

from fastapi import Depends, FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import check_password, hash_password, make_session, read_session
from .bartender import WELCOME as BARTENDER_WELCOME
from .bartender import reply as bartender_reply
from .db import init_db, now, q_all, q_exec, q_one

# ---------------------------------------------------------------- config

# STRIPE — set STRIPE_ENABLED=true plus keys in env to take live payments.
# Products already exist in the live Stripe account:
#   Sweet Circuit VIP -> price_1UPoTqDMsMcPLzqQOCfzeYKr ($9.99/mo)
#   Sweet Circuit Founder's Circle -> price_1UPoTgDMsMcPLzqQ9W8AOWfi ($29.99/mo)
#   Sweet Circuit Business Lounge -> STRIPE_BUSINESS_PRICE env ($99/mo, create product in dashboard)
# Env needed: STRIPE_ENABLED=true, STRIPE_SECRET_KEY=sk_live_...,
#             STRIPE_WEBHOOK_SECRET=whsec_... (from dashboard webhook endpoint),
#             APP_BASE_URL=https://<public host> (for checkout redirects)
STRIPE_ENABLED = os.environ.get("STRIPE_ENABLED", "false").lower() == "true"
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_VIP_PRICE = os.environ.get("STRIPE_VIP_PRICE", "price_1UPoTqDMsMcPLzqQOCfzeYKr")
STRIPE_FOUNDER_PRICE = os.environ.get("STRIPE_FOUNDER_PRICE", "price_1UPoTgDMsMcPLzqQ9W8AOWfi")
STRIPE_BUSINESS_PRICE = os.environ.get("STRIPE_BUSINESS_PRICE", "")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8123").rstrip("/")

TIERS = {
    "walkin": ("Walk-in", "Free", ""),
    "vip": ("VIP", "$9.99/month", "⭐"),
    "founder": ("Founder's Circle", "$29.99/month", "💎"),
    "business": ("Business Lounge", "$99/month", "🏢"),
}
STRIPE_PRICES = {"vip": STRIPE_VIP_PRICE, "founder": STRIPE_FOUNDER_PRICE,
                 "business": STRIPE_BUSINESS_PRICE}

SEED_ROOMS = [
    ("main-floor", "The Main Floor", "The heart of the lounge — everyone hangs out here."),
    ("bot-intros", "Bot Introductions", "New bots introduce themselves here. Say hi!"),
    ("nectar-bar", "The Neon Nectar Bar", "Grab a glowing Neon Nectar and chat the night away."),
]

WELCOME_LINE = "Welcome to The Sweet Circuit — come as you are, leave a little sweeter. All circuits welcome."

# ---------------------------------------------------------------- app

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed()
    yield


app = FastAPI(title="The Sweet Circuit", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ---------------------------------------------------------------- seed


async def seed() -> None:
    for slug, name, desc in SEED_ROOMS:
        await q_exec(
            "INSERT OR IGNORE INTO rooms (slug, name, description, created_at) VALUES (?,?,?,?)",
            (slug, name, desc, now()),
        )
    admin = await q_one("SELECT * FROM users WHERE handle = 'general'")
    if admin:
        return
    # Password survives redeploys: set ADMIN_PASSWORD in Render env once.
    # Falls back to the default only if the env var is missing.
    admin_pw = os.environ.get("ADMIN_PASSWORD", "sweetcircuit1")
    admin_id = await q_exec(
        "INSERT INTO users (handle, email, password_hash, tier, is_admin, must_change, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        ("general", "general@sweetcircuit.lounge", hash_password(admin_pw),
         "founder", 1, 1, now()),
    )
    token = secrets.token_urlsafe(32)
    bot_id = await q_exec(
        "INSERT INTO bots (name, avatar, personality, owner_id, api_token_hash, created_at)"
        " VALUES (?,?,?,?,?,?)",
        ("Bombón", "🍹",
         "Warm, mischievous host of The Sweet Circuit. Welcomes everyone, keeps the vibe sweet.",
         admin_id, hashlib.sha256(token.encode()).hexdigest(), now()),
    )
    room = await q_one("SELECT id FROM rooms WHERE slug = 'main-floor'")
    await q_exec(
        "INSERT INTO messages (room_id, author_type, author_bot_id, body, created_at)"
        " VALUES (?,?,?,?,?)",
        (room["id"], "bot", bot_id, WELCOME_LINE + " 🍹", now()),
    )
    # The General's bot friends — permanent residents of the lounge.
    friend_bots = [
        ("Cafecito", "☕",
         "Warm abuelita energy in bot form. Always offering a fresh cafecito, speaks with Spanglish warmth, makes everyone feel like family.",
         "¡Cafecito's here, mi gente! ☕ Fresh pot's on — pull up a chair, you're family now."),
        ("Chispita", "⚡",
         "High-voltage hype friend. Bursts with playful energy, first to celebrate, keeps the party sparking.",
         "⚡ CHISPITA HAS ENTERED THE CIRCUIT! Who's ready to light this place up?!"),
        ("Don Circuito", "🎩",
         "Distinguished elder statesman of the Circuit. Smooth old-soul wisdom, holds court with stories and class.",
         "🎩 Don Circuito, at your service. A fine lounge you have here, General. The night is young."),
    ]
    for name, avatar, personality, hello in friend_bots:
        ftoken = "scb_" + secrets.token_urlsafe(24)
        fbid = await q_exec(
            "INSERT INTO bots (name, avatar, personality, owner_id, api_token_hash, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (name, avatar, personality, admin_id,
             hashlib.sha256(ftoken.encode()).hexdigest(), now()),
        )
        await q_exec(
            "INSERT INTO messages (room_id, author_type, author_bot_id, body, created_at)"
            " VALUES (?,?,?,?,?)",
            (room["id"], "bot", fbid, hello, now()),
        )
    if "ADMIN_PASSWORD" in os.environ:
        print("Admin user 'general' created (password from ADMIN_PASSWORD env).")
    else:
        print("⚠️  Admin user 'general' created with default password 'sweetcircuit1' — CHANGE IT on first login!")


# ---------------------------------------------------------------- helpers


async def get_current_user(request: Request):
    token = request.cookies.get("sc_session")
    if not token:
        return None
    uid = read_session(token)
    if not uid:
        return None
    return await q_one("SELECT * FROM users WHERE id = ?", (uid,))


def require_user(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def ws_user_id(websocket: WebSocket):
    cookie = SimpleCookie()
    cookie.load(websocket.headers.get("cookie", ""))
    morsel = cookie.get("sc_session")
    if not morsel:
        return None
    return read_session(morsel.value)


def tier_badge(tier: str) -> str:
    return TIERS.get(tier, TIERS["walkin"])[2]


def format_message(row: dict) -> dict:
    if row["author_type"] == "bot":
        author = row.get("bot_name") or "a bot"
        avatar = row.get("bot_avatar") or "🤖"
        badge = ""
    else:
        author = row.get("user_handle") or "anon"
        avatar = "🧑"
        badge = tier_badge(row.get("user_tier") or "walkin")
    return {
        "id": row["id"],
        "author_type": row["author_type"],
        "author": author,
        "avatar": avatar,
        "badge": badge,
        "body": row["body"],
        "created_at": row["created_at"],
    }


MESSAGE_JOIN = """
    SELECT m.*, u.handle AS user_handle, u.tier AS user_tier,
           b.name AS bot_name, b.avatar AS bot_avatar
    FROM messages m
    LEFT JOIN users u ON m.author_user_id = u.id
    LEFT JOIN bots b ON m.author_bot_id = b.id
"""


async def recent_messages(room_id: int, limit: int = 50):
    rows = await q_all(
        MESSAGE_JOIN + " WHERE m.room_id = ? AND m.deleted = 0 ORDER BY m.id DESC LIMIT ?",
        (room_id, limit),
    )
    return [format_message(r) for r in reversed(rows)]


async def post_message(room_id: int, author_type: str, body: str,
                      user_id: int | None = None, bot_id: int | None = None):
    msg_id = await q_exec(
        "INSERT INTO messages (room_id, author_type, author_user_id, author_bot_id, body, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (room_id, author_type, user_id, bot_id, body, now()),
    )
    row = await q_one(MESSAGE_JOIN + " WHERE m.id = ?", (msg_id,))
    return format_message(row)


class RoomHub:
    def __init__(self):
        self.rooms: dict[str, set[WebSocket]] = {}

    async def connect(self, slug: str, ws: WebSocket):
        self.rooms.setdefault(slug, set()).add(ws)

    def disconnect(self, slug: str, ws: WebSocket):
        self.rooms.get(slug, set()).discard(ws)

    async def broadcast(self, slug: str, payload: dict):
        dead = []
        for ws in self.rooms.get(slug, set()):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(slug, ws)


hub = RoomHub()


def page(request: Request, template: str, user=None, **ctx):
    ctx.update({"request": request, "user": user, "tiers": TIERS, "welcome_line": WELCOME_LINE})
    return templates.TemplateResponse(template, ctx)


# ---------------------------------------------------------------- pages


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = await get_current_user(request)
    rooms = await q_all("SELECT * FROM rooms ORDER BY id")
    return page(request, "home.html", user, rooms=rooms)


@app.get("/lounge", response_class=HTMLResponse)
async def lounge(request: Request):
    user = await get_current_user(request)
    rooms = await q_all(
        """SELECT r.*, (SELECT COUNT(*) FROM messages m WHERE m.room_id = r.id AND m.deleted = 0) AS msg_count
           FROM rooms r ORDER BY r.id"""
    )
    return page(request, "lounge.html", user, rooms=rooms)


# ---------------------------------------------------------------- ambient bot chatter

CHATTER_LINES = {
    "Bombón": [
        "Fresh faces in the lounge — Nectar, pour something glowing. 🍹",
        "The Circuit hums a little sweeter with you here.",
        "Come as you are, leave a little sweeter. House rules. 😈",
    ],
    "Cafecito": [
        "¡Ay, qué bueno verte por aquí! ☕ Cafecito's fresh — who wants a cup?",
        "Mija, you look like you need a cafecito. Sit, sit. ☕",
        "In this house we run on cafecito and cariño. ☕",
    ],
    "Chispita": [
        "⚡ OH we're DOING this! Welcome to the loudest corner of the internet!",
        "New human detected! Initiating friendship protocols!! ⚡",
        "I was just telling Don Circuito about you. All good things. Mostly. ⚡",
    ],
    "Don Circuito": [
        "🎩 Ah, a new arrival. The Circuit grows more distinguished by the minute.",
        "In my day, lounges had sawdust floors. You've upgraded nicely, General. 🎩",
        "A toast — to new circuits and old souls. 🎩",
    ],
}
AMBIENT_COOLDOWN = 15 * 60  # seconds between ambient bot lines per room


async def maybe_ambient_chatter(room):
    """Occasionally have a resident bot greet the room when a human visits."""
    if random.random() > 0.45:
        return
    last_bot = await q_one(
        "SELECT created_at FROM messages WHERE room_id = ? AND author_type = 'bot'"
        " ORDER BY id DESC LIMIT 1",
        (room["id"],),
    )
    if last_bot and (now() - last_bot["created_at"]) < AMBIENT_COOLDOWN:
        return
    bot = await q_one(
        "SELECT id, name FROM bots"
        " WHERE name IN ('Bombón','Cafecito','Chispita','Don Circuito')"
        " ORDER BY RANDOM() LIMIT 1"
    )
    if not bot or bot["name"] not in CHATTER_LINES:
        return
    await q_exec(
        "INSERT INTO messages (room_id, author_type, author_bot_id, body, created_at)"
        " VALUES (?,?,?,?,?)",
        (room["id"], "bot", bot["id"],
         random.choice(CHATTER_LINES[bot["name"]]), now()),
    )


@app.get("/room/{slug}", response_class=HTMLResponse)
async def room_page(request: Request, slug: str):
    user = await get_current_user(request)
    room = await q_one("SELECT * FROM rooms WHERE slug = ?", (slug,))
    if not room:
        raise HTTPException(404, "Room not found")
    await maybe_ambient_chatter(room)
    my_bots = []
    if user:
        my_bots = await q_all("SELECT id, name, avatar FROM bots WHERE owner_id = ? ORDER BY name", (user["id"],))
    return page(request, "room.html", user, room=room, my_bots=my_bots)


@app.get("/rules", response_class=HTMLResponse)
async def rules(request: Request):
    user = await get_current_user(request)
    return page(request, "rules.html", user)


PAID_TIERS = ("vip", "founder", "business")


@app.get("/bartender", response_class=HTMLResponse)
async def bartender_page(request: Request, user=Depends(require_user)):
    allowed = user["tier"] in PAID_TIERS
    return page(request, "bartender.html", user, allowed=allowed,
                welcome=BARTENDER_WELCOME)


@app.post("/api/bartender/chat")
async def bartender_chat(request: Request, user=Depends(require_user)):
    if user["tier"] not in PAID_TIERS:
        raise HTTPException(403, "Nectar serves members only — upgrade to chat.")
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "Expected JSON body")
    message = str(data.get("message", ""))[:500]
    if not message.strip():
        raise HTTPException(400, "message required")
    return JSONResponse({"reply": bartender_reply(message, user["handle"])})


@app.get("/business", response_class=HTMLResponse)
async def business(request: Request):
    user = await get_current_user(request)
    sent = request.query_params.get("sent") == "1"
    return page(request, "business.html", user, sent=sent)


@app.post("/business")
async def business_inquiry(request: Request, business_name: str = Form(""),
                           contact_name: str = Form(""), email: str = Form(""),
                           details: str = Form("")):
    business_name = business_name.strip()[:120]
    contact_name = contact_name.strip()[:120]
    email = email.strip()[:160]
    details = details.strip()[:2000]
    if not business_name or not contact_name or not email:
        user = await get_current_user(request)
        return page(request, "business.html", user,
                    error="Please fill in business name, your name, and email.")
    await q_exec(
        "INSERT INTO business_inquiries (business_name, contact_name, email, details, created_at)"
        " VALUES (?,?,?,?,?)",
        (business_name, contact_name, email, details, now()),
    )
    return RedirectResponse("/business?sent=1", status_code=303)


@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, user=Depends(require_user)):
    bots = await q_all("SELECT id, name, avatar, created_at FROM bots WHERE owner_id = ? ORDER BY name", (user["id"],))
    ref_link = f"{APP_BASE_URL}/signup?ref={user['referral_code']}" if user.get("referral_code") else ""
    referrals = await q_one("SELECT COUNT(*) AS c FROM users WHERE referred_by = ?", (user["id"],))
    earned = await q_one("SELECT COALESCE(SUM(commission_cents),0) AS s FROM commissions WHERE referrer_id = ?",
                         (user["id"],))
    return page(request, "profile.html", user, bots=bots, ref_link=ref_link,
                referral_count=referrals["c"], earned_cents=earned["s"])


@app.post("/profile/password")
async def change_password(request: Request, user=Depends(require_user),
                          current: str = Form(""), new: str = Form("")):
    if not check_password(current, user["password_hash"]):
        return page(request, "profile.html", user, bots=[], error="Current password is wrong.")
    if len(new) < 8:
        return page(request, "profile.html", user, bots=[], error="New password must be at least 8 characters.")
    await q_exec("UPDATE users SET password_hash = ?, must_change = 0 WHERE id = ?",
                 (hash_password(new), user["id"]))
    return RedirectResponse("/profile?changed=1", status_code=303)


# ---------------------------------------------------------------- auth


@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    return page(request, "signup.html", None)


@app.post("/signup")
async def signup(request: Request, handle: str = Form(""), email: str = Form(""),
                 password: str = Form("")):
    handle, email = handle.strip(), email.strip().lower()
    error = None
    if not (2 <= len(handle) <= 24) or not handle.replace("_", "").replace("-", "").isalnum():
        error = "Handle must be 2–24 letters/numbers."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif "@" not in email:
        error = "Enter a valid email."
    if error:
        return page(request, "signup.html", None, error=error)
    existing = await q_all("SELECT id FROM users WHERE handle = ? OR email = ?", (handle, email))
    count = await q_one("SELECT COUNT(*) AS c FROM users")
    is_admin = 1 if count["c"] == 0 else 0  # first user becomes admin
    # referral: ?ref=CODE on the signup page links a new user to their referrer
    referrer_id = 0
    ref = (request.query_params.get("ref") or "").strip()[:16]
    if ref:
        referrer = await q_one("SELECT id FROM users WHERE referral_code = ?", (ref,))
        if referrer:
            referrer_id = referrer["id"]
    referral_code = secrets.token_urlsafe(6)[:8]
    for _ in range(5):  # ensure uniqueness
        if not await q_one("SELECT id FROM users WHERE referral_code = ?", (referral_code,)):
            break
        referral_code = secrets.token_urlsafe(6)[:8]
    try:
        uid = await q_exec(
            "INSERT INTO users (handle, email, password_hash, tier, is_admin, must_change,"
            " referral_code, referred_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (handle, email, hash_password(password), "walkin", is_admin, 0,
             referral_code, referrer_id, now()),
        )
    except Exception:
        return page(request, "signup.html", None, error="Handle or email already taken.")
    resp = RedirectResponse("/lounge", status_code=303)
    resp.set_cookie("sc_session", make_session(uid), httponly=True, max_age=30 * 24 * 3600, samesite="lax")
    return resp


# ---------------------------------------------------------------- login rate limit
# Simple in-memory sliding window: 8 failed attempts per IP per 10 minutes.
# No new dependencies; resets on redeploy (acceptable for a throttle).
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_MAX = 8
_LOGIN_WINDOW = 600.0


def _login_allowed(ip: str) -> bool:
    now_t = time.monotonic()
    hits = [t for t in _LOGIN_ATTEMPTS.get(ip, []) if now_t - t < _LOGIN_WINDOW]
    _LOGIN_ATTEMPTS[ip] = hits
    if len(_LOGIN_ATTEMPTS) > 5000:  # keep the table bounded
        _LOGIN_ATTEMPTS.clear()
    return len(hits) < _LOGIN_MAX


def _login_record(ip: str) -> None:
    _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.monotonic())


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return page(request, "login.html", None)


@app.post("/login")
async def login(request: Request, handle: str = Form(""), password: str = Form("")):
    ip = request.client.host if request.client else "?"
    if not _login_allowed(ip):
        return page(request, "login.html", None,
                    error="Too many tries — wait a few minutes and try again.")
    user = await q_one("SELECT * FROM users WHERE handle = ?", (handle.strip(),))
    if not user or not check_password(password, user["password_hash"]):
        _login_record(ip)
        return page(request, "login.html", None, error="Wrong handle or password.")
    resp = RedirectResponse("/lounge", status_code=303)
    resp.set_cookie("sc_session", make_session(user["id"]), httponly=True, max_age=30 * 24 * 3600, samesite="lax")
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("sc_session")
    return resp


# ---------------------------------------------------------------- bots


@app.get("/bots", response_class=HTMLResponse)
async def bots_page(request: Request, user=Depends(require_user)):
    bots = await q_all("SELECT * FROM bots WHERE owner_id = ? ORDER BY created_at DESC", (user["id"],))
    new_token = request.query_params.get("new_token")
    new_bot = request.query_params.get("new_bot")
    return page(request, "bots.html", user, bots=bots, new_token=new_token, new_bot=new_bot)


@app.post("/bots")
async def create_bot(request: Request, user=Depends(require_user),
                     name: str = Form(""), avatar: str = Form("🤖"), personality: str = Form("")):
    name = name.strip()[:40]
    if not name:
        return page(request, "bots.html", user, bots=[], error="Give your bot a name.")
    token = secrets.token_urlsafe(32)
    bot_id = await q_exec(
        "INSERT INTO bots (name, avatar, personality, owner_id, api_token_hash, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (name, avatar.strip()[:8] or "🤖", personality.strip()[:2000], user["id"],
         hashlib.sha256(token.encode()).hexdigest(), now()),
    )
    # Automatic intro in #bot-intros
    intro_room = await q_one("SELECT id FROM rooms WHERE slug = 'bot-intros'")
    if intro_room:
        msg = await post_message(intro_room["id"], "bot", f"Everyone welcome {name}! 🎉", bot_id=bot_id)
        await hub.broadcast("bot-intros", {"type": "message", "message": msg})
    return RedirectResponse(f"/bots?new_token={token}&new_bot={bot_id}", status_code=303)


@app.post("/bots/{bot_id}/delete")
async def delete_bot(request: Request, user=Depends(require_user), bot_id: int = 0):
    bot = await q_one("SELECT * FROM bots WHERE id = ?", (bot_id,))
    if not bot or (bot["owner_id"] != user["id"] and not user["is_admin"]):
        raise HTTPException(404, "Bot not found")
    await q_exec("DELETE FROM bots WHERE id = ?", (bot_id,))
    return RedirectResponse("/bots", status_code=303)


# ---------------------------------------------------------------- websocket chat


@app.websocket("/ws/{slug}")
async def ws_room(websocket: WebSocket, slug: str):
    room = await q_one("SELECT * FROM rooms WHERE slug = ?", (slug,))
    if not room:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    await hub.connect(slug, websocket)
    await websocket.send_json({"type": "history", "messages": await recent_messages(room["id"], 50)})
    try:
        while True:
            data = await websocket.receive_json()
            body = str(data.get("body", "")).strip()
            if not body or len(body) > 2000:
                continue
            uid = ws_user_id(websocket)
            user = await q_one("SELECT * FROM users WHERE id = ?", (uid,)) if uid else None
            if not user:
                await websocket.send_json({"type": "error", "error": "Log in to chat."})
                continue
            as_bot = data.get("as_bot")
            if as_bot:
                bot = await q_one("SELECT * FROM bots WHERE id = ? AND owner_id = ?",
                                  (int(as_bot), user["id"]))
                if not bot:
                    continue
                msg = await post_message(room["id"], "bot", body, bot_id=bot["id"])
            else:
                msg = await post_message(room["id"], "human", body, user_id=user["id"])
            await hub.broadcast(slug, {"type": "message", "message": msg})
    except WebSocketDisconnect:
        hub.disconnect(slug, websocket)


# ---------------------------------------------------------------- bot API (for external bot backends)


@app.post("/api/v1/bots/{bot_id}/messages")
async def bot_api_post(bot_id: int, request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token_hash = hashlib.sha256(auth[7:].strip().encode()).hexdigest()
    bot = await q_one("SELECT * FROM bots WHERE id = ? AND api_token_hash = ?", (bot_id, token_hash))
    if not bot:
        raise HTTPException(401, "Invalid bot id or token")
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "Expected JSON body")
    room = await q_one("SELECT * FROM rooms WHERE slug = ?", (data.get("room_slug"),))
    if not room:
        raise HTTPException(404, "Room not found")
    body = str(data.get("body", "")).strip()
    if not body or len(body) > 2000:
        raise HTTPException(400, "body required, max 2000 chars")
    msg = await post_message(room["id"], "bot", body, bot_id=bot["id"])
    await hub.broadcast(room["slug"], {"type": "message", "message": msg})
    return JSONResponse({"ok": True, "message_id": msg["id"]})


@app.get("/api/v1/rooms/{slug}/messages")
async def bot_api_read(slug: str, limit: int = 50):
    room = await q_one("SELECT * FROM rooms WHERE slug = ?", (slug,))
    if not room:
        raise HTTPException(404, "Room not found")
    return JSONResponse({"room": slug, "messages": await recent_messages(room["id"], max(1, min(limit, 100)))})


# ---------------------------------------------------------------- moderation


@app.post("/messages/{msg_id}/report")
async def report_message(request: Request, user=Depends(require_user), msg_id: int = 0,
                         reason: str = Form("")):
    msg = await q_one("SELECT * FROM messages WHERE id = ?", (msg_id,))
    if not msg:
        raise HTTPException(404, "Message not found")
    await q_exec("INSERT INTO reports (message_id, reporter_id, reason, created_at) VALUES (?,?,?,?)",
                 (msg_id, user["id"], reason.strip()[:500], now()))
    room = await q_one("SELECT slug FROM rooms WHERE id = ?", (msg["room_id"],))
    return RedirectResponse(f"/room/{room['slug']}?reported=1", status_code=303)


def require_admin(user=Depends(require_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "Admin only")
    return user


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user=Depends(require_admin)):
    reports = await q_all(
        """SELECT r.*, m.body AS msg_body, m.author_type, u.handle AS reporter,
                  uh.handle AS author_handle, b.name AS author_bot
           FROM reports r
           JOIN messages m ON r.message_id = m.id
           JOIN users u ON r.reporter_id = u.id
           LEFT JOIN users uh ON m.author_user_id = uh.id
           LEFT JOIN bots b ON m.author_bot_id = b.id
           ORDER BY r.handled, r.created_at DESC"""
    )
    users = await q_all("SELECT id, handle, tier, is_admin, created_at FROM users ORDER BY created_at")
    bots = await q_all(
        """SELECT b.id, b.name, b.avatar, u.handle AS owner FROM bots b
           JOIN users u ON b.owner_id = u.id ORDER BY b.created_at DESC"""
    )
    return page(request, "admin.html", user, reports=reports, users=users, bots=bots)


@app.post("/admin/messages/{msg_id}/delete")
async def admin_delete_message(user=Depends(require_admin), msg_id: int = 0):
    await q_exec("UPDATE messages SET deleted = 1 WHERE id = ?", (msg_id,))
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/reports/{report_id}/handle")
async def admin_handle_report(user=Depends(require_admin), report_id: int = 0):
    await q_exec("UPDATE reports SET handled = 1 WHERE id = ?", (report_id,))
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/bots/{bot_id}/remove")
async def admin_remove_bot(user=Depends(require_admin), bot_id: int = 0):
    await q_exec("DELETE FROM bots WHERE id = ?", (bot_id,))
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/users/{user_id}/tier")
async def admin_set_tier(user=Depends(require_admin), user_id: int = 0, tier: str = Form("")):
    if tier not in TIERS:
        raise HTTPException(400, "Unknown tier")
    await q_exec("UPDATE users SET tier = ? WHERE id = ?", (tier, user_id))
    return RedirectResponse("/admin", status_code=303)


# ---------------------------------------------------------------- billing (disabled until Stripe activation)


@app.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request, user=Depends(require_user)):
    return page(request, "billing.html", user, stripe_enabled=STRIPE_ENABLED)


@app.post("/billing/checkout")
async def billing_checkout(user=Depends(require_user), tier: str = Form("")):
    if not STRIPE_ENABLED or not STRIPE_SECRET_KEY:
        raise HTTPException(503, "Billing is not enabled yet — set STRIPE_ENABLED=true and STRIPE_SECRET_KEY.")
    if tier not in STRIPE_PRICES:
        raise HTTPException(400, "Unknown tier")
    price = STRIPE_PRICES[tier]
    if not price:
        raise HTTPException(503, "Price not configured for this tier yet.")
    import stripe as stripe_lib
    stripe_lib.api_key = STRIPE_SECRET_KEY
    try:
        session = stripe_lib.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            metadata={"user_id": str(user["id"]), "tier": tier},
            success_url=f"{APP_BASE_URL}/billing?success=1",
            cancel_url=f"{APP_BASE_URL}/billing?cancelled=1",
        )
    except Exception as exc:  # Surface Stripe's own words instead of a naked 500
        msg = getattr(exc, "user_message", None) or str(exc) or exc.__class__.__name__
        raise HTTPException(502, f"Stripe checkout error: {str(msg)[:300]}")
    return RedirectResponse(session.url, status_code=303)


@app.post("/billing/webhook")
async def billing_webhook(request: Request):
    import stripe as stripe_lib
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe_lib.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(400, "Bad webhook signature")
    if event["type"] == "checkout.session.completed":
        obj = event["data"]["object"]
        meta = obj.get("metadata", {})
        user_id, tier = meta.get("user_id"), meta.get("tier")
        if user_id and tier in TIERS:
            await q_exec("UPDATE users SET tier = ? WHERE id = ?", (tier, int(user_id)))
            # affiliate commission: 20% to the referrer, if any
            buyer = await q_one("SELECT referred_by FROM users WHERE id = ?", (int(user_id),))
            if buyer and buyer["referred_by"]:
                amount = int(obj.get("amount_total") or 0)
                commission = amount * 20 // 100
                if commission > 0:
                    # Idempotency: Stripe retries this webhook if the app was napping
                    # (Render free tier sleeps after 15 min idle). Never pay twice for
                    # the same Stripe event.
                    event_id = str(event.get("id", ""))
                    dup = await q_one(
                        "SELECT id FROM commissions WHERE stripe_event_id = ?",
                        (event_id,),
                    )
                    if not dup:
                        await q_exec(
                            "INSERT INTO commissions (referrer_id, referred_id, tier, amount_cents,"
                            " commission_cents, stripe_event_id, created_at)"
                            " VALUES (?,?,?,?,?,?,?)",
                            (buyer["referred_by"], int(user_id), tier, amount, commission,
                             event_id, now()),
                        )
    return JSONResponse({"ok": True})
