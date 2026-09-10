import sqlite3
import secrets
from pydantic import BaseModel

import app_bridge
import app_v2

app = app_bridge.app

# Temporary Railway demo tables. Final production data lives in Supabase.
with app_v2.db() as c:
    c.executescript('''
    CREATE TABLE IF NOT EXISTS mentors(
      user_id INTEGER PRIMARY KEY,
      full_name TEXT NOT NULL,
      professional_title TEXT,
      organization TEXT,
      expertise TEXT,
      bio TEXT,
      linkedin_url TEXT,
      approval_status TEXT NOT NULL DEFAULT 'pending'
    );
    CREATE TABLE IF NOT EXISTS mentor_contents(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      mentor_user_id INTEGER NOT NULL,
      title TEXT NOT NULL,
      summary TEXT,
      content_type TEXT NOT NULL DEFAULT 'article',
      primary_field TEXT,
      body TEXT,
      resource_url TEXT,
      status TEXT NOT NULL DEFAULT 'pending_review',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    ''')

class MentorRegisterIn(BaseModel):
    email: str
    password: str
    full_name: str
    professional_title: str = ''
    organization: str = ''
    expertise: str = ''
    bio: str = ''
    linkedin_url: str = ''

class TokenIn(BaseModel):
    token: str

class MentorContentIn(BaseModel):
    token: str
    title: str
    summary: str = ''
    content_type: str = 'article'
    primary_field: str = ''
    body: str = ''
    resource_url: str = ''

@app.post('/api/mentor/register')
def mentor_register(d: MentorRegisterIn):
    if len(d.password) < 8:
        from fastapi import HTTPException
        raise HTTPException(400, 'Şifre en az 8 karakter olmalı.')
    try:
        with app_v2.db() as c:
            cur = c.execute(
                'INSERT INTO users(email,password,role) VALUES(?,?,?)',
                (d.email.lower(), app_v2.hp(d.password), 'mentor')
            )
            uid = cur.lastrowid
            c.execute(
                '''INSERT INTO mentors(user_id,full_name,professional_title,organization,expertise,bio,linkedin_url,approval_status)
                   VALUES(?,?,?,?,?,?,?,?)''',
                (uid,d.full_name,d.professional_title,d.organization,d.expertise,d.bio,d.linkedin_url,'pending')
            )
            tok = secrets.token_urlsafe(32)
            c.execute('INSERT INTO sessions VALUES(?,?)', (tok, uid))
        return {'token': tok, 'role': 'mentor'}
    except sqlite3.IntegrityError:
        from fastapi import HTTPException
        raise HTTPException(409, 'Bu e-posta zaten kayıtlı.')

@app.post('/api/mentor/me')
def mentor_me(d: TokenIn):
    from fastapi import HTTPException
    u = app_v2.auth(d.token)
    if not u or u['role'] != 'mentor':
        raise HTTPException(401, 'Oturum geçersiz.')
    with app_v2.db() as c:
        p = c.execute('SELECT * FROM mentors WHERE user_id=?', (u['id'],)).fetchone()
    return {'user': u, 'profile': dict(p) if p else None}

@app.post('/api/mentor/content')
def mentor_content(d: MentorContentIn):
    from fastapi import HTTPException
    u = app_v2.auth(d.token)
    if not u or u['role'] != 'mentor':
        raise HTTPException(401, 'Oturum geçersiz.')
    if not d.title.strip():
        raise HTTPException(400, 'Başlık gerekli.')
    with app_v2.db() as c:
        c.execute(
            '''INSERT INTO mentor_contents(mentor_user_id,title,summary,content_type,primary_field,body,resource_url,status)
               VALUES(?,?,?,?,?,?,?,?)''',
            (u['id'], d.title.strip(), d.summary.strip(), d.content_type, d.primary_field,
             d.body.strip(), d.resource_url.strip(), 'pending_review')
        )
    return {'ok': True, 'status': 'pending_review'}

