"""
Web-Terminal für den Copy-Trading-Bot.
Einseitige Browser-App: Settings (API-Keys speichern), Live-Dashboard
(Positionen, P&L, Logs) und Call-Bot (Pre-Bonding, New Pairs, Trending).
Bot läuft im selben Asyncio-Event-Loop.
"""

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from config import cfg
from shared_state import state

log = logging.getLogger("web")

app = FastAPI(title="Copy-Trading Web-Terminal")
_bot = None


def _get_bot():
    global _bot
    if _bot is None:
        from bot import CopyTradingBot
        _bot = CopyTradingBot()
    return _bot


@app.get("/", response_class=HTMLResponse)
async def index():
    return INDEX_HTML


@app.get("/api/config")
async def get_config():
    return JSONResponse(cfg.as_dict(mask_secrets=True))


@app.post("/api/config")
async def save_config(data: dict):
    try:
        cfg.save(data)
        state.add_log("INFO", "Einstellungen gespeichert.")
        return {"ok": True, "configured": cfg.is_configured()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.post("/api/derive")
async def derive_address(data: dict):
    """Leitet aus einer Recovery Phrase die Wallet-Adresse(n) ab — nur zur Prüfung."""
    chain = data.get("chain", "SOL")
    mnemonic = (data.get("mnemonic") or "").strip()
    if mnemonic == "********" or not mnemonic:
        return JSONResponse({"ok": False, "error": "Bitte Recovery Phrase eingeben."}, status_code=400)
    words = len(mnemonic.split())
    if words not in (12, 24):
        return JSONResponse({"ok": False, "error": f"Phrase hat {words} Wörter — erwartet 12 oder 24."}, status_code=400)
    try:
        import key_utils
        if chain == "SOL":
            return {"ok": True, "addresses": key_utils.list_solana_addresses(mnemonic)}
        else:
            addr = key_utils.derive_eth_address(mnemonic)
            return {"ok": True, "addresses": [{"path": "m/44'/60'/0'/0/0", "label": "MetaMask", "address": addr}]}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.post("/api/start")
async def start_bot():
    if not cfg.is_configured():
        return JSONResponse(
            {"ok": False, "error": "Keine Chain vollständig konfiguriert. Bitte Settings ausfüllen."},
            status_code=400,
        )
    try:
        bot = _get_bot()
        await bot.start()
        return {"ok": True}
    except Exception as e:
        log.exception("Bot-Start fehlgeschlagen")
        state.add_log("ERROR", f"Start fehlgeschlagen: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/stop")
async def stop_bot():
    bot = _get_bot()
    await bot.stop()
    return {"ok": True}


@app.post("/api/pause")
async def pause_bot():
    _get_bot().pause()
    return {"ok": True}


@app.post("/api/resume")
async def resume_bot():
    _get_bot().resume()
    return {"ok": True}


@app.get("/api/state")
async def get_state():
    return JSONResponse(state.snapshot())


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(state.snapshot())
            await asyncio.sleep(1.5)
    except (WebSocketDisconnect, Exception):
        return


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Copy-Trading Terminal</title>
<style>
  :root{
    --bg:#0a0e14; --panel:#0f1620; --panel2:#131c28; --border:#1e2a3a;
    --txt:#c9d6e3; --muted:#5b6b7d; --accent:#3fb950; --accent2:#58a6ff;
    --red:#f85149; --green:#3fb950; --yellow:#d29922; --cyan:#39c5cf;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--txt);font:13px/1.5 'SF Mono',Menlo,Consolas,monospace}
  a{color:var(--accent2);text-decoration:none}
  ::-webkit-scrollbar{width:8px;height:8px}
  ::-webkit-scrollbar-thumb{background:#22303f;border-radius:4px}

  header{display:flex;align-items:center;gap:14px;padding:10px 18px;
    background:var(--panel);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:10}
  .logo{font-weight:700;color:#fff;letter-spacing:.5px}
  .logo span{color:var(--accent)}
  .pills{display:flex;gap:8px;flex-wrap:wrap}
  .pill{padding:3px 10px;border-radius:20px;font-size:11px;background:var(--panel2);
    border:1px solid var(--border);color:var(--muted)}
  .pill.on{color:var(--green);border-color:#1d3a25}
  .pill.off{color:var(--muted)}
  .pill.dry{color:var(--yellow);border-color:#3a2f12}
  .pill.live{color:var(--red);border-color:#3a1d1d}
  .spacer{flex:1}
  .btn{padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--panel2);
    color:var(--txt);cursor:pointer;font-family:inherit;font-size:12px;transition:.15s}
  .btn:hover{border-color:var(--accent2)}
  .btn.go{background:#16301d;border-color:#1d4a2b;color:var(--green)}
  .btn.stop{background:#301616;border-color:#4a1d1d;color:var(--red)}
  .btn.warn{background:#302816;border-color:#4a3d1d;color:var(--yellow)}

  nav{display:flex;gap:2px;padding:0 18px;background:var(--panel);border-bottom:1px solid var(--border)}
  nav button{background:none;border:none;color:var(--muted);padding:11px 16px;cursor:pointer;
    font-family:inherit;font-size:13px;border-bottom:2px solid transparent}
  nav button.active{color:#fff;border-bottom-color:var(--accent)}
  nav button:hover{color:var(--txt)}

  main{padding:18px;max-width:1400px;margin:0 auto}
  .tab{display:none}
  .tab.active{display:block}

  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
  .stat{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:14px}
  .stat .label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.5px}
  .stat .val{font-size:24px;font-weight:700;margin-top:4px;color:#fff}

  .panel{background:var(--panel);border:1px solid var(--border);border-radius:8px;margin-bottom:16px}
  .panel h3{padding:11px 14px;border-bottom:1px solid var(--border);font-size:12px;
    text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600}
  table{width:100%;border-collapse:collapse}
  th,td{padding:8px 14px;text-align:left;font-size:12px;border-bottom:1px solid #131c28}
  th{color:var(--muted);font-weight:500;font-size:11px;text-transform:uppercase}
  tbody tr:hover{background:var(--panel2)}
  .pos{color:var(--green)} .neg{color:var(--red)}
  .empty{padding:24px;text-align:center;color:var(--muted)}
  .spark{height:22px}

  .logs{padding:10px 14px;max-height:280px;overflow-y:auto;font-size:12px}
  .logline{padding:2px 0;white-space:nowrap}
  .logline .t{color:var(--muted);margin-right:8px}
  .lvl-TRADE{color:var(--cyan)} .lvl-TP{color:var(--green)} .lvl-SL{color:var(--red)}
  .lvl-WARN{color:var(--yellow)} .lvl-ERROR{color:var(--red)} .lvl-INFO{color:var(--txt)}

  .scan-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
  @media(max-width:1000px){.scan-grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}}
  .badge{display:inline-block;padding:1px 7px;border-radius:4px;font-size:11px;font-weight:600}
  .score-hi{background:#16301d;color:var(--green)}
  .score-mid{background:#302816;color:var(--yellow)}
  .score-lo{background:#2a2a2a;color:var(--muted)}
  .prog{height:6px;background:var(--panel2);border-radius:3px;overflow:hidden;margin-top:3px}
  .prog>i{display:block;height:100%;background:linear-gradient(90deg,var(--yellow),var(--green))}

  form{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  @media(max-width:800px){form{grid-template-columns:1fr}}
  fieldset{border:1px solid var(--border);border-radius:8px;padding:14px;background:var(--panel)}
  legend{padding:0 8px;color:var(--accent);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
  .field{margin-bottom:10px}
  .field label{display:block;color:var(--muted);font-size:11px;margin-bottom:3px}
  .field input[type=text],.field input[type=password],.field input[type=number]{
    width:100%;padding:8px 10px;background:var(--bg);border:1px solid var(--border);
    border-radius:6px;color:var(--txt);font-family:inherit;font-size:12px}
  .field input:focus{outline:none;border-color:var(--accent2)}
  select{width:100%;padding:8px 10px;background:var(--bg);border:1px solid var(--border);
    border-radius:6px;color:var(--txt);font-family:inherit;font-size:12px}
  .orsep{text-align:center;color:var(--muted);font-size:11px;margin:8px 0}
  .derive-result{margin-top:8px;font-size:11px}
  .derive-result .dhint{color:var(--yellow);margin-bottom:5px}
  .derive-result .daddr{background:var(--bg);border:1px solid var(--border);border-radius:6px;
    padding:7px 9px;margin-bottom:5px}
  .derive-result code{color:var(--accent2);word-break:break-all;font-size:11px}
  .derive-result .t{color:var(--muted)}
  .check{display:flex;align-items:center;gap:8px;margin-bottom:8px}
  .check input{width:16px;height:16px;accent-color:var(--accent)}
  .save-row{grid-column:1/-1;display:flex;gap:10px;align-items:center}
  .hint{color:var(--muted);font-size:11px;margin-top:2px}
  .toast{position:fixed;bottom:20px;right:20px;padding:12px 18px;border-radius:8px;
    background:var(--panel2);border:1px solid var(--accent);color:#fff;opacity:0;transition:.3s;z-index:50}
  .toast.show{opacity:1}
  .disclaimer{background:#2a1f0a;border:1px solid #3a2f12;color:var(--yellow);
    padding:10px 14px;border-radius:8px;font-size:11px;margin-bottom:14px}
</style>
</head>
<body>
<header>
  <div class="logo">COPY<span>·</span>TRADE <span>TERMINAL</span></div>
  <div class="pills" id="pills"></div>
  <div class="spacer"></div>
  <button class="btn go" id="btnStart" onclick="ctl('start')">▶ Start</button>
  <button class="btn warn" id="btnPause" onclick="togglePause()">⏸ Pause</button>
  <button class="btn stop" id="btnStop" onclick="ctl('stop')">■ Stop</button>
</header>

<nav>
  <button class="active" data-tab="dash" onclick="tab('dash')">Dashboard</button>
  <button data-tab="scan" onclick="tab('scan')">Call-Bot</button>
  <button data-tab="set" onclick="tab('set')">Einstellungen</button>
</nav>

<main>
  <!-- DASHBOARD -->
  <section class="tab active" id="dash">
    <div class="stats">
      <div class="stat"><div class="label">Trades</div><div class="val" id="s-trades">0</div></div>
      <div class="stat"><div class="label">Gesamt P&L</div><div class="val" id="s-pnl">$0</div></div>
      <div class="stat"><div class="label">Take-Profit Hits</div><div class="val pos" id="s-tp">0</div></div>
      <div class="stat"><div class="label">Stop-Loss Hits</div><div class="val neg" id="s-sl">0</div></div>
    </div>
    <div class="panel">
      <h3>Offene Positionen</h3>
      <table>
        <thead><tr><th>Token</th><th>Chain</th><th>Entry</th><th>Aktuell</th>
          <th>P&L %</th><th>P&L $</th><th>TP</th><th>SL</th><th>Verlauf</th><th>KI-Grund</th></tr></thead>
        <tbody id="positions"><tr><td colspan="10" class="empty">Keine offenen Positionen</td></tr></tbody>
      </table>
    </div>
    <div class="panel">
      <h3>Live-Log</h3>
      <div class="logs" id="logs"><div class="empty">Warte auf Aktivität…</div></div>
    </div>
  </section>

  <!-- CALL-BOT -->
  <section class="tab" id="scan">
    <div class="disclaimer">⚠ Der Call-Bot ist eine Heuristik, keine Anlageberatung. Memecoins & Pre-Bonding-Token sind extrem riskant. Letztes Update: <span id="scanTime">—</span></div>
    <div class="scan-grid">
      <div class="panel">
        <h3>🔥 Pre-Bonding (kurz vor Migration)</h3>
        <table><thead><tr><th>Token</th><th>Fortschritt</th><th>MCap</th></tr></thead>
          <tbody id="pre_bonding"><tr><td colspan="3" class="empty">Lädt…</td></tr></tbody></table>
      </div>
      <div class="panel">
        <h3>✨ Neue Pairs</h3>
        <table><thead><tr><th>Token</th><th>Liq.</th><th>Score</th></tr></thead>
          <tbody id="new_pairs"><tr><td colspan="3" class="empty">Lädt…</td></tr></tbody></table>
      </div>
      <div class="panel">
        <h3>📈 Trending (1h)</h3>
        <table><thead><tr><th>Token</th><th>1h %</th><th>Score</th></tr></thead>
          <tbody id="trending"><tr><td colspan="3" class="empty">Lädt…</td></tr></tbody></table>
      </div>
    </div>
  </section>

  <!-- SETTINGS -->
  <section class="tab" id="set">
    <form id="cfgForm" onsubmit="return false">
      <fieldset>
        <legend>Solana</legend>
        <div class="field"><label>RPC URL (Helius)</label><input type="text" name="SOLANA_RPC_URL"></div>
        <div class="field"><label>WebSocket URL (wss://…)</label><input type="text" name="SOLANA_WS_URL"></div>
        <div class="field"><label>Private Key (Base58) — leer lassen wenn Recovery Phrase</label><input type="password" name="SOLANA_PRIVATE_KEY"></div>
        <div class="orsep">— ODER —</div>
        <div class="field"><label>Recovery Phrase (12 / 24 Wörter)</label><input type="password" name="SOLANA_MNEMONIC"></div>
        <div class="field"><label>Ableitungspfad</label>
          <select name="SOLANA_DERIVATION_PATH">
            <option value="m/44'/501'/0'/0'">Phantom (Standard)</option>
            <option value="m/44'/501'/0'">Solflare / Account-Pfad</option>
          </select>
        </div>
        <button class="btn" type="button" onclick="deriveAddr('SOL')">🔍 Adresse aus Phrase prüfen</button>
        <div class="derive-result" id="derive-SOL"></div>
        <div class="field" style="margin-top:10px"><label>Ziel-Wallet (z.B. Cented)</label><input type="text" name="TARGET_WALLET_SOL"></div>
        <div class="check"><input type="checkbox" name="ENABLE_SOL"><label>Solana Copy-Trading aktiv</label></div>
      </fieldset>

      <fieldset>
        <legend>Ethereum</legend>
        <div class="field"><label>RPC URL (Alchemy)</label><input type="text" name="ETH_RPC_URL"></div>
        <div class="field"><label>WebSocket URL (wss://…)</label><input type="text" name="ETH_WS_URL"></div>
        <div class="field"><label>Private Key (0x…) — leer lassen wenn Recovery Phrase</label><input type="password" name="ETH_PRIVATE_KEY"></div>
        <div class="orsep">— ODER —</div>
        <div class="field"><label>Recovery Phrase (12 / 24 Wörter)</label><input type="password" name="ETH_MNEMONIC"></div>
        <button class="btn" type="button" onclick="deriveAddr('ETH')">🔍 Adresse aus Phrase prüfen</button>
        <div class="derive-result" id="derive-ETH"></div>
        <div class="field" style="margin-top:10px"><label>Ziel-Wallet</label><input type="text" name="TARGET_WALLET_ETH"></div>
        <div class="check"><input type="checkbox" name="ENABLE_ETH"><label>Ethereum Copy-Trading aktiv</label></div>
      </fieldset>

      <fieldset>
        <legend>KI & Telegram</legend>
        <div class="field"><label>Anthropic API Key (dynamisches TP/SL)</label><input type="password" name="ANTHROPIC_API_KEY"></div>
        <div class="field"><label>Telegram Bot Token (optional)</label><input type="password" name="TELEGRAM_BOT_TOKEN"></div>
        <div class="field"><label>Telegram Chat-ID</label><input type="text" name="TELEGRAM_CHAT_ID"></div>
      </fieldset>

      <fieldset>
        <legend>Call-Bot / Scanner</legend>
        <div class="field"><label>Moralis API Key (beste Pre-Bonding-Daten, optional)</label><input type="password" name="MORALIS_API_KEY"></div>
        <div class="field"><label>Birdeye API Key (optional)</label><input type="password" name="BIRDEYE_API_KEY"></div>
        <div class="field"><label>Min. Liquidität ($)</label><input type="number" name="MIN_LIQUIDITY_USD"></div>
        <div class="field"><label>Min. Volumen 24h ($)</label><input type="number" name="MIN_VOLUME_USD"></div>
        <div class="check"><input type="checkbox" name="ENABLE_SCANNER"><label>Call-Bot aktiv</label></div>
      </fieldset>

      <fieldset>
        <legend>Trading-Filter</legend>
        <div class="field"><label>Max. Trade-Größe (SOL)</label><input type="number" step="0.01" name="MAX_TRADE_SOL"></div>
        <div class="field"><label>Max. Trade-Größe (ETH)</label><input type="number" step="0.001" name="MAX_TRADE_ETH"></div>
        <div class="field"><label>Slippage (Basispunkte, 50 = 0.5%)</label><input type="number" name="SLIPPAGE_BPS"></div>
        <div class="check"><input type="checkbox" name="DRY_RUN"><label>DRY RUN (Simulation — kein echter Handel)</label>
        </div>
        <div class="hint">Zum Testen anlassen. Zum echten Handeln deaktivieren.</div>
      </fieldset>

      <div class="save-row">
        <button class="btn go" type="button" onclick="saveCfg()">💾 Speichern</button>
        <span class="hint" id="cfgHint">Keys werden lokal in .env gespeichert.</span>
      </div>
    </form>
  </section>
</main>

<div class="toast" id="toast"></div>

<script>
const SECRETS=["SOLANA_PRIVATE_KEY","SOLANA_MNEMONIC","ETH_PRIVATE_KEY","ETH_MNEMONIC","ANTHROPIC_API_KEY","TELEGRAM_BOT_TOKEN","MORALIS_API_KEY","BIRDEYE_API_KEY"];
const BOOLS=["ENABLE_SOL","ENABLE_ETH","ENABLE_SCANNER","DRY_RUN"];
let paused=false;

function tab(id){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  document.querySelector('nav button[data-tab="'+id+'"]').classList.add('active');
}

function toast(msg,ok=true){
  const t=document.getElementById('toast');
  t.textContent=msg; t.style.borderColor=ok?'#3fb950':'#f85149';
  t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),2600);
}

async function loadCfg(){
  const r=await fetch('/api/config'); const c=await r.json();
  for(const k in c){
    const el=document.querySelector('[name="'+k+'"]'); if(!el)continue;
    if(BOOLS.includes(k)) el.checked=(c[k]===true||c[k]==='true');
    else if(c[k]!=='' && c[k]!=null) el.value=c[k];
  }
}

async function deriveAddr(chain){
  const name = chain==='SOL' ? 'SOLANA_MNEMONIC' : 'ETH_MNEMONIC';
  const mnemonic = document.querySelector('[name="'+name+'"]').value;
  const box = document.getElementById('derive-'+chain);
  if(!mnemonic || mnemonic==='********'){ box.innerHTML='<span class="neg">Bitte Recovery Phrase eingeben.</span>'; return; }
  box.innerHTML='Prüfe…';
  const r = await fetch('/api/derive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chain,mnemonic})});
  const res = await r.json();
  if(!res.ok){ box.innerHTML='<span class="neg">'+res.error+'</span>'; return; }
  box.innerHTML='<div class="dhint">⚠ Vergleiche mit deiner echten Wallet-Adresse! Eine davon muss exakt passen:</div>'+
    res.addresses.map(a=>'<div class="daddr"><b>'+a.label+'</b> <span class="t">'+a.path+'</span><br><code>'+a.address+'</code></div>').join('');
}

async function saveCfg(){
  const form=document.getElementById('cfgForm'); const data={};
  new FormData(form).forEach((v,k)=>{data[k]=v;});
  BOOLS.forEach(k=>{const el=form.querySelector('[name="'+k+'"]'); data[k]=el.checked;});
  // Maskierte Secrets nur senden wenn geändert
  SECRETS.forEach(k=>{const el=form.querySelector('[name="'+k+'"]'); if(el && el.value==='********') delete data[k];});
  const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const res=await r.json();
  if(res.ok) toast('Einstellungen gespeichert ✓');
  else toast('Fehler: '+(res.error||''),false);
}

async function ctl(action){
  const r=await fetch('/api/'+action,{method:'POST'});
  const res=await r.json();
  if(res.ok) toast(action==='start'?'Bot gestartet ▶':'Bot gestoppt ■', action!=='stop');
  else toast(res.error||'Fehler',false);
}
async function togglePause(){
  paused=!paused;
  await fetch('/api/'+(paused?'pause':'resume'),{method:'POST'});
  document.getElementById('btnPause').textContent=paused?'▶ Resume':'⏸ Pause';
  toast(paused?'Pausiert':'Fortgesetzt');
}

function fmt(n,d=2){return Number(n).toLocaleString('de-DE',{minimumFractionDigits:d,maximumFractionDigits:d});}
function fmtUsd(n){return (n<0?'-$':'$')+fmt(Math.abs(n),2);}
function cls(n){return n>0?'pos':(n<0?'neg':'');}
function scoreBadge(s){const c=s>=60?'score-hi':(s>=35?'score-mid':'score-lo');return '<span class="badge '+c+'">'+s+'</span>';}

function sparkline(arr){
  if(!arr||arr.length<2)return '';
  const w=80,h=22,min=Math.min(...arr),max=Math.max(...arr),rng=(max-min)||1;
  const pts=arr.map((v,i)=>(i/(arr.length-1)*w)+','+(h-((v-min)/rng)*h)).join(' ');
  const up=arr[arr.length-1]>=arr[0];
  return '<svg class="spark" width="'+w+'" height="'+h+'"><polyline fill="none" stroke="'+(up?'#3fb950':'#f85149')+'" stroke-width="1.5" points="'+pts+'"/></svg>';
}

function render(d){
  // Status-Pills
  const st=d.status;
  const pills=[];
  pills.push('<span class="pill '+(st.active?'on':'off')+'">'+(st.active?'● AKTIV':'○ GESTOPPT')+'</span>');
  if(st.paused) pills.push('<span class="pill dry">⏸ PAUSIERT</span>');
  pills.push('<span class="pill '+(st.dry_run?'dry':'live')+'">'+(st.dry_run?'DRY RUN':'● LIVE')+'</span>');
  pills.push('<span class="pill '+(st.enable_sol?'on':'off')+'">SOL</span>');
  pills.push('<span class="pill '+(st.enable_eth?'on':'off')+'">ETH</span>');
  pills.push('<span class="pill '+(st.enable_scanner?'on':'off')+'">SCAN</span>');
  document.getElementById('pills').innerHTML=pills.join('');

  document.getElementById('s-trades').textContent=st.total_trades;
  const pnlEl=document.getElementById('s-pnl');
  pnlEl.textContent=fmtUsd(st.total_pnl_usd); pnlEl.className='val '+cls(st.total_pnl_usd);
  document.getElementById('s-tp').textContent=st.tp_hits;
  document.getElementById('s-sl').textContent=st.sl_hits;

  // Positionen
  const pb=document.getElementById('positions');
  if(!d.positions.length){pb.innerHTML='<tr><td colspan="10" class="empty">Keine offenen Positionen</td></tr>';}
  else{
    pb.innerHTML=d.positions.map(p=>{
      const hist=d.price_history[p.symbol]||[];
      return '<tr><td><b>'+p.symbol+'</b></td><td>'+p.chain+'</td>'+
        '<td>$'+fmt(p.entry_price,6)+'</td><td>$'+fmt(p.current_price,6)+'</td>'+
        '<td class="'+cls(p.pnl_pct)+'">'+(p.pnl_pct>0?'+':'')+fmt(p.pnl_pct,1)+'%</td>'+
        '<td class="'+cls(p.pnl_usd)+'">'+fmtUsd(p.pnl_usd)+'</td>'+
        '<td class="pos">+'+fmt(p.tp_pct,0)+'%</td><td class="neg">-'+fmt(p.sl_pct,0)+'%</td>'+
        '<td>'+sparkline(hist)+'</td>'+
        '<td style="color:var(--muted);max-width:240px;white-space:normal">'+(p.reasoning||'')+'</td></tr>';
    }).join('');
  }

  // Logs
  const lb=document.getElementById('logs');
  if(d.logs.length){
    lb.innerHTML=d.logs.slice().reverse().map(l=>
      '<div class="logline"><span class="t">'+l.time+'</span><span class="lvl-'+l.level+'">['+l.level+']</span> '+l.message+'</div>'
    ).join('');
  }

  // Scanner
  document.getElementById('scanTime').textContent=d.scanner_updated||'—';
  renderScan('pre_bonding',d.scanner.pre_bonding,'prebond');
  renderScan('new_pairs',d.scanner.new_pairs,'score');
  renderScan('trending',d.scanner.trending,'trend');
}

function renderScan(id,rows,type){
  const tb=document.getElementById(id);
  if(!rows||!rows.length){tb.innerHTML='<tr><td colspan="3" class="empty">Nichts gefunden</td></tr>';return;}
  tb.innerHTML=rows.map(r=>{
    const link=r.link?'<a href="'+r.link+'" target="_blank">'+r.symbol+'</a>':r.symbol;
    if(type==='prebond'){
      return '<tr><td><b>'+link+'</b></td><td style="width:120px">'+fmt(r.progress,0)+'%'+
        '<div class="prog"><i style="width:'+Math.min(100,r.progress)+'%"></i></div></td>'+
        '<td>$'+fmt(r.mcap,0)+'</td></tr>';
    } else if(type==='trend'){
      return '<tr><td><b>'+link+'</b></td><td class="'+cls(r.change_1h)+'">'+(r.change_1h>0?'+':'')+fmt(r.change_1h,1)+'%</td>'+
        '<td>'+scoreBadge(r.score)+'</td></tr>';
    } else {
      return '<tr><td><b>'+link+'</b></td><td>$'+fmt(r.liquidity,0)+'</td><td>'+scoreBadge(r.score)+'</td></tr>';
    }
  }).join('');
}

function connect(){
  const ws=new WebSocket((location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/ws');
  ws.onmessage=e=>render(JSON.parse(e.data));
  ws.onclose=()=>setTimeout(connect,2000);
}

loadCfg(); connect();
</script>
</body>
</html>
"""
