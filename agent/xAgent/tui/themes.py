from textual.theme import Theme

THEMES: dict[str, Theme] = {
    "red": Theme(
        name="xagent-red",
        primary="#c92a2a",
        secondary="#862e9c",
        warning="#f08c00",
        error="#e03131",
        success="#2f9e44",
        accent="#ff6b6b",
        foreground="#fff0f0",
        background="#1a0f0f",
        surface="#241717",
        panel="#1f1212",
        boost="#2d1a1a",
        dark=True,
    ),
    "green": Theme(
        name="xagent-green",
        primary="#2b8a3e",
        secondary="#0c8599",
        warning="#f08c00",
        error="#e03131",
        success="#51cf66",
        accent="#69db7c",
        foreground="#f0fff4",
        background="#0d150f",
        surface="#152018",
        panel="#111a13",
        boost="#1a2b1e",
        dark=True,
    ),
    "white": Theme(
        name="xagent-white",
        primary="#495057",
        secondary="#5c636a",
        warning="#b8860b",
        error="#c92a2a",
        success="#2f9e44",
        accent="#212529",
        foreground="#212529",
        background="#f5f5f5",
        surface="#ffffff",
        panel="#ececec",
        boost="#ffffff",
        dark=False,
        luminosity_spread=0.1,
    ),
    "black": Theme(
        name="xagent-black",
        primary="#495057",
        secondary="#343a40",
        warning="#f08c00",
        error="#e03131",
        success="#2f9e44",
        accent="#f8f9fa",
        foreground="#e9ecef",
        background="#000000",
        surface="#0a0a0a",
        panel="#121212",
        boost="#1a1a1a",
        dark=True,
        luminosity_spread=0.05,
    ),
}

THEME_ORDER = ["red", "green", "white", "black"]

THEME_LABELS = {
    "red": "红",
    "green": "绿",
    "white": "白",
    "black": "黑",
}

THEME_DARK = {"red": True, "green": True, "white": False, "black": True}
