"""
Fixture data for `manage.py seed_demo`. Kept as plain Python so tests and
other commands can import it without touching the database.
"""

DEMO_PASSWORD = "Password123!"

DEMO_USERS = [
    {
        "email": "alice@example.com",
        "name": "Alice",
        "favorite_genres": ["rock", "indie"],
        "favorite_artists": ["Radiohead", "Arctic Monkeys"],
        "moods": ["chill"],
    },
    {
        "email": "bob@example.com",
        "name": "Bob",
        "favorite_genres": ["hip-hop", "r-n-b"],
        "favorite_artists": ["Kendrick Lamar", "Drake"],
        "moods": ["energetic", "party"],
    },
    {
        "email": "carol@example.com",
        "name": "Carol",
        "favorite_genres": ["pop", "dance"],
        "favorite_artists": ["Dua Lipa", "The Weeknd"],
        "moods": ["happy"],
    },
    {
        "email": "dave@example.com",
        "name": "Dave",
        "favorite_genres": ["classical", "jazz"],
        "favorite_artists": ["Miles Davis"],
        "moods": ["focus"],
    },
    {
        "email": "eve@example.com",
        "name": "Eve",
        "favorite_genres": ["edm", "electronic"],
        "favorite_artists": ["Daft Punk", "Fred again.."],
        "moods": ["workout"],
    },
]

# Staff but NOT superuser: can use the staff paths of the API and log into
# /admin/, but has no model permissions there. Demo credentials are public.
DEMO_STAFF = {"email": "admin@example.com", "name": "Admin", "is_staff": True}

# (track_id, track_name, artist_name) — real Spotify IDs so activity lines up
# with what the search-based recommendations are likely to return.
DEMO_TRACKS = [
    ("6b2oQwSGFkzsMtQruIWm2p", "Creep", "Radiohead"),
    ("5ghIJDpPoe3CfHMGu71E6T", "Do I Wanna Know?", "Arctic Monkeys"),
    ("7KXjTSCq5nL1LoYtL7XAwS", "HUMBLE.", "Kendrick Lamar"),
    ("1zi7xx7UVEFkmKfv06H8x0", "One Dance", "Drake"),
    ("39LLxExYz6ewLAcYrzQQyP", "Levitating", "Dua Lipa"),
    ("0VjIjW4GlUZAMYd2vXMi3b", "Blinding Lights", "The Weeknd"),
    ("0aWMVrwxPNYkKmFthzmpRi", "So What", "Miles Davis"),
    ("2cGxRwrMyEAp8dEbuZaVv6", "Around the World", "Daft Punk"),
    ("2K7xn816oNHJZ0aVqdQsha", "Delilah (pull me out of this)", "Fred again.."),
    ("3n3Ppam7vgaVa1iaRUc9Lp", "Mr. Brightside", "The Killers"),
]

# Rough per-user taste weights so trends look plausible.
ACTION_WEIGHTS = {"play": 0.6, "like": 0.25, "skip": 0.15}
