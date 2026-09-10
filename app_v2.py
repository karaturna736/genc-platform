import sqlite3, hashlib, secrets
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title='G.E.N.C Live v2')
DB = Path('/tmp/genc_live.db')

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,password TEXT,role TEXT);
    CREATE TABLE IF NOT EXISTS students(user_id INTEGER PRIMARY KEY,first_name TEXT,last_name TEXT,birth_date TEXT,city TEXT,education TEXT,school TEXT,department TEXT,field TEXT,bio TEXT);
    CREATE TABLE IF NOT EXISTS companies(user_id INTEGER PRIMARY KEY,legal_name TEXT,trade_name TEXT,company_type TEXT,sector TEXT,tax_number TEXT,mersis TEXT,city TEXT,authorized_name TEXT,official_email TEXT,status TEXT DEFAULT 'pending');
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER);
    ''')
    return c

def hp(p):
    return hashlib.sha256(('genc-live-v2:' + p).encode()).hexdigest()

def auth(t):
    with db() as c:
        r = c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?',(t,)).fetchone()
        return dict(r) if r else None

class StudentIn(BaseModel):
    email:str
    password:str
    first_name:str
    last_name:str
    birth_date:str
    city:str
    education:str
    school:str=''
    department:str=''
    field:str
    bio:str=''

class CompanyIn(BaseModel):
    password:str
    legal_name:str
    trade_name:str=''
    company_type:str
    sector:str
    tax_number:str=''
    mersis:str=''
    city:str
    authorized_name:str
    official_email:str

class LoginIn(BaseModel):
    email:str
    password:str
    role:str

@app.get('/api/health')
def health():
    return {'ok':True,'version':'v2'}

@app.post('/api/student/register')
def student_register(d:StudentIn):
    if len(d.password) < 8:
        raise HTTPException(400,'Şifre en az 8 karakter olmalı.')
    try:
        with db() as c:
            cur = c.execute('INSERT INTO users(email,password,role) VALUES(?,?,?)',(d.email.lower(),hp(d.password),'student'))
            uid = cur.lastrowid
            c.execute('INSERT INTO students VALUES(?,?,?,?,?,?,?,?,?,?)',(uid,d.first_name,d.last_name,d.birth_date,d.city,d.education,d.school,d.department,d.field,d.bio))
            tok = secrets.token_urlsafe(32)
            c.execute('INSERT INTO sessions VALUES(?,?)',(tok,uid))
        return {'token':tok,'role':'student'}
    except sqlite3.IntegrityError:
        raise HTTPException(409,'Bu e-posta zaten kayıtlı.')

@app.post('/api/company/register')
def company_register(d:CompanyIn):
    if len(d.password) < 8:
        raise HTTPException(400,'Şifre en az 8 karakter olmalı.')
    try:
        with db() as c:
            cur = c.execute('INSERT INTO users(email,password,role) VALUES(?,?,?)',(d.official_email.lower(),hp(d.password),'company'))
            uid = cur.lastrowid
            c.execute('INSERT INTO companies(user_id,legal_name,trade_name,company_type,sector,tax_number,mersis,city,authorized_name,official_email,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid,d.legal_name,d.trade_name,d.company_type,d.sector,d.tax_number,d.mersis,d.city,d.authorized_name,d.official_email,'pending'))
            tok = secrets.token_urlsafe(32)
            c.execute('INSERT INTO sessions VALUES(?,?)',(tok,uid))
        return {'token':tok,'role':'company'}
    except sqlite3.IntegrityError:
        raise HTTPException(409,'Bu e-posta zaten kayıtlı.')

@app.post('/api/login')
def login(d:LoginIn):
    with db() as c:
        u = c.execute('SELECT * FROM users WHERE lower(email)=lower(?) AND password=? AND role=?',(d.email,hp(d.password),d.role)).fetchone()
        if not u:
            raise HTTPException(401,'E-posta veya şifre hatalı.')
        tok = secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions VALUES(?,?)',(tok,u['id']))
    return {'token':tok,'role':d.role}

@app.get('/api/me')
def me(token:str):
    u = auth(token)
    if not u:
        raise HTTPException(401,'Oturum geçersiz.')
    with db() as c:
        if u['role'] == 'student':
            p = c.execute('SELECT * FROM students WHERE user_id=?',(u['id'],)).fetchone()
        else:
            p = c.execute('SELECT * FROM companies WHERE user_id=?',(u['id'],)).fetchone()
    return {'user':u,'profile':dict(p) if p else None}

HTML = r'''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#071019"><title>G.E.N.C</title><style>
:root{--bg:#071019;--card:#0e1b28;--card2:#112434;--text:#f3f7f7;--muted:#92a6b6;--line:rgba(255,255,255,.09);--a:#68e3c4}*{box-sizing:border-box}body{margin:0;background:radial-gradient(900px 600px at 10% -10%,rgba(104,227,196,.09),transparent 60%),var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif;min-height:100vh}button,input,select,textarea{font:inherit}a{text-decoration:none;color:inherit}.wrap{width:min(1180px,calc(100% - 36px));margin:auto}.brand{font-weight:900;letter-spacing:.18em;cursor:pointer}.brand b{color:var(--a)}.hero{min-height:100vh;display:flex;flex-direction:column}.head{height:78px;display:flex;align-items:center;justify-content:space-between}.main{flex:1;display:flex;align-items:center}.ey{color:var(--a);font-size:12px;font-weight:900;letter-spacing:.2em;text-transform:uppercase}.hero h1{font-size:clamp(50px,8vw,94px);line-height:.96;letter-spacing:-.06em;margin:18px 0}.hero h1 em{color:var(--a);font-style:normal}.hero p{max-width:650px;color:#b8c7d1;font-size:18px;line-height:1.7}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:28px}.btn{border:0;border-radius:12px;padding:12px 16px;background:var(--a);color:#06211a;font-weight:900;cursor:pointer}.btn.alt{background:#14283a;color:var(--text);border:1px solid var(--line)}.btn.ghost{background:transparent;color:var(--muted);border:1px solid var(--line)}.values{border-top:1px solid var(--line);min-height:78px;display:flex;align-items:center;gap:12px;color:#c5d1d9}.values b{color:var(--a)}.auth{min-height:100vh;display:grid;grid-template-columns:.9fr 1.1fr}.aside{padding:55px;border-right:1px solid var(--line);display:flex;flex-direction:column;justify-content:space-between}.aside h1{font-size:clamp(38px,5vw,66px);line-height:1.02;letter-spacing:-.05em}.aside p{color:var(--muted);line-height:1.7}.pane{display:flex;align-items:center;justify-content:center;padding:38px}.card{width:min(680px,100%);background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:20px;padding:28px}.card h2{font-size:32px;letter-spacing:-.04em}.form{display:grid;gap:15px}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.field{display:grid;gap:7px}.field label{font-size:13px;color:#c7d2da;font-weight:800}.in{width:100%;background:#08131e;border:1px solid rgba(255,255,255,.12);border-radius:11px;padding:13px 14px;color:var(--text);outline:none}.in:focus{border-color:rgba(104,227,196,.65)}.muted{color:var(--muted)}.dash{padding:40px 0 90px}.top{position:sticky;top:0;z-index:20;background:rgba(7,16,25,.92);backdrop-filter:blur(16px);border-bottom:1px solid var(--line)}.topin{min-height:68px;display:flex;align-items:center;justify-content:space-between;gap:16px}.top-left{display:flex;align-items:center;gap:22px}.nav{display:flex;gap:5px;align-items:center}.nav button{border:0;background:transparent;color:var(--muted);padding:9px 11px;border-radius:9px;font-weight:800;cursor:pointer}.nav button:hover,.nav button.active{background:rgba(255,255,255,.05);color:var(--text)}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.box{background:var(--card);border:1px solid var(--line);border-radius:17px;padding:22px}.box small{color:var(--muted);font-weight:800}.box strong{display:block;font-size:28px;margin-top:10px}.notice{padding:15px;border-radius:13px;border:1px solid rgba(104,227,196,.22);background:rgba(104,227,196,.06);color:#bdd7cf}.toast{position:fixed;z-index:50;right:20px;top:20px;background:#102538;border:1px solid rgba(104,227,196,.24);padding:13px 15px;border-radius:12px;display:none}.toast.show{display:block}.section{margin-top:28px}.panel-title{font-size:clamp(34px,5vw,52px);letter-spacing:-.045em;margin:10px 0}.mobile-home{display:none}.user-pill{font-size:13px;color:var(--muted)}
@media(max-width:850px){.auth{grid-template-columns:1fr}.aside{min-height:300px;border-right:0;border-bottom:1px solid var(--line);padding:30px}.pane{padding:24px 16px}.grid,.row{grid-template-columns:1fr}.head{height:68px}.hero p{font-size:16px}.actions{flex-direction:column}.nav{display:none}.mobile-home{display:inline-flex}.topin{min-height:66px}.user-pill{display:none}}
</style></head><body><div id="app"></div><div id="toast" class="toast"></div><script>
let token=localStorage.genc_token||'',role=localStorage.genc_role||'';const A=document.getElementById('app');
function go(x){location.hash=x}function path(){return location.hash.slice(1)||'/'}function toast(m){let x=document.getElementById('toast');x.textContent=m;x.classList.add('show');setTimeout(()=>x.classList.remove('show'),2500)}
async function api(u,o={}){o.headers={'Content-Type':'application/json',...(o.headers||{})};let r=await fetch('/api'+u,o),d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'İşlem başarısız');return d}
function brand(toDashboard=false){return `<span class="brand" onclick="go('${toDashboard?'/dashboard':'/'}')">G.E.N<b>.C</b></span>`}
function home(){if(token&&role){return `<main class="hero"><div class="wrap head">${brand(true)}<button class="btn" onclick="go('/dashboard')">Ana Panele Dön →</button></div><div class="wrap main"><div><div class="ey">Oturum açık</div><h1>G.E.N.C’e<br><em>devam et.</em></h1><p>Hesabın açık. Kariyer veya şirket paneline kaldığın yerden devam edebilirsin.</p><div class="actions"><button class="btn" onclick="go('/dashboard')">Ana Panel →</button><button class="btn alt" onclick="out()">Çıkış yap</button></div></div></div><div class="wrap values"><span>Gerçek görevler</span><b>•</b><span>Doğrulanabilir beceriler</span><b>•</b><span>Kariyer profili</span></div></main>`}return `<main class="hero"><div class="wrap head">${brand(false)}<div class="actions" style="margin:0"><button class="btn alt" onclick="go('/student/login')">Öğrenci Girişi</button><button class="btn alt" onclick="go('/company/login')">Şirket Girişi</button></div></div><div class="wrap main"><div><div class="ey">Kariyer ve deneyim platformu</div><h1>Deneyimin yoksa,<br><em>burada kazan.</em></h1><p>Gerçek iş senaryolarında kendini geliştir. Yeteneklerini kanıtla. Kariyer profilini oluşturmaya başla.</p><div class="actions"><button class="btn" onclick="go('/student/register')">Öğrenci olarak başla →</button><button class="btn alt" onclick="go('/company/register')">Şirket olarak devam et →</button></div></div></div><div class="wrap values"><span>Gerçek görevler</span><b>•</b><span>Doğrulanabilir beceriler</span><b>•</b><span>Kariyer profili</span></div></main>`}
function shell(kind,inside){let student=kind==='student';return `<main class="auth"><aside class="aside"><div>${brand(false)}<h1>${student?'Kariyerini CV’den önce işinle göster.':'CV yığınını değil, gerçek performansı değerlendir.'}</h1><p>${student?'Ad-soyad, eğitim ve kariyer bilgilerinle profesyonel profilini oluştur.':'Kurumsal bilgilerin doğrulandıktan sonra gerçek görev yayınla ve adayları iş çıktıları üzerinden değerlendir.'}</p></div><p>G.E.N.C · Doğrulanabilir deneyim altyapısı</p></aside><section class="pane">${inside}</section></main>`}
function sreg(){return shell('student',`<div class="card"><div class="ey">Öğrenci Kaydı</div><h2>Profilini profesyonel şekilde oluştur.</h2><form class="form" onsubmit="student(event)"><div class="row"><div class="field"><label>Ad</label><input id="fn" class="in" required></div><div class="field"><label>Soyad</label><input id="ln" class="in" required></div></div><div class="row"><div class="field"><label>Doğum tarihi</label><input id="bd" type="date" class="in" required></div><div class="field"><label>Şehir</label><input id="city" class="in" required></div></div><div class="row"><div class="field"><label>Eğitim durumu</label><select id="edu" class="in"><option>Lise</option><option>Önlisans</option><option>Lisans</option><option>Mezun</option></select></div><div class="field"><label>Okul / Üniversite</label><input id="school" class="in"></div></div><div class="row"><div class="field"><label>Bölüm</label><input id="dep" class="in"></div><div class="field"><label>Ana kariyer alanı</label><select id="field" class="in"><option>Yazılım & Teknoloji</option><option>Tasarım & UI/UX</option><option>Pazarlama & Satış</option><option>Veri & Finans</option><option>Denizcilik</option><option>Girişimcilik</option></select></div></div><div class="field"><label>E-posta</label><input id="email" type="email" class="in" required></div><div class="field"><label>Şifre</label><input id="pw" type="password" minlength="8" class="in" required></div><div class="field"><label>Kısa bio</label><textarea id="bio" class="in"></textarea></div><button class="btn">Hesabımı oluştur</button><button type="button" class="btn alt" onclick="go('/')">← Ana sayfa</button></form></div>`)}
function creg(){return shell('company',`<div class="card"><div class="ey">Şirket Kaydı</div><h2>Resmi şirket başvurusu.</h2><form class="form" onsubmit="company(event)"><div class="field"><label>Ticari unvan</label><input id="legal" class="in" required></div><div class="row"><div class="field"><label>Marka adı</label><input id="trade" class="in"></div><div class="field"><label>Şirket türü</label><select id="ctype" class="in"><option>A.Ş.</option><option>Ltd. Şti.</option><option>Şahıs</option><option>Diğer</option></select></div></div><div class="row"><div class="field"><label>Sektör</label><input id="sector" class="in" required></div><div class="field"><label>Şehir</label><input id="ccity" class="in" required></div></div><div class="row"><div class="field"><label>Vergi numarası</label><input id="tax" class="in"></div><div class="field"><label>MERSİS</label><input id="mersis" class="in"></div></div><div class="field"><label>Yetkili ad soyad</label><input id="authname" class="in" required></div><div class="field"><label>Kurumsal e-posta</label><input id="cemail" type="email" class="in" required></div><div class="field"><label>Şifre</label><input id="cpw" type="password" minlength="8" class="in" required></div><div class="notice">Başvuru sonrası hesap “Doğrulama bekleniyor” durumuna alınır. Doğrulanmadan gerçek şirket görevi yayınlanmaz.</div><button class="btn">Başvuruyu tamamla</button><button type="button" class="btn alt" onclick="go('/')">← Ana sayfa</button></form></div>`)}
function login(kind){return shell(kind,`<div class="card"><div class="ey">${kind==='student'?'Öğrenci':'Şirket'} Girişi</div><h2>Tekrar hoş geldin.</h2><form class="form" onsubmit="log(event,'${kind}')"><div class="field"><label>E-posta</label><input id="le" type="email" class="in" required></div><div class="field"><label>Şifre</label><input id="lp" type="password" class="in" required></div><button class="btn">Giriş yap</button><button type="button" class="btn alt" onclick="go('/')">← Ana sayfa</button></form></div>`)}
async function student(e){e.preventDefault();try{let d=await api('/student/register',{method:'POST',body:JSON.stringify({email:email.value,password:pw.value,first_name:fn.value,last_name:ln.value,birth_date:bd.value,city:city.value,education:edu.value,school:school.value,department:dep.value,field:field.value,bio:bio.value})});token=d.token;role=d.role;localStorage.genc_token=token;localStorage.genc_role=role;go('/dashboard')}catch(e){toast(e.message)}}
async function company(e){e.preventDefault();try{let d=await api('/company/register',{method:'POST',body:JSON.stringify({password:cpw.value,legal_name:legal.value,trade_name:trade.value,company_type:ctype.value,sector:sector.value,tax_number:tax.value,mersis:mersis.value,city:ccity.value,authorized_name:authname.value,official_email:cemail.value})});token=d.token;role=d.role;localStorage.genc_token=token;localStorage.genc_role=role;go('/dashboard')}catch(e){toast(e.message)}}
async function log(e,k){e.preventDefault();try{let d=await api('/login',{method:'POST',body:JSON.stringify({email:le.value,password:lp.value,role:k})});token=d.token;role=d.role;localStorage.genc_token=token;localStorage.genc_role=role;go('/dashboard')}catch(e){toast(e.message)}}
function topbar(q){let label=role==='student'?(q.first_name+' '+q.last_name):(q.trade_name||q.legal_name);return `<header class="top"><div class="wrap topin"><div class="top-left">${brand(true)}<nav class="nav"><button class="active" onclick="go('/dashboard')">Ana Panel</button><button onclick="go('/tasks')">Görevler</button><button onclick="go('/profile')">Profil</button></nav></div><div style="display:flex;align-items:center;gap:9px"><span class="user-pill">${label}</span><button class="btn alt mobile-home" onclick="go('/dashboard')">Panel</button><button class="btn alt" onclick="out()">Çıkış</button></div></div></header>`}
async function loadProfile(){if(!token)throw Error('Oturum yok');return await api('/me?token='+encodeURIComponent(token))}
async function dashboard(){if(!token){go('/');return''}try{let d=await loadProfile(),q=d.profile;if(role==='student')return `${topbar(q)}<main class="dash"><div class="wrap"><div class="ey">Öğrenci Ana Paneli</div><h1 class="panel-title">${q.first_name} ${q.last_name}</h1><p class="muted">${q.city} · ${q.education} · ${q.field}</p><div class="grid"><div class="box"><small>G.E.N.C Score</small><strong style="font-size:20px">Henüz oluşmadı</strong></div><div class="box"><small>Doğrulanmış deneyim</small><strong>0</strong></div><div class="box"><small>Profil</small><strong>${q.school?'Güçlü':'Geliştir'}</strong></div></div><div class="section box"><h2>Sana uygun görevler</h2><p class="muted">Gerçek doğrulanmış şirket görevleri sisteme eklendikçe burada görünecek. Demo görevler doğrulanmış deneyim gibi gösterilmez.</p><button class="btn alt" onclick="go('/tasks')">Görev alanına git →</button></div></div></main>`;return `${topbar(q)}<main class="dash"><div class="wrap"><div class="ey">Şirket Ana Paneli</div><h1 class="panel-title">${q.trade_name||q.legal_name}</h1><p class="muted">${q.legal_name} · ${q.sector} · ${q.city}</p><div class="notice">Doğrulama durumu: <b>${q.status==='pending'?'Bekleniyor':q.status}</b></div><div class="grid section"><div class="box"><small>Yayındaki görev</small><strong>0</strong></div><div class="box"><small>Aday teslimi</small><strong>0</strong></div><div class="box"><small>Talent Radar</small><strong style="font-size:20px">Henüz boş</strong></div></div><div class="section box"><h2>Şirket çalışma alanı</h2><p class="muted">Görev ve aday akışları burada yönetilecek.</p><button class="btn alt" onclick="go('/tasks')">Görevlere git →</button></div></div></main>`}catch(e){out();return''}}
async function tasks(){if(!token){go('/');return''}try{let d=await loadProfile(),q=d.profile;return `${topbar(q)}<main class="dash"><div class="wrap"><div class="ey">Görevler</div><h1 class="panel-title">Görev Alanı</h1><div class="box"><h2>${role==='student'?'Uygun görevler':'Şirket görevleri'}</h2><p class="muted">${role==='student'?'Gerçek şirket görevleri eklendiğinde burada listelenecek.':'Şirket doğrulama ve görev yayınlama akışı sonraki geliştirme adımında bu alana bağlanacak.'}</p><button class="btn" onclick="go('/dashboard')">← Ana Panele Dön</button></div></div></main>`}catch(e){out();return''}}
async function profile(){if(!token){go('/');return''}try{let d=await loadProfile(),q=d.profile;if(role==='student')return `${topbar(q)}<main class="dash"><div class="wrap"><div class="ey">Profil</div><h1 class="panel-title">${q.first_name} ${q.last_name}</h1><div class="box"><p><b>Şehir:</b> ${q.city}</p><p><b>Eğitim:</b> ${q.education}</p><p><b>Okul:</b> ${q.school||'Belirtilmedi'}</p><p><b>Bölüm:</b> ${q.department||'Belirtilmedi'}</p><p><b>Kariyer alanı:</b> ${q.field}</p><p class="muted">${q.bio||'Henüz bio eklenmedi.'}</p><button class="btn" onclick="go('/dashboard')">← Ana Panele Dön</button></div></div></main>`;return `${topbar(q)}<main class="dash"><div class="wrap"><div class="ey">Şirket Profili</div><h1 class="panel-title">${q.trade_name||q.legal_name}</h1><div class="box"><p><b>Ticari unvan:</b> ${q.legal_name}</p><p><b>Sektör:</b> ${q.sector}</p><p><b>Şehir:</b> ${q.city}</p><p><b>Vergi no:</b> ${q.tax_number||'Belirtilmedi'}</p><p><b>MERSİS:</b> ${q.mersis||'Belirtilmedi'}</p><button class="btn" onclick="go('/dashboard')">← Ana Panele Dön</button></div></div></main>`}catch(e){out();return''}}
function out(){token='';role='';localStorage.removeItem('genc_token');localStorage.removeItem('genc_role');go('/')}
async function render(){let x=path(),h=x==='/'?home():x==='/student/register'?sreg():x==='/company/register'?creg():x==='/student/login'?login('student'):x==='/company/login'?login('company'):x==='/dashboard'?await dashboard():x==='/tasks'?await tasks():x==='/profile'?await profile():home();A.innerHTML=h;scrollTo(0,0)}
addEventListener('hashchange',render);addEventListener('DOMContentLoaded',()=>{if(token&&path()==='/')go('/dashboard');else render()})
</script></body></html>'''

@app.get('/',response_class=HTMLResponse)
def root():
    return HTML

@app.get('/{path:path}',response_class=HTMLResponse)
def fallback(path:str):
    return HTML
