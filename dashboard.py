"""
VINTED FLIP ULTIMATE — Dashboard
==================================
http://localhost:8081
"""

import sqlite3, json
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request

DB = Path(__file__).parent / "vinted_ultimate.db"
app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vinted Flip Ultimate</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;700;900&family=Playfair+Display:wght@700;900&display=swap" rel="stylesheet">
<style>
:root{--bg:#0b0b10;--card:#141419;--card2:#1a1a22;--accent:#ff6b35;--green:#00d68f;--red:#ff4757;--text:#eaeaf0;--dim:#6b6b80;--border:#222233}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;min-height:100vh}

.hdr{padding:20px 32px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);flex-wrap:wrap;gap:16px}
.logo{display:flex;align-items:center;gap:12px}
.logo-i{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,#ff6b35,#ee5a24);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:#fff}
.logo h1{font-family:'Playfair Display',serif;font-size:1.3rem;letter-spacing:-.5px}
.logo h1 b{color:var(--accent)}
.logo .v{font-size:9px;color:var(--dim);background:var(--card);padding:2px 8px;border-radius:4px;margin-left:8px}
.stats{display:flex;gap:28px;flex-wrap:wrap}
.sv{font-size:1.4rem;font-weight:900;font-variant-numeric:tabular-nums}
.sv.g{color:var(--green)}.sv.a{color:var(--accent)}
.sl{font-size:8px;color:var(--dim);text-transform:uppercase;letter-spacing:1.5px;margin-top:2px}

.filters{padding:12px 32px;display:flex;gap:6px;border-bottom:1px solid var(--border);flex-wrap:wrap;overflow-x:auto}
.fb{background:var(--card);border:1px solid var(--border);color:var(--dim);padding:6px 16px;border-radius:8px;cursor:pointer;font-size:11px;font-weight:600;transition:.2s;white-space:nowrap;font-family:'DM Sans'}
.fb:hover{border-color:var(--accent);color:var(--accent)}.fb.on{background:var(--accent);border-color:var(--accent);color:#fff}

.grid{padding:20px 32px;display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}

.c{background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;transition:.3s}
.c:hover{border-color:rgba(255,107,53,.3);transform:translateY(-2px)}
.c .bar{height:3px}.bar.h{background:var(--accent)}.bar.w{background:#f9a825}.bar.k{background:var(--border)}
.c .bd{padding:18px}
.c .top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
.c .brand{font-family:'Playfair Display',serif;font-size:1.05rem}
.c .badge{font-size:11px;font-weight:800;padding:4px 12px;border-radius:20px}
.badge.h{background:rgba(255,107,53,.12);color:var(--accent)}.badge.w{background:rgba(249,168,37,.12);color:#f9a825}.badge.k{background:rgba(107,107,128,.1);color:var(--dim)}
.c .tags{display:flex;gap:5px;margin:6px 0;flex-wrap:wrap}
.c .tag{font-size:10px;padding:2px 8px;border-radius:5px;background:var(--card2);color:var(--dim)}
.c .ttl{font-size:11px;color:var(--dim);margin-bottom:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.c .prices{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:12px;background:rgba(0,0,0,.3);border-radius:10px;margin-bottom:8px}
.c .prices label{display:block;font-size:8px;color:var(--dim);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px}
.c .prices .v{font-size:15px;font-weight:800;font-variant-numeric:tabular-nums}
.c .prices .v.g{color:var(--green)}.c .prices .v.r{color:var(--red)}
.c .mkt{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;border-radius:8px;margin-bottom:14px;font-size:11px}
.c .mkt.good{background:rgba(0,214,143,.06);border:1px solid rgba(0,214,143,.15)}
.c .mkt.meh{background:rgba(249,168,37,.06);border:1px solid rgba(249,168,37,.15)}
.c .ecart{font-weight:900;font-size:14px}.ecart.g{color:var(--green)}.ecart.y{color:#f9a825}
.c .det{color:var(--dim);font-size:10px}
.c .acts{display:flex;gap:6px}
.btn{flex:1;padding:9px;border-radius:8px;font-size:11px;font-weight:700;cursor:pointer;text-align:center;text-decoration:none;transition:.2s;font-family:'DM Sans'}
.btn-p{background:linear-gradient(135deg,#ff6b35,#ee5a24);color:#fff;border:none}
.btn-s{background:transparent;border:1px solid var(--border);color:var(--dim)}

.empty{text-align:center;padding:60px;grid-column:1/-1;color:var(--dim)}
.empty h2{font-family:'Playfair Display',serif;margin-bottom:8px;color:var(--text)}

@keyframes up{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.c{animation:up .35s ease both}
@media(max-width:768px){.hdr,.filters,.grid{padding-left:14px;padding-right:14px}.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="hdr">
    <div class="logo"><div class="logo-i">V</div><h1>Vinted <b>Flip</b> Ultimate</h1><span class="v">v4.0</span></div>
    <div class="stats">
        <div><div class="sv" id="st">—</div><div class="sl">Articles</div></div>
        <div><div class="sv g" id="sg">—</div><div class="sl">Deals (-40%+)</div></div>
        <div><div class="sv a" id="sb">—</div><div class="sl">Meilleur écart</div></div>
        <div><div class="sv g" id="sp">—</div><div class="sl">Profit potentiel</div></div>
    </div>
</div>
<div class="filters" id="fl"></div>
<div class="grid" id="gr"><div class="empty"><h2>En attente du premier scan...</h2><p>Lance scraper.py</p></div></div>
<script>
let D=[],F='all';
async function load(){try{D=await(await fetch('/api/deals')).json();render();stats()}catch(e){}}
function stats(){
    document.getElementById('st').textContent=D.length;
    const g=D.filter(d=>(d.ecart_pourcent||0)>=40);
    document.getElementById('sg').textContent=g.length;
    if(D.length){
        document.getElementById('sb').textContent='-'+Math.max(...D.map(d=>d.ecart_pourcent||0)).toFixed(0)+'%';
        document.getElementById('sp').textContent=g.reduce((s,d)=>s+(d.marge_euro||0),0).toFixed(0)+'€';
    }
    const m=[...new Set(D.map(d=>d.marque).filter(Boolean))].sort();
    document.getElementById('fl').innerHTML=
        '<button class="fb on" onclick="sf(\\'all\\')">Tous</button>'+
        m.map(x=>'<button class="fb" onclick="sf(\\''+x+'\\')">'+x+'</button>').join('')+
        '<button class="fb" onclick="sf(\\'top\\')">🔥 Top</button>';
}
function sf(f){F=f;document.querySelectorAll('.fb').forEach(b=>b.classList.remove('on'));event.target.classList.add('on');render()}
function render(){
    let d=F==='all'?D:F==='top'?D.filter(x=>(x.ecart_pourcent||0)>=40):D.filter(x=>x.marque===F);
    const g=document.getElementById('gr');
    if(!d.length){g.innerHTML='<div class="empty"><h2>Aucun deal</h2></div>';return}
    g.innerHTML=d.map((x,i)=>{
        const e=x.ecart_pourcent||0,h=e>=40?'h':e>=20?'w':'k',
              ec=e>=40?'g':'y',mk=e>=20?'good':'meh';
        return `<div class="c" style="animation-delay:${i*.03}s">
        <div class="bar ${h}"></div><div class="bd">
        <div class="top"><div class="brand">${x.marque||''}</div><div class="badge ${h}">${x.score||0}/100</div></div>
        <div class="tags"><span class="tag">${x.type_vetement||'veste'}</span><span class="tag">📏 ${x.taille||'?'}</span>
        ${x.etat&&x.etat!='?'?'<span class="tag">'+x.etat+'</span>':''}
        ${x.nb_comparaisons?'<span class="tag">📊 '+x.nb_comparaisons+' comparés</span>':''}</div>
        <div class="ttl">${x.titre||''}</div>
        <div class="prices">
            <div><label>Prix</label><div class="v">${x.prix||0}€</div></div>
            <div><label>Médiane même produit</label><div class="v">${x.prix_median||0}€</div></div>
        </div>
        <div class="mkt ${mk}">
            <div><div class="ecart ${ec}">-${e.toFixed(0)}% vs marché</div>
            <div class="det">${x.nb_comparaisons||0} annonces du même produit</div></div>
            <div style="text-align:right"><label style="font-size:8px;color:var(--dim)">MARGE</label>
            <div class="v ${(x.marge_euro||0)>=0?'g':'r'}" style="font-size:15px;font-weight:800">+${x.marge_euro||0}€</div></div>
        </div>
        <div class="acts">
            <button class="btn btn-s" onclick="navigator.clipboard.writeText(\`${x.marque} — ${x.type_vetement||'veste'}\\n\\n${x.marque} authentique en très bon état.\\nTaille: ${x.taille||'?'}\\n\\nEnvoi soigné sous 24h.\\n\\nPrix: ${x.prix_median||0}€\`);this.textContent='✅ Copié'">📝 Annonce</button>
            <a href="${x.url||'#'}" target="_blank" class="btn btn-p">Voir →</a>
        </div></div></div>`}).join('');
}
load();setInterval(load,20000);
</script>
</body>
</html>
"""

@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/api/deals")
def deals():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM deals ORDER BY score DESC, date_trouvee DESC LIMIT 200").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/market")
def market():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM prix_marche ORDER BY date_analyse DESC LIMIT 50").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/stats")
def stats():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    good = c.execute("SELECT COUNT(*) FROM deals WHERE ecart_pourcent >= 40").fetchone()[0]
    best = c.execute("SELECT MAX(ecart_pourcent) FROM deals").fetchone()[0] or 0
    scans = c.execute("SELECT COUNT(*) FROM scan_log").fetchone()[0]
    conn.close()
    return jsonify({"total": total, "deals": good, "best_ecart": best, "scans": scans})

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════╗
    ║   🛍️  VINTED FLIP ULTIMATE — Dashboard    ║
    ║   👉 http://localhost:8081               ║
    ╚═══════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=8081, debug=False)
