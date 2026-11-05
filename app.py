from __future__ import annotations
 
import base64, hashlib, json, random, re
from datetime import datetime
 
import requests
from flask import Flask, jsonify, render_template, request, session
from groq import Groq
 
import config
 
app = Flask(__name__)
app.secret_key = config.APP_SECRET
app.config['SESSION_PERMANENT'] = False
client = Groq(api_key=config.GROQ_API_KEY) if config.GROQ_API_KEY else None
 
STYLE_TAGS = {
    'Hypercar': ['aggressive aero', 'track-born drama', 'hero stance'],
    'Luxury': ['quiet prestige', 'clean surfacing', 'executive cabin'],
    'Off-Road': ['all-terrain muscle', 'raised stance', 'rugged utility'],
    'EV': ['clean tech', 'silent thrust', 'future cockpit'],
    'Retro-Future': ['heritage remix', 'neo-classic curves', 'concept nostalgia'],
    'Street': ['night-run energy', 'urban custom', 'after-dark attitude'],
}
MATERIALS = {
    'Carbon Fiber': ['carbon composite shell', 'forged aero fins', 'lightweight chassis'],
    'Aluminum': ['aluminum body frame', 'precision-machined trim', 'satin shell panels'],
    'Titanium': ['titanium highlights', 'heat-blued metal details', 'ultra-premium structural spine'],
    'Recycled Composite': ['recycled composite shell', 'eco-performance weave', 'sustainable cabin accents'],
    'Glass & Metal': ['glass canopy roof', 'brushed alloy bodywork', 'framed light signature'],
    'Mixed Performance': ['hybrid material shell', 'performance mesh venting', 'contrasting aero textures'],
}
PRICES = {'Daily Drive': '$58,000', 'Track Day': '$210,000', 'Adventure': '$96,000', 'Collector Reveal': '$320,000', 'City Tech': '$74,000', 'Luxury Tourer': '$168,000'}
PROMPT = '''You are a visionary automotive concept designer.
Generate a complete futuristic car concept based on:
Style: {style}
Primary Color: {primary_color}
Accent Color: {accent_color}
Material: {material}
Occasion: {occasion}
Inspiration: {inspiration}
 
Respond with raw JSON only — no markdown, no explanation.
{{
  "name": "2-4 word creative car name",
  "tagline": "punchy tagline max 10 words",
  "description": "2-3 sentence cinematic concept description",
  "materials": ["mat1", "mat2", "mat3"],
  "colorways": [{{"name": "launch spec", "body": "#hex", "accent": "#hex", "wheels": "#hex", "cabin": "#hex"}}],
  "features": ["feat1", "feat2", "feat3", "feat4"],
  "powertrain": "power system description",
  "cockpit_theme": "cockpit mood and interface idea",
  "target_driver": "who this concept is for",
  "retail_price": "$XXX,XXX",
  "style_tags": ["tag1", "tag2", "tag3"]
}}
Generate exactly 3 colorways. All hex codes must be valid #RRGGBB.'''
FIELDS = {'style': 'Hypercar', 'primary_color': '#1d4ed8', 'accent_color': '#f97316', 'material': 'Carbon Fiber', 'occasion': 'City Tech', 'inspiration': 'Tokyo neon rain'}
 
 
@app.get('/')
def index(): return render_template('index.html')
 
 
@app.get('/studio')
def studio(): return render_template('studio.html', hcaptcha_site_key=config.HCAPTCHA_SITE_KEY)
 
 
@app.get('/history')
def history(): return render_template('history.html', designs=session.get('designs', []))
 
 
@app.post('/generate')
def generate():
    data = request.get_json(silent=True) or request.form
    token = str(data.get('h-captcha-response', '')).strip()
    if not token: return error('Please complete the CAPTCHA.', 400)
    if not verify_hcaptcha(token): return error('CAPTCHA verification failed.', 400)
    prefs = {k: str(data.get(k, v)).strip() for k, v in FIELDS.items()}
    if any(not v for v in prefs.values()): return error('Please complete every field in the design brief.', 400)
    try:
        concept = ai_concept(prefs)
    except json.JSONDecodeError as exc:
        return error(f'Malformed AI response: {exc}', 500)
    except Exception as exc:
        return error(f'Concept generation failed: {exc}', 500)
    concept |= {
        'image_prompt': build_image_prompt(prefs),
        'image_url': placeholder_image(concept['name']),
        'brief': prefs,
        'timestamp': datetime.now().strftime('%d %b %Y, %I:%M %p'),
        'fingerprint': fingerprint(prefs, concept['name']),
    }
    save_design(concept)
    return jsonify(success=True, concept=concept, prefs=prefs)
 
 
