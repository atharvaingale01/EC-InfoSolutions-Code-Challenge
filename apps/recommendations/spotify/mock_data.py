"""
Fixture catalogue for SPOTIFY_MOCK mode.

Real Spotify track ids / names / artists, grouped by the genre terms the
engine searches for, so mock runs look like live runs and line up with the
demo activity created by `seed_demo`.
"""

_SPOTIFY_TRACK_URL = "https://open.spotify.com/track/{id}"


def _t(track_id, name, artist, album, popularity, duration_ms=210_000):
    return {
        "id": track_id,
        "name": name,
        "artists": [{"name": artist}],
        "album": {"name": album},
        "preview_url": None,
        "external_urls": {"spotify": _SPOTIFY_TRACK_URL.format(id=track_id)},
        "popularity": popularity,
        "duration_ms": duration_ms,
    }


TRACKS_BY_GENRE: dict[str, list[dict]] = {
    "rock": [
        _t("6b2oQwSGFkzsMtQruIWm2p", "Creep", "Radiohead", "Pablo Honey", 88),
        _t("3n3Ppam7vgaVa1iaRUc9Lp", "Mr. Brightside", "The Killers", "Hot Fuss", 87),
        _t("7ouMYWpwJ422jRcDASZB7P", "Seven Nation Army", "The White Stripes", "Elephant", 84),
        _t("4bHsxqR3GMrXTxEPLuK5ue", "Don't Stop Believin'", "Journey", "Escape", 82),
        _t("40riOy7x9W7GXjyGp4pjAv", "Hotel California", "Eagles", "Hotel California", 83),
    ],
    "indie": [
        _t("5ghIJDpPoe3CfHMGu71E6T", "Do I Wanna Know?", "Arctic Monkeys", "AM", 89),
        _t("2QjOHCTQ1Jl3zawyYOpxh6", "Sweater Weather", "The Neighbourhood", "I Love You.", 86),
        _t("0lP4HYLmvowOKdsQ7CVkuq", "Take Me Out", "Franz Ferdinand", "Franz Ferdinand", 78),
        _t("6nek1Nin9q48AVZcWs9e9D", "Paradise", "Coldplay", "Mylo Xyloto", 80),
    ],
    "hip-hop": [
        _t("7KXjTSCq5nL1LoYtL7XAwS", "HUMBLE.", "Kendrick Lamar", "DAMN.", 87),
        _t("2xLMifQCjDGFmkHkpNLD9h", "SICKO MODE", "Travis Scott", "ASTROWORLD", 84),
        _t("0wwPcA6wtMf6HUMpIRdeP7", "Hotline Bling", "Drake", "Views", 79),
        _t("7lQ8MOhq6IN2w8EYcFNSUk", "Without Me", "Eminem", "The Eminem Show", 85),
    ],
    "r-n-b": [
        _t("1zi7xx7UVEFkmKfv06H8x0", "One Dance", "Drake", "Views", 82),
        _t("7MXVkk9YMctZqd1Srtv4MB", "Starboy", "The Weeknd", "Starboy", 86),
        _t("2dLLR6qlu5UJ5gk0dKz0h3", "Kiss Me More", "Doja Cat", "Planet Her", 80),
        _t("4DHcnVTT87F0zZhRPYmZ3B", "Redbone", "Childish Gambino", "Awaken, My Love!", 81),
    ],
    "pop": [
        _t("39LLxExYz6ewLAcYrzQQyP", "Levitating", "Dua Lipa", "Future Nostalgia", 85),
        _t("0VjIjW4GlUZAMYd2vXMi3b", "Blinding Lights", "The Weeknd", "After Hours", 90),
        _t(
            "463CkQjx2Zk1yXoBuierM9",
            "Levitating (feat. DaBaby)",
            "Dua Lipa",
            "Future Nostalgia",
            83,
        ),
        _t("1BxfuPKGuaTgP7aM0Bbdwr", "Cruel Summer", "Taylor Swift", "Lover", 92),
        _t("3nqQXoyQOWXiESFLlDF1hG", "Unholy", "Sam Smith", "Gloria", 81),
    ],
    "dance": [
        _t(
            "2K7xn816oNHJZ0aVqdQsha",
            "Delilah (pull me out of this)",
            "Fred again..",
            "Actual Life 3",
            78,
        ),
        _t("6FZDfxM3a3UCqtzo5pxSLZ", "Don't Start Now", "Dua Lipa", "Future Nostalgia", 84),
        _t("4h9wh7iOZ0GGn8QVp4RAOB", "I Gotta Feeling", "The Black Eyed Peas", "THE E.N.D.", 79),
        _t("2tpWsVSb9UEmDRxAl1zhX1", "Counting Stars", "OneRepublic", "Native", 82),
    ],
    "classical": [
        _t("1dCqNqO2szZjWNCQXLVDaE", "Clair de Lune", "Claude Debussy", "Suite bergamasque", 74),
        _t("3zrs4mucS4pJ8N9LdEbmqw", "Gymnopédie No. 1", "Erik Satie", "Gymnopédies", 76),
        _t("7bnjbIYqcOKLLXG4NnBKfF", "Nuvole Bianche", "Ludovico Einaudi", "Una Mattina", 77),
        _t("5UdFfEnIEIO1HOhXYqZg6f", "Experience", "Ludovico Einaudi", "In a Time Lapse", 79),
    ],
    "jazz": [
        _t("0aWMVrwxPNYkKmFthzmpRi", "So What", "Miles Davis", "Kind of Blue", 72),
        _t("1YQWosTIljIvxAgHWTp7KP", "Take Five", "The Dave Brubeck Quartet", "Time Out", 73),
        _t(
            "4vLYewWIvqHfKtJDk8c8tq",
            "My Favorite Things",
            "John Coltrane",
            "My Favorite Things",
            66,
        ),
        _t("3ZGtu63S3dXijBDNBR0ZwT", "Feeling Good", "Nina Simone", "I Put a Spell on You", 75),
    ],
    "edm": [
        _t("2cGxRwrMyEAp8dEbuZaVv6", "Around the World", "Daft Punk", "Homework", 76),
        _t("0DiWol3AO6WpXZgp0goxAV", "One More Time", "Daft Punk", "Discovery", 81),
        _t(
            "3AJwUDP919kvQ9QcozQPxg",
            "Titanium (feat. Sia)",
            "David Guetta",
            "Nothing but the Beat",
            80,
        ),
        _t("4NEc4aTvuSlhNaXhc4MCO0", "Animals", "Martin Garrix", "Animals", 74),
    ],
    "electronic": [
        _t("5qmRM6NgbNZVyN8zDQEGaV", "Midnight City", "M83", "Hurry Up, We're Dreaming", 78),
        _t("1fDsrQ23eTAVFElUMaf38X", "Strobe", "deadmau5", "For Lack of a Better Name", 68),
        _t("2AAyEogh6o5tvYTd3MA4h9", "Get Lucky", "Daft Punk", "Random Access Memories", 82),
        _t("0nbXyq5TXYPCO7pr3N8S4I", "The Less I Know the Better", "Tame Impala", "Currents", 86),
    ],
    "acoustic": [
        _t("1dGr1c8CrMLDpV6mPbImSI", "Lover", "Taylor Swift", "Lover", 80),
        _t("3JvKfv6T31zO0ini8iNItO", "Another Love", "Tom Odell", "Long Way Down", 84),
        _t("0tgVpDi06FyKpA1z0VMD4v", "Perfect", "Ed Sheeran", "÷ (Deluxe)", 86),
    ],
    "singer-songwriter": [
        _t("4iV5W9uYEdYUVa79Axb7Rh", "Hallelujah", "Jeff Buckley", "Grace", 73),
        _t("2rurDawMfoKP4uHyb2kJBt", "Skinny Love", "Bon Iver", "For Emma, Forever Ago", 71),
        _t("6DCZcSspjsKoFjzjrWoCdn", "Fast Car", "Tracy Chapman", "Tracy Chapman", 79),
    ],
    "chill": [
        _t(
            "3AhXZa8sUQht0UEdBJgpGc",
            "Sunflower",
            "Post Malone",
            "Spider-Man: Into the Spider-Verse",
            84,
        ),
        _t("0u2P5u6lvoDfwTYjAADbn4", "lovely (with Khalid)", "Billie Eilish", "lovely", 85),
        _t("2Fxmhks0bxGSBdJ92vM42m", "bad guy", "Billie Eilish", "WHEN WE ALL FALL ASLEEP", 84),
    ],
    "ambient": [
        _t("2dKAaC0zc8g3IVmjDSs5uu", "An Ending (Ascent)", "Brian Eno", "Apollo", 62),
        _t("6Ke1SeEJt5s2wTHZzYx3cV", "Weightless", "Marconi Union", "Weightless", 64),
    ],
    "lo-fi": [
        _t("6tK2cUFYKeInmwzOVGfBVE", "Snowman", "WYS", "Snowman", 66),
        _t("2XIc1pqjXV3Cr2BQUGNBck", "Dreams", "Lofi Fruits Music", "Dreams", 60),
    ],
    "instrumental": [
        _t(
            "2Foc5Q5nqNiosCNqttzHof",
            "Ludovico Einaudi: Una Mattina",
            "Ludovico Einaudi",
            "Una Mattina",
            70,
        ),
        _t("5xg2g4oR7Qv2wGUyjEoXqc", "River Flows in You", "Yiruma", "First Love", 78),
    ],
    "soul": [
        _t("4WVNGtmxgAUTU2UhoZOEqy", "Ain't No Sunshine", "Bill Withers", "Just As I Am", 76),
        _t("1eBcc8fzfZpZJHCJ8iVOgb", "Superstition", "Stevie Wonder", "Talking Book", 78),
    ],
    "reggaeton": [
        _t("6habFhsOp2NvshLv26DqMb", "Despacito", "Luis Fonsi", "VIDA", 81),
        _t("5w9c2J52mkdntKOmRLeM2m", "Tití Me Preguntó", "Bad Bunny", "Un Verano Sin Ti", 85),
    ],
}

