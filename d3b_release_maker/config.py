"""
Default config values for release maker
"""

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"

GH_TOKEN_VAR = "GH_TOKEN"
RELEASE_EMOJIS = "🏷🔖"
EMOJI_CATEGORIES = {
    "Additions": {"✨", "🎉", "📈", "➕", "🌐", "🔀", "🔊"},
    "Documentation": {"💡", "📝"},
    "Removals": {"🔥", "➖", "⏪", "🔇", "🗑"},
    "Fixes": {
        "🐛",
        "🚑",
        "🔒",
        "🍎",
        "🐧",
        "🏁",
        "🤖",
        "🍏",
        "🚨",
        "✏️",
        "👽",
        "👌",
        "♿️",
        "💬",
        "🚸",
        "🥅",
    },
    "Ops": {
        "🚀",
        "💚",
        "⬇️",
        "⬆️",
        "📌",
        "👷",
        "🐳",
        "📦",
        "👥",
        "🙈",
        "📸",
        "☸️",
        "🌱",
        "🚩",
    },
}
OTHER_CATEGORY = "Other Changes"