@app.post('/generate-image')
def generate_image():
    data = request.get_json(silent=True) or {}
    prompt = str(data.get('image_prompt', '')).strip()
    if not prompt: return error('No image prompt.', 400)
    if not config.HF_API_KEY: return error('HF_API_KEY not configured.', 503)
    image_url = hf_image(prompt)
    if not image_url: return error('Image generation failed. Try again.', 500)
    fp = str(data.get('fingerprint', '')).strip()
    if fp:
        designs = session.get('designs', [])
        for item in designs:
            if item.get('fingerprint') == fp:
                item['image_url'] = image_url
                break
        session['designs'] = designs
        session.modified = True
    return jsonify(success=True, image_url=image_url)
 
 
@app.post('/clear-history')
def clear_history():
    session['designs'] = []
    session.modified = True
    return jsonify(success=True)
 
 
def error(message, status): return jsonify(error=message), status
 
 
def verify_hcaptcha(token: str) -> bool:
    try:
        r = requests.post(config.HCAPTCHA_VERIFY_URL, data={'secret': config.HCAPTCHA_SECRET, 'response': token}, timeout=5)
        return r.json().get('success', False)
    except Exception:
        return False
 
 
def ai_concept(prefs: dict[str, str]) -> dict:
    if client:
        raw = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {'role': 'system', 'content': 'Automotive concept design expert. Pure JSON only.'},
                {'role': 'user', 'content': PROMPT.format(**prefs)},
            ],
            temperature=0.85,
            max_tokens=1200,
        ).choices[0].message.content.strip()
        concept = sanitize(json.loads(extract_json(raw)), prefs)
        if concept: return concept
    return local_concept(prefs)
 
 
def extract_json(raw: str) -> str:
    raw = raw.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    match = re.search(r'\{[\s\S]*\}', raw)
    return match.group(0) if match else raw
 
 
def sanitize(data: dict, brief: dict[str, str]) -> dict:
    if not {'name', 'tagline', 'description', 'colorways'}.issubset(data):
        return {}
    return {
        'name': str(data.get('name', 'Concept X')).strip(),
        'tagline': str(data.get('tagline', 'Future in motion.')).strip(),
        'description': str(data.get('description', '')).strip(),
        'materials': [str(x).strip() for x in data.get('materials', [])][:5] or MATERIALS[brief['material']][:3],
        'features': [str(x).strip() for x in data.get('features', [])][:6] or ['Adaptive aero body surfaces', 'Panoramic digital cockpit', 'Active rear light blade', 'Predictive drive intelligence'],
        'powertrain': str(data.get('powertrain', 'Quad-motor electric performance')).strip(),
        'cockpit_theme': str(data.get('cockpit_theme', 'Minimal driver-first cockpit')).strip(),
        'target_driver': str(data.get('target_driver', 'Design-forward performance drivers')).strip(),
        'retail_price': str(data.get('retail_price', PRICES.get(brief['occasion'], '$120,000'))).strip(),
        'style_tags': [str(x).strip() for x in data.get('style_tags', [])][:3] or STYLE_TAGS[brief['style']][:3],
        'colorways': colorways(data.get('colorways', []), brief),
    }
 
 