# Artist name -> top tracks (real ids). Used by search_artist / artist_top_tracks.
ARTIST_TOP_TRACKS: dict[str, list[dict]] = {
    "Radiohead": [
        _t("6b2oQwSGFkzsMtQruIWm2p", "Creep", "Radiohead", "Pablo Honey", 88),
        _t("63OQupATfueTdZMWTxW03A", "Karma Police", "Radiohead", "OK Computer", 80),
        _t("5jafMI8FLibnjkYTZ33m0c", "No Surprises", "Radiohead", "OK Computer", 84),
    ],
    "Arctic Monkeys": [
        _t("5ghIJDpPoe3CfHMGu71E6T", "Do I Wanna Know?", "Arctic Monkeys", "AM", 89),
        _t("3jfr0TF6DQcOLat8gGn7E2", "505", "Arctic Monkeys", "Favourite Worst Nightmare", 87),
        _t(
            "2AT8iROs4FQueDv2c8q2KE",
            "Why'd You Only Call Me When You're High?",
            "Arctic Monkeys",
            "AM",
            85,
        ),
    ],
    "Kendrick Lamar": [
        _t("7KXjTSCq5nL1LoYtL7XAwS", "HUMBLE.", "Kendrick Lamar", "DAMN.", 87),
        _t("6AI3ezQ4o3HUoP6Dhudph3", "Not Like Us", "Kendrick Lamar", "Not Like Us", 90),
        _t("3eze1WULQQWgWdY0AMB1jl", "Money Trees", "Kendrick Lamar", "good kid, m.A.A.d city", 84),
    ],
    "Drake": [
        _t("1zi7xx7UVEFkmKfv06H8x0", "One Dance", "Drake", "Views", 82),
        _t("0wwPcA6wtMf6HUMpIRdeP7", "Hotline Bling", "Drake", "Views", 79),
        _t("6DCZcSspjsKoFjzjrWoCdn", "God's Plan", "Drake", "Scorpion", 85),
    ],
    "Dua Lipa": [
        _t("39LLxExYz6ewLAcYrzQQyP", "Levitating", "Dua Lipa", "Future Nostalgia", 85),
        _t("6FZDfxM3a3UCqtzo5pxSLZ", "Don't Start Now", "Dua Lipa", "Future Nostalgia", 84),
        _t("2ekn2ttSfGqwhhate0LSR0", "New Rules", "Dua Lipa", "Dua Lipa", 80),
    ],
    "The Weeknd": [
        _t("0VjIjW4GlUZAMYd2vXMi3b", "Blinding Lights", "The Weeknd", "After Hours", 90),
        _t("7MXVkk9YMctZqd1Srtv4MB", "Starboy", "The Weeknd", "Starboy", 86),
        _t("2p8IUWQDrpjuFltbdgLOag", "After Hours", "The Weeknd", "After Hours", 80),
    ],
    "Miles Davis": [
        _t("0aWMVrwxPNYkKmFthzmpRi", "So What", "Miles Davis", "Kind of Blue", 72),
        _t("4vLYewWIvqHfKtJDk8c8tq", "Blue in Green", "Miles Davis", "Kind of Blue", 68),
        _t("1YQWosTIljIvxAgHWTp7KP", "Freddie Freeloader", "Miles Davis", "Kind of Blue", 65),
    ],
    "Daft Punk": [
        _t("2AAyEogh6o5tvYTd3MA4h9", "Get Lucky", "Daft Punk", "Random Access Memories", 82),
        _t("0DiWol3AO6WpXZgp0goxAV", "One More Time", "Daft Punk", "Discovery", 81),
        _t("2cGxRwrMyEAp8dEbuZaVv6", "Around the World", "Daft Punk", "Homework", 76),
    ],
    "Fred again..": [
        _t(
            "2K7xn816oNHJZ0aVqdQsha",
            "Delilah (pull me out of this)",
            "Fred again..",
            "Actual Life 3",
            78,
        ),
        _t(
            "4v6e3WlYwBqYj8g8y0nqGj",
            "Marea (we've lost dancing)",
            "Fred again..",
            "Actual Life",
            74,
        ),
        _t("0ZXXtvNwDRNuvVWyvHT7Zm", "Jungle", "Fred again..", "Jungle", 76),
    ],
}
