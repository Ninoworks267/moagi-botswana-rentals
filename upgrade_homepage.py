from pathlib import Path

p = Path("app.py")
text = p.read_text(encoding="utf-8")

css = """
/* MOAGI HOMEPAGE DESIGN UPGRADE */
:root {
    --blue: #2878d0;
    --blue-light: #65aaff;
    --white: #ffffff;
    --surface: #11151b;
    --border: #26313e;
}
html { scroll-behavior: smooth; }
body {
    background: #080b10;
    color: #f7f9fc;
}
nav {
    background: rgba(8,11,16,.96);
    backdrop-filter: blur(14px);
    border-bottom: 1px solid #202c39;
}
.logo { color: white; }
.logo::after { content: "."; color: var(--blue-light); }
nav a:hover { color: var(--blue-light); }
.container { max-width: 1180px; }
.hero {
    padding: 85px 35px 65px;
    margin: 25px 0 28px;
    border: 1px solid #25374b;
    border-radius: 22px;
    background: radial-gradient(ellipse at 85% 15%, #153b62 0%, transparent 48%),
                linear-gradient(135deg,#111a27,#090d14 70%);
}
.hero .eyebrow { color: #80baff; }
.hero h1 {
    max-width: 750px;
    line-height: 1.05;
    letter-spacing: -3px;
}
.hero .muted { max-width: 580px; font-size: 17px; }
.btn {
    background: var(--blue);
    border-color: var(--blue);
    color: white;
    transition: .2s ease;
}
.btn:hover {
    background: #398be8;
    border-color: #398be8;
    color: white;
}
.btn.ghost {
    background: transparent;
    border-color: #52657a;
    color: white;
}
.btn.ghost:hover {
    background: #17283b;
    border-color: var(--blue-light);
}
main.container > form.card {
    max-width: 100%;
    padding: 24px;
    background: #101722;
    border-color: #293c51;
    margin-bottom: 42px;
}
input, select, textarea {
    background: #0b111a;
    border-color: #344253;
}
input:focus, select:focus, textarea:focus {
    outline: 2px solid #2878d0;
    border-color: #2878d0;
}
h2 { letter-spacing: -.5px; margin: 35px 0 20px; }
.grid { gap: 22px; }
.card {
    background: #101722;
    border-color: #263547;
    border-radius: 17px;
}
.card:hover {
    border-color: #438bd1;
    box-shadow: 0 12px 32px rgba(0,0,0,.25);
}
.card img { height: 205px; }
.card .price { color: #8fc4ff; }
.tag {
    color: #a9d2ff;
    border-color: #31577d;
    background: #14263a;
}
footer {
    border-top: 1px solid #202c39;
    margin-top: 65px;
}
@media(max-width:650px) {
    .hero {
        padding: 45px 22px;
        margin-top: 15px;
        border-radius: 16px;
    }
    .hero h1 { letter-spacing: -2px; }
    .hero .muted { font-size: 15px; }
    main.container > form.card { padding: 17px; }
    .card img { height: 190px; }
    nav .links { gap: 12px; }
}
"""

if "/* MOAGI HOMEPAGE DESIGN UPGRADE */" not in text:
    if "</style>" not in text:
        raise SystemExit("Could not find the CSS closing tag. No changes made.")
    text = text.replace("</style>", css + "\n</style>", 1)

p.write_text(text, encoding="utf-8", newline="\n")
print("Homepage styling updated.")