def colorways(items: list[dict], brief: dict[str, str]) -> list[dict[str, str]]:
    fallback = [
        {'name': 'Launch Spec', 'body': brief['primary_color'], 'accent': brief['accent_color'], 'wheels': '#1b1e28', 'cabin': '#d9dce5'},
        {'name': 'Midnight Pulse', 'body': shift(brief['primary_color'], -18), 'accent': brief['accent_color'], 'wheels': '#0f1218', 'cabin': '#c7d2e2'},
        {'name': 'Solar Echo', 'body': shift(brief['primary_color'], 18), 'accent': shift(brief['accent_color'], 20), 'wheels': '#2b2f3e', 'cabin': '#f4f1eb'},
    ]
    clean = [{
        'name': str(item.get('name', fallback[i]['name'])).strip(),
        'body': valid_hex(item.get('body'), fallback[i]['body']),
        'accent': valid_hex(item.get('accent'), fallback[i]['accent']),
        'wheels': valid_hex(item.get('wheels'), fallback[i]['wheels']),
        'cabin': valid_hex(item.get('cabin'), fallback[i]['cabin']),
    } for i, item in enumerate(items[:3])]
    return clean + fallback[len(clean):]
 
 
def valid_hex(value, fallback):
    value = f"#{str(value).strip().lstrip('#')}"
    return value if re.fullmatch(r'#[0-9a-fA-F]{6}', value) else fallback
 
 