@app.post('/api/mentor/contents/list')
def mentor_contents(d: TokenIn):
    from fastapi import HTTPException
    u = app_v2.auth(d.token)
    if not u or u['role'] != 'mentor':
        raise HTTPException(401, 'Oturum geçersiz.')
    with app_v2.db() as c:
        rows = c.execute(
            'SELECT id,title,content_type,primary_field,status,created_at FROM mentor_contents WHERE mentor_user_id=? ORDER BY id DESC',
            (u['id'],)
        ).fetchall()
    return {'items': [dict(r) for r in rows]}

html = app_v2.HTML

# Add the third role to the unauthenticated landing page.
html = html.replace(
    '<button class="btn alt" onclick="go(\'/company/login\')">Şirket Girişi</button>',
    '<button class="btn alt" onclick="go(\'/company/login\')">Şirket Girişi</button><button class="btn alt" onclick="go(\'/mentor/login\')">Eğitmen / Mentor</button>'
)
html = html.replace(
    '<button class="btn alt" onclick="go(\'/company/register\')">Şirket olarak devam et →</button>',
    '<button class="btn alt" onclick="go(\'/company/register\')">Şirket olarak devam et →</button><button class="btn alt" onclick="go(\'/mentor/register\')">Bilgini ücretsiz paylaş →</button>'
)

