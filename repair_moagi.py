from pathlib import Path

p = Path("app.py")
text = p.read_text(encoding="utf-8")

fixes = [
    ("ðŸ‡§ðŸ‡¼", "🇧🇼"),
    ("ðŸ‘‹", "👋"),
    ("ðŸ’¬", "💬"),
    ("ðŸ”’", "🔒"),
    ("ðŸ˜Š", "😊"),
    ("ðŸ˜‚", "😂"),
    ("â¤ï¸", "❤️"),
    ("â˜…", "★"),
    ("â˜†", "☆"),
    ("â€”", "—"),
    ("â€“", "–"),
    ("â€™", "’"),
    ("â€œ", "“"),
    ("âž¤", "➤"),
    ("âœï¸", "✏️"),
    ("Â·", "·"),
]

for old, new in fixes:
    text = text.replace(old, new)

p.write_text(text, encoding="utf-8", newline="\n")
print("Text replacements completed.")
