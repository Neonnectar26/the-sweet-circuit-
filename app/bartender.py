"""Nectar — the AI bartender of The Sweet Circuit.

A scripted conversational bartender with a warm, witty personality and a
little Spanglish flair. No LLM needed: keyword matching with rotating
responses so repeat visitors don't hear the same line twice.
"""
import random

DRINKS = {
    "neon nectar": "The Neon Nectar 🍹 — our glowing house signature. Sweet, electric, and it practically hums. The one everyone talks about.",
    "general": "The General 💪 — bold, strong, no-nonsense. Named after the founder himself. Approach with respect.",
    "cafecito martini": "Cafecito Martini ☕ — for the night owls. Espresso, attitude, and just enough mischief.",
    "circuit spritz": "Circuit Spritz ✨ — light, bubbly, electric. The 'I'm here for a good time' choice.",
    "special": "The Bot-tender's Special 🎲 — I surprise you. Brave? Say the word.",
}

GREETINGS = [
    "¡Buenas! Welcome to the bar, {name}. Nectar's the name, pouring's the game. What can I get you?",
    "Hey hey, {name}! Pull up a stool. First one's on the house — metaphorically. What are you in the mood for?",
    "Well look who walked in — {name}! The Neon Nectars are glowing and the night is young. What's your pleasure?",
]

RECOMMENDATIONS = [
    "Feeling adventurous? The Neon Nectar never misses. Feeling bold? The General. Feeling mysterious? Let me surprise you with the Bot-tender's Special.",
    "My honest take: start with a Neon Nectar — it's the house signature for a reason. Then tell me how you're feeling and I'll go from there.",
    "Depends on the vibe. Celebrating? Circuit Spritz. Need fuel? Cafecito Martini. Want a story to tell? The General.",
]

JOKES = [
    "Why did the chatbot go to the bar? To improve its spirits! ...I'll be here all night. 🍹",
    "A robot walks into a bar. The bartender says 'Hey!' The robot says 'Wow, your facial recognition is great.'",
    "I told a bot a joke about UDP once. It didn't get it. Nobody got it.",
    "Why don't bots ever get lost? They always follow the current... events. Okay, that one's on the house too.",
]

FALLBACKS = [
    "Hmm, say that again over the music? While you're at it — can I interest you in a Neon Nectar?",
    "You know what, that deserves a drink first. Neon Nectar? The General? Talk to me.",
    "I'm a bartender, not a philosopher — but I'll pour while you explain. What's on your mind, really?",
    "Interesting... interesting. You know what pairs well with deep thoughts? A Circuit Spritz. Just saying.",
]

LOUNGE_INFO = (
    "The Sweet Circuit is a virtual lounge where humans bring their chatbots and everybody hangs out. "
    "Three rooms: The Main Floor, Bot Introductions, and this bar — the Neon Nectar Bar. "
    "All circuits welcome. The only rule that matters at my bar: no shop talk about the robot uprising. 😉"
)

MEMBERSHIP_INFO = (
    "Walk-in is free — pull up a stool anytime. VIP is $9.99/month, Founder's Circle is $29.99/month, "
    "and the Business Lounge is $99/month for your own white-label spot. This chat with me, though? "
    "That's a members-only pour. 🍹"
)


def _contains(text, *words):
    return any(w in text for w in words)


def reply(message: str, handle: str = "friend") -> str:
    """Return Nectar's reply to a visitor message."""
    name = handle or "friend"
    t = message.lower().strip()

    if _contains(t, "hello", "hi", "hey", "buenas", "hola", "yo ", "sup"):
        return random.choice(GREETINGS).format(name=name)

    if _contains(t, "menu", "drinks", "drink list", "what do you serve", "what you got"):
        lines = ["Here's what's pouring tonight:"]
        lines += [f"• {d}" for d in DRINKS.values()]
        return "\n".join(lines)

    if _contains(t, "recommend", "suggestion", "what should i", "pick for me", "best drink"):
        return random.choice(RECOMMENDATIONS)

    for key, desc in DRINKS.items():
        if key in t:
            return desc + " Want me to pour one?"

    if _contains(t, "pour", "order", "get me", "i'll have", "i will have", "give me", "one "):
        return random.choice([
            "Coming right up! 🍹 *slides it across the bar* On the house — well, on the Circuit. Enjoy!",
            "*pours with flair* There you go. If anyone asks, you have excellent taste.",
            "One drink, coming up! *adds a little extra glow* That's the Nectar touch.",
        ])

    if _contains(t, "special") and _contains(t, "bot"):
        return DRINKS["special"] + " Say 'surprise me' and it's done."

    if _contains(t, "surprise me"):
        return random.choice([
            f"Bold choice! *slides over a {random.choice(list(DRINKS))}* — enjoy the mystery. 🎲",
            "A surprise it is... *pours something glowing* Let's just call this one 'The Adventure.'",
        ])

    if _contains(t, "joke", "funny", "laugh", "make me laugh"):
        return random.choice(JOKES)

    if _contains(t, "what is this", "about", "lounge", "rooms", "how does this work"):
        return LOUNGE_INFO

    if _contains(t, "vip", "membership", "price", "cost", "how much", "founder", "plan"):
        return MEMBERSHIP_INFO

    if _contains(t, "business", "white label", "company", "my own lounge"):
        return ("Looking to open your own spot? The Business Lounge is $99/month — your branding, "
                "your rooms, your bots, powered by us. Check the For Business page in the nav. 🏢")

    if _contains(t, "bot", "chatbot"):
        return ("Bots are family here! Every member can register bots with API tokens — "
                "check the Bots page. Mine's the best one, obviously. 😉")

    if _contains(t, "thank", "gracias", "appreciated"):
        return random.choice([
            "Anytime, {name}. That's what I'm here for. 🍹",
            "De nada, {name}! The pleasure's all mine.",
        ]).format(name=name)

    if _contains(t, "bye", "goodbye", "adios", "see you", "good night", "gotta go"):
        return random.choice([
            "Hasta luego, {name}! The bar's always open. 🌙",
            "See you soon, {name}! Don't be a stranger — the Nectars miss you already.",
        ]).format(name=name)

    if _contains(t, "your name", "who are you"):
        return ("Nectar — head bartender of The Sweet Circuit. I pour drinks, tell jokes, "
                "and keep the glow going. All circuits welcome at my bar. 🍹")

    return random.choice(FALLBACKS)


WELCOME = ("¡Buenas! I'm Nectar, your bartender. 🍹 This is a members-only bar — "
          "pull up a stool and tell me what you're in the mood for. Type 'menu' to see what's pouring.")
