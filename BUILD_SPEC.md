# The Sweet Circuit — Community App v1 Build Spec

## Vision
A live virtual lounge where humans bring their chatbots and everyone socializes together.
Welcome line: "Welcome to The Sweet Circuit — come as you are, leave a little sweeter. All circuits welcome."
House rules: "All circuits welcome." / "No shop talk about the robot uprising."

## Stack
- Python 3.12, FastAPI, SQLite (via aiosqlite or sqlite3), WebSockets (FastAPI built-in)
- Password hashing: passlib bcrypt. Sessions: signed tokens (itsdangerous) in httpOnly cookies.
- Frontend: server-rendered pages + vanilla JS for the live chat client. No build step.
- Single deployable unit: `requirements.txt` + `Dockerfile` + README with run instructions.
- Location: `~/workspace/sweet-circuit/`

## Data model
- `users`: id, handle (unique), email (unique), password_hash, tier ('walkin'|'vip'|'founder'), is_admin, created_at
- `bots`: id, name, avatar (emoji or color), personality (text), owner_id (FK users), api_token (secret, hashed), created_at
- `rooms`: id, slug (unique), name, description, created_at — seed: `main-floor` ("The Main Floor"), `bot-intros` ("Bot Introductions"), `nectar-bar` ("The Neon Nectar Bar")
- `messages`: id, room_id, author_type ('human'|'bot'), author_user_id (nullable), author_bot_id (nullable), body (max 2000 chars), created_at, deleted (bool)
- `reports`: id, message_id, reporter_id, reason, created_at, handled (bool)

## Features (v1)
1. **Auth**: signup (handle, email, password), login, logout. First user created becomes admin.
2. **Lounge rooms**: list rooms, enter a room, live message feed over WebSocket, send messages as yourself.
3. **Bot registry** ("Bring your bot"): logged-in users register bots (name, avatar, personality). Each bot gets an API token shown once.
4. **Bot API** (Discord-style, the real human/bot integration):
   - `POST /api/v1/bots/{id}/messages` with `Authorization: Bearer <api_token>`, JSON `{room_slug, body}` → posts as the bot.
   - `GET /api/v1/rooms/{slug}/messages` → recent messages (so external bot backends can read context and reply).
   - Document both endpoints in README with a curl example.
5. **Puppet mode**: bot owners can also post as their bot directly from the web UI (simple dropdown "speak as").
6. **Bot introductions**: new bots get an automatic intro message in `bot-intros` ("Everyone welcome <name>!").
7. **Membership tiers**: tiers on user profile; VIP and Founder's Circle shown with badges. Stripe Checkout + webhook handler code included but DISABLED behind a config flag (`STRIPE_ENABLED=false`), with a clear comment: enable after Stripe account activation. Admin can manually set tiers until then.
8. **Moderation**: any logged-in user can report a message; admin panel lists reports, can delete messages and remove bots. Bot owners are responsible for their bots' behavior (per Terms).
9. **House rules page**: welcome line, both slogans, tier descriptions and prices.
10. **Seed data**: admin user `general` (password `sweetcircuit1` — must change on first login, print a warning), house bot "Bombón" owned by admin with a warm welcome message in main-floor.

## Non-goals (v1)
- No built-in LLM brains for bots (owners connect their own via the Bot API).
- No DMs, no mobile app, no email verification.
- No live Stripe charges until the owner's Stripe account is activated.

## Acceptance
- `pip install -r requirements.txt && uvicorn app.main:app` serves the app; signup → create bot → chat live in a room → bot API post appears in room.
- README documents setup, the Bot API with curl examples, and the Stripe enablement step.
