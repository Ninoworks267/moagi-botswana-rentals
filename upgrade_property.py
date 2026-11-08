from pathlib import Path

p = Path("app.py")
text = p.read_text(encoding="utf-8")

route = '@app.route("/property/<int:property_id>")'
start = text.index(route)
template_start = text.index('    return page("""', start)
ending = '    """, p=p)'
template_end = text.index(ending, template_start) + len(ending)

replacement = '''    return page("""
    <style>
    .property-layout {
        display:grid;
        grid-template-columns:1.5fr 1fr;
        gap:25px;
        align-items:start;
    }
    .property-photo {
        width:100%;
        height:390px;
        object-fit:cover;
        border-radius:16px;
        background:#17202b;
        display:block;
    }
    .property-placeholder {
        height:390px;
        border-radius:16px;
        background:linear-gradient(135deg,#17283b,#101722);
        display:flex;
        align-items:center;
        justify-content:center;
        color:#a9c9e8;
    }
    .property-info {
        background:#101722;
        border:1px solid #293c51;
        border-radius:18px;
        padding:25px;
    }
    .property-price {
        font-size:32px;
        font-weight:800;
        color:#8fc4ff;
        margin:15px 0;
    }
    .property-specs {
        display:flex;
        flex-wrap:wrap;
        gap:10px;
        margin:20px 0;
    }
    .property-spec {
        background:#17283b;
        border:1px solid #31577d;
        padding:12px 15px;
        border-radius:10px;
        color:#c6e0ff;
    }
    .property-description {
        white-space:pre-line;
        line-height:1.8;
        color:#d0d5dc;
    }
    .landlord-panel {
        margin-top:22px;
        padding:20px;
        background:#101722;
        border:1px solid #293c51;
        border-radius:16px;
    }
    .property-actions {
        display:flex;
        flex-wrap:wrap;
        gap:10px;
        margin-top:20px;
    }
    @media(max-width:750px) {
        .property-layout {grid-template-columns:1fr}
        .property-photo,.property-placeholder {height:260px}
        .property-info {padding:19px}
        .property-price {font-size:27px}
    }
    </style>

    <p><a href="/" class="muted">← Back to explore homes</a></p>

    <div class="property-layout">
        <section>
            {% if p.photo %}
                <img class="property-photo"
                src="{{p.photo if p.photo.startswith('http') else url_for('static',filename='uploads/'+p.photo)}}"
                alt="{{p.title}}">
            {% else %}
                <div class="property-placeholder">Property photo unavailable</div>
            {% endif %}

            <div class="property-info" style="margin-top:20px">
                <span class="tag">{{p.location}}</span>
                <h1>{{p.title}}</h1>

                <div class="property-price">
                    P{{"{:,.0f}".format(p.price)}}
                    <span class="small">/ month</span>
                </div>

                <div class="property-specs">
                    <div class="property-spec">🛏 {{p.bedrooms}} Bedrooms</div>
                    <div class="property-spec">🛁 {{p.bathrooms}} Bathrooms</div>
                </div>

                <hr style="border:0;border-top:1px solid #293c51">
                <h2>About this property</h2>
                <div class="property-description">{{p.description or "No property description has been added yet."}}</div>
            </div>
        </section>

        <aside>
            <div class="property-info">
                <div class="eyebrow">Interested in this home?</div>
                <h2>Make your next move.</h2>
                <p class="muted">Connect directly with the landlord to ask questions and discuss this property.</p>

                <div class="property-actions">
                    {% if me and me.id != p.landlord_id %}
                        <a class="btn" href="/chat/{{p.landlord_id}}?property_id={{p.id}}">Contact landlord</a>
                    {% elif not me %}
                        <a class="btn" href="/login">Log in to contact landlord</a>
                    {% else %}
                        <p class="muted">This is your property listing.</p>
                    {% endif %}
                    <a class="btn ghost" href="/">Browse more homes</a>
                </div>
            </div>

            <div class="landlord-panel">
                <div class="eyebrow">Listed by</div>
                <h2>{{p.first_name}} {{p.surname}}</h2>
                <p class="muted">{{p.landlord_location}}</p>
                <a href="/landlord/{{p.landlord_id}}">View landlord profile →</a>
            </div>
        </aside>
    </div>
    """, p=p)'''

text = text[:template_start] + replacement + text[template_end:]
p.write_text(text, encoding="utf-8", newline="\n")
print("Property details page upgraded successfully.")