mentor_js = r'''
<script>
function mentorShell(inside){return `<main class="auth"><aside class="aside"><div>${brand(false)}<h1>Bilgini paylaş, gençlerin gelişimine katkı ver.</h1><p>Mentorlar ve eğitmenler öğrencilere ücretsiz, uygulamalı ve kaliteli içerikler sunar. İçerikler yayınlanmadan önce incelemeye alınır.</p></div><p>G.E.N.C · Ücretsiz gelişim ağı</p></aside><section class="pane">${inside}</section></main>`}
function mentorRegisterPage(){return mentorShell(`<div class="card"><div class="ey">Eğitmen / Mentor Kaydı</div><h2>Uzmanlığını G.E.N.C’e taşı.</h2><form class="form" onsubmit="mentorRegister(event)"><div class="field"><label>Ad soyad</label><input id="mname" class="in" required></div><div class="row"><div class="field"><label>Mesleki unvan</label><input id="mtitle" class="in" placeholder="Örn. Frontend Developer"></div><div class="field"><label>Kurum / şirket</label><input id="morg" class="in" placeholder="Opsiyonel"></div></div><div class="field"><label>Uzmanlık alanları</label><input id="mexpert" class="in" placeholder="Yazılım, UI/UX, finans..."></div><div class="field"><label>Kısa bio</label><textarea id="mbio" class="in"></textarea></div><div class="field"><label>LinkedIn</label><input id="mlink" class="in"></div><div class="field"><label>E-posta</label><input id="memail" type="email" class="in" required></div><div class="field"><label>Şifre</label><input id="mpw" type="password" minlength="8" class="in" required></div><div class="notice">Mentor hesabın önce doğrulanır. Öğrencilere sunulan içerikler ücretsizdir ve yayın öncesi incelemeye gönderilir.</div><button class="btn">Mentor hesabı oluştur</button><button type="button" class="btn alt" onclick="go('/')">← Ana sayfa</button></form></div>`)}
function mentorLoginPage(){return mentorShell(`<div class="card"><div class="ey">Eğitmen / Mentor Girişi</div><h2>Bilgi paylaşım alanına dön.</h2><form class="form" onsubmit="mentorLogin(event)"><div class="field"><label>E-posta</label><input id="mle" type="email" class="in" required></div><div class="field"><label>Şifre</label><input id="mlp" type="password" class="in" required></div><button class="btn">Giriş yap</button><button type="button" class="btn alt" onclick="go('/')">← Ana sayfa</button></form></div>`)}
async function mentorRegister(e){e.preventDefault();try{let d=await api('/mentor/register',{method:'POST',body:JSON.stringify({email:memail.value,password:mpw.value,full_name:mname.value,professional_title:mtitle.value,organization:morg.value,expertise:mexpert.value,bio:mbio.value,linkedin_url:mlink.value})});token=d.token;role='mentor';localStorage.genc_token=token;localStorage.genc_role=role;go('/dashboard')}catch(e){toast(e.message)}}
async function mentorLogin(e){e.preventDefault();try{let d=await api('/login',{method:'POST',body:JSON.stringify({email:mle.value,password:mlp.value,role:'mentor'})});token=d.token;role='mentor';localStorage.genc_token=token;localStorage.genc_role=role;go('/dashboard')}catch(e){toast(e.message)}}
function mentorTopbar(name){return `<header class="top"><div class="wrap topin"><div class="top-left">${brand(true)}<nav class="nav"><button class="active" onclick="go('/dashboard')">Mentor Paneli</button></nav></div><div style="display:flex;align-items:center;gap:9px"><span class="user-pill">${name}</span><button class="btn alt" onclick="out()">Çıkış</button></div></div></header>`}
async function mentorDashboard(){try{let d=await api('/mentor/me',{method:'POST',body:JSON.stringify({token})}),q=d.profile;setTimeout(loadMentorContents,0);return `${mentorTopbar(q.full_name)}<main class="dash"><div class="wrap"><div class="ey">Eğitmen / Mentor Paneli</div><h1 class="panel-title">${q.full_name}</h1><p class="muted">${q.professional_title||'Mentor'}${q.organization?' · '+q.organization:''}</p><div class="notice">Doğrulama durumu: <b>${q.approval_status==='pending'?'İnceleme bekliyor':q.approval_status}</b></div><div class="section box"><h2>Ücretsiz öğretici içerik ekle</h2><p class="muted">Amaç satış değil; öğrencinin gerçek bir beceri kazanmasına yardımcı olmak. Gönderiler yayın öncesi incelenir.</p><form class="form" onsubmit="mentorContentSubmit(event)"><div class="field"><label>Başlık</label><input id="ctitle" class="in" required></div><div class="row"><div class="field"><label>İçerik türü</label><select id="ctype2" class="in"><option value="article">Makale</option><option value="video">Video</option><option value="guide">Rehber</option><option value="resource">Kaynak</option><option value="mini_course">Mini eğitim</option></select></div><div class="field"><label>Alan</label><input id="cfield" class="in" placeholder="Örn. Yazılım & Teknoloji"></div></div><div class="field"><label>Kısa açıklama</label><textarea id="csummary" class="in"></textarea></div><div class="field"><label>İçerik / öğretici metin</label><textarea id="cbody" class="in" rows="7"></textarea></div><div class="field"><label>Kaynak veya video bağlantısı</label><input id="curl" class="in"></div><button class="btn">İncelemeye gönder</button></form></div><div class="section box"><h2>İçeriklerim</h2><div id="mentorContents" class="muted">Yükleniyor...</div></div></div></main>`}catch(e){out();return''}}
async function mentorContentSubmit(e){e.preventDefault();try{await api('/mentor/content',{method:'POST',body:JSON.stringify({token,title:ctitle.value,summary:csummary.value,content_type:ctype2.value,primary_field:cfield.value,body:cbody.value,resource_url:curl.value})});toast('İçerik incelemeye gönderildi.');e.target.reset();loadMentorContents()}catch(e){toast(e.message)}}
async function loadMentorContents(){let el=document.getElementById('mentorContents');if(!el)return;try{let d=await api('/mentor/contents/list',{method:'POST',body:JSON.stringify({token})});el.innerHTML=d.items.length?d.items.map(x=>`<div style="padding:12px 0;border-bottom:1px solid var(--line)"><b>${x.title}</b><div class="muted" style="font-size:13px">${x.content_type} · ${x.primary_field||'Genel'} · ${x.status==='pending_review'?'İnceleme bekliyor':x.status}</div></div>`).join(''):'Henüz içerik eklemedin.'}catch(e){el.textContent='İçerikler yüklenemedi.'}}
const _gencDashboard=dashboard;dashboard=async function(){if(role==='mentor')return await mentorDashboard();return await _gencDashboard()}
const _gencRender=render;render=async function(){let x=path();if(x==='/mentor/register'){A.innerHTML=mentorRegisterPage();scrollTo(0,0);return}if(x==='/mentor/login'){A.innerHTML=mentorLoginPage();scrollTo(0,0);return}return await _gencRender()}
</script>
'''

html = html.replace('</body></html>', mentor_js + '</body></html>')
app_v2.HTML = html