def shift(hex_color: str, amount: int) -> str:
    parts = [int(valid_hex(hex_color, '#667eea')[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{max(0, min(255, p + amount)):02x}' for p in parts)
 
 
def local_concept(brief: dict[str, str]) -> dict:
    seed = int(hashlib.sha1(json.dumps(brief, sort_keys=True).encode()).hexdigest(), 16)
    rng = random.Random(seed + random.randint(1, 9999))
    name = f"{rng.choice(['Nova','Aero','Volt','Phantom','Zenith','Pulse','Halo','Rift'])} {rng.choice(['GT','Flux','One','Racer','Drive','Arc','XR','Vision'])}"
    return sanitize({
        'name': name,
        'tagline': rng.choice(['Built for tomorrow\'s roads.', 'Where concept meets velocity.', 'Electric drama. Precision control.', 'Designed to steal the skyline.']),
        'description': f"{name} is a {brief['style'].lower()} concept shaped for {brief['occasion'].lower()} moments. It pairs {brief['material'].lower()} surfaces with {brief['primary_color']} as the hero tone and {brief['accent_color']} as the visual pulse. The whole build channels {brief['inspiration']} into a cinematic road presence.",
        'materials': MATERIALS.get(brief['material'], MATERIALS['Mixed Performance'])[:3],
        'features': [f"{brief['style']} silhouette with active aero channels", f"{brief['occasion']} tuned suspension package", 'Full-width reactive light blade', 'Augmented HUD with route intelligence', f"Cabin accents inspired by {brief['inspiration']}"],
        'powertrain': rng.choice(['Tri-motor electric vector drive', 'Hydrogen-electric hybrid thrust system', 'Dual-motor grand touring EV platform']),
        'cockpit_theme': rng.choice(['Wraparound holo-dash with floating controls', 'Pilot-inspired cabin with layered ambient light', 'Minimal glass cockpit with tactile drive spine']),
        'target_driver': rng.choice(['Trend-forward urban performance drivers', 'Collectors chasing a cinematic concept feel', 'Drivers who want tech presence with everyday usability']),
        'retail_price': PRICES.get(brief['occasion'], '$120,000'),
        'style_tags': STYLE_TAGS.get(brief['style'], ['future-ready', 'bold stance', 'concept energy']),
        'colorways': [],
    }, brief)
 
 
def color_name(hex_code: str) -> str:
    h = hex_code.lstrip('#').lower()
    try: r, g, b = int(h[:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception: return hex_code
    mx, mn = max(r, g, b), min(r, g, b)
    br, sat = mx / 255, (mx - mn) / mx if mx else 0
    if br < 0.15: return 'black'
    if br > 0.88 and sat < 0.15: return 'white'
    if sat < 0.18: return 'dark gray' if br < 0.4 else 'gray' if br < 0.65 else 'light gray'
    if mx == r: return ('orange' if g > 120 else 'dark orange') if g > b + 60 else 'magenta' if b > g + 40 else 'red'
    if mx == g: return 'yellow-green' if r > b + 60 else 'cyan-green' if b > r + 40 else 'green'
    return 'purple' if r > g + 60 else 'cyan' if g > r + 40 else 'blue'
 
 
def build_image_prompt(prefs: dict[str, str]) -> str:
    prompt = (
        f"Professional product photography of a futuristic {prefs['style']} concept car, "
        f"{color_name(prefs['primary_color'])} {prefs['material']} body, {color_name(prefs['accent_color'])} accent line, "
        f"{color_name(prefs['accent_color'])} rear light detail, side-front three quarter view, white studio background, sharp focus, ultra detailed, 8k, car only"
    )
    return prompt + (f", {prefs['inspiration']} theme" if prefs.get('inspiration') else '')
 
 
def hf_image(prompt: str) -> str | None:
    try:
        r = requests.post(
            config.HF_IMAGE_URL,
            headers={'Authorization': f'Bearer {config.HF_API_KEY}', 'Content-Type': 'application/json'},
            json={'inputs': prompt},
            timeout=60,
        )
        if r.status_code == 200 and r.headers.get('content-type', '').startswith('image'):
            mime = r.headers['content-type'].split(';')[0].strip()
            return f'data:{mime};base64,{base64.b64encode(r.content).decode()}'
    except Exception:
        return None
    return None
 
 
def save_design(concept: dict) -> None:
    existing = [d for d in session.get('designs', []) if d.get('fingerprint') != concept['fingerprint']]
    session['designs'] = [concept] + existing[: config.MAX_HISTORY - 1]
    session.modified = True
 
 
def fingerprint(prefs: dict[str, str], name: str) -> str:
    return hashlib.sha1('|'.join([*prefs.values(), name]).encode()).hexdigest()[:14]
 
 
def placeholder_image(name: str) -> str:
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 960 600'><rect width='960' height='600' fill='#0c1220'/><rect x='40' y='40' width='880' height='520' rx='28' fill='#111a2c' stroke='#22304f'/><text x='60' y='100' fill='#dbeafe' font-size='34' font-family='Arial' font-weight='700'>{name.replace('&', 'and')}</text><text x='60' y='140' fill='#94a3b8' font-size='20' font-family='Arial'>Rendering AI concept image...</text><rect x='60' y='470' width='340' height='16' rx='8' fill='#1f2937'/><rect x='60' y='470' width='220' height='16' rx='8' fill='#60a5fa'/><path d='M200 360 Q250 250 410 228 L580 220 Q700 225 800 330 L830 366 L790 392 L702 392 Q676 330 612 328 Q548 331 518 392 L352 392 Q324 330 262 328 Q195 331 162 392 L126 392 Q90 392 92 370 Z' fill='#2563eb' stroke='#60a5fa' stroke-width='6'/><path d='M374 236 L468 188 Q558 174 650 184 L718 306 L448 306 Z' fill='#cfd8e3' opacity='0.8'/><circle cx='270' cy='390' r='56' fill='#111827'/><circle cx='270' cy='390' r='24' fill='#64748b'/><circle cx='630' cy='390' r='56' fill='#111827'/><circle cx='630' cy='390' r='24' fill='#64748b'/></svg>"""
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()
 
 
if __name__ == '__main__':
    app.run(debug=True, port=5000)
