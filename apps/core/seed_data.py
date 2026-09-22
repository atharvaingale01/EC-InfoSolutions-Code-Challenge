"""
Fixture data for `manage.py seed_demo`. Kept as plain Python so tests and
other commands can import it without touching the database.
"""

DEMO_PASSWORD = "Password123!"

# Five listeners with distinct Indian tastes. Artist seeds carry the most weight
# (Spotify's genre filter no longer ranks by popularity), so each profile names two.
DEMO_USERS = [
    {
        "email": "aarav@example.com",
        "name": "Aarav",
        "favorite_genres": ["bollywood", "indian pop"],
        "favorite_artists": ["Arijit Singh", "Pritam"],
        "moods": ["romantic"],
    },
    {
        "email": "bhavya@example.com",
        "name": "Bhavya",
        "favorite_genres": ["punjabi", "bhangra"],
        "favorite_artists": ["Diljit Dosanjh", "Karan Aujla"],
        "moods": ["party", "energetic"],
    },
    {
        "email": "charvi@example.com",
        "name": "Charvi",
        "favorite_genres": ["indian indie", "indian pop"],
        "favorite_artists": ["Prateek Kuhad", "Anuv Jain"],
        "moods": ["chill"],
    },
    {
        "email": "dev@example.com",
        "name": "Dev",
        "favorite_genres": ["hindustani classical", "carnatic"],
        "favorite_artists": ["A.R. Rahman", "Shreya Ghoshal"],
        "moods": ["focus"],
    },
    {
        "email": "esha@example.com",
        "name": "Esha",
        "favorite_genres": ["desi pop", "indian folk"],
        "favorite_artists": ["DIVINE", "Ritviz"],
        "moods": ["workout"],
    },
]

# Staff but NOT superuser: can use the staff paths of the API and log into
# /admin/, but has no model permissions there. Demo credentials are public.
DEMO_STAFF = {"email": "admin@example.com", "name": "Admin", "is_staff": True}

# (track_id, track_name, artist_name) — real Spotify IDs (market IN), one per seeded
# artist in profile order, so each demo user's activity lines up with their tastes.
DEMO_TRACKS = [
    ("6WlARP6h4CDVOcY386wW0W", 'Sitaare (From "Ikkis")', "Arijit Singh"),
    ("23T4WcVkvuaAEOgXr848i1", "Tera Mera Rishta - Original Version", "Pritam"),
    ("0XwRlvv3KlOu4HWlOH34XG", "Lover", "Diljit Dosanjh"),
    ("0cYohCh24y1aMjJmcS9RBl", "For A Reason", "Karan Aujla"),
    ("3hB9lDLyAClYVZivMMl20N", "Co2", "Prateek Kuhad"),
    ("1bMkimTb47umgNP6xCi4A1", "Arz Kiya Hai | Coke Studio Bharat", "Anuv Jain"),
    ("6flQ5XJKj5qIhpxSHOd3jC", "Aawaara Angaara", "A.R. Rahman"),
    ("0rk2X5TAhraBC5aCIXK2Rq", "Samjhawan", "Shreya Ghoshal"),
    ("4w3SKupiTNoAMi8JKbJAl9", "No Competition", "DIVINE"),
    ("7tbzfR8ZvZzJEzy6v0d6el", "Liggi", "Ritviz"),
]

# Rough per-user taste weights so trends look plausible.
ACTION_WEIGHTS = {"play": 0.6, "like": 0.25, "skip": 0.15}
