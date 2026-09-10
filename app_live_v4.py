import os
import smtplib
import sqlite3
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr

import app_mentor_bridge
import app_v2

app = app_mentor_bridge.app

# Temporary Railway verification storage. Final production auth will move to Supabase Auth.
with app_v2.db() as c:
    c.executescript('''
    CREATE TABLE IF NOT EXISTS email_verifications(
      email TEXT PRIMARY KEY,
      code_hash TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      verified_at TEXT,
      attempts INTEGER NOT NULL DEFAULT 0,
      sent_at TEXT NOT NULL
    );
    ''')

class VerificationRequest(BaseModel):
    email: EmailStr

class VerificationConfirm(BaseModel):
    email: EmailStr
    code: str

class MentorVerifiedRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    professional_title: str = ''
    organization: str = ''
    expertise: str = ''
    bio: str = ''
    linkedin_url: str = ''


def utcnow():
    return datetime.now(timezone.utc)


def code_hash(email: str, code: str) -> str:
    return hashlib.sha256(f"genc-verify-v1|{email.lower()}|{code}".encode()).hexdigest()


def smtp_ready() -> bool:
    return bool(os.getenv('SMTP_USER') and os.getenv('SMTP_PASSWORD'))


def send_verification_email(to_email: str, code: str):
    if not smtp_ready():
        raise HTTPException(
            503,
            'E-posta doğrulama servisi henüz bağlanmadı. G.E.N.C gönderici hesabı yapılandırılmalı.'
        )

    host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    port = int(os.getenv('SMTP_PORT', '587'))
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASSWORD')
    from_name = os.getenv('SMTP_FROM_NAME', 'G.E.N.C')

    msg = EmailMessage()
    msg['Subject'] = 'G.E.N.C doğrulama kodun'
    msg['From'] = f'{from_name} <{user}>'
    msg['To'] = to_email
    msg.set_content(
        f'''G.E.N.C hesabını doğrulamak için kodun:\n\n{code}\n\nKod 10 dakika geçerlidir. Bu işlemi sen başlatmadıysan bu e-postayı yok sayabilirsin.'''
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
    except Exception:
        raise HTTPException(503, 'Doğrulama e-postası şu anda gönderilemedi. Lütfen tekrar dene.')


@app.get('/api/email/status')
def email_status():
    return {'configured': smtp_ready(), 'provider': 'gmail_smtp' if smtp_ready() else 'not_configured'}


@app.post('/api/email/request-code')
def request_code(d: VerificationRequest):
    email = str(d.email).lower()
    now = utcnow()

    with app_v2.db() as c:
        row = c.execute('SELECT sent_at FROM email_verifications WHERE email=?', (email,)).fetchone()
        if row:
            try:
                last = datetime.fromisoformat(row['sent_at'])
                if (now - last).total_seconds() < 60:
                    raise HTTPException(429, 'Yeni kod istemeden önce 60 saniye bekle.')
            except ValueError:
                pass

    code = f'{secrets.randbelow(1_000_000):06d}'
    send_verification_email(email, code)
    exp = now + timedelta(minutes=10)

    with app_v2.db() as c:
        c.execute('''
          INSERT INTO email_verifications(email,code_hash,expires_at,verified_at,attempts,sent_at)
          VALUES(?,?,?,?,0,?)
          ON CONFLICT(email) DO UPDATE SET
            code_hash=excluded.code_hash,
            expires_at=excluded.expires_at,
            verified_at=NULL,
            attempts=0,
            sent_at=excluded.sent_at
        ''', (email, code_hash(email, code), exp.isoformat(), None, now.isoformat()))

    return {'ok': True, 'message': 'Doğrulama kodu e-posta adresine gönderildi.'}


@app.post('/api/email/confirm-code')
def confirm_code(d: VerificationConfirm):
    email = str(d.email).lower()
    code = ''.join(ch for ch in d.code if ch.isdigit())
    if len(code) != 6:
        raise HTTPException(400, '6 haneli doğrulama kodunu gir.')

    with app_v2.db() as c:
        row = c.execute('SELECT * FROM email_verifications WHERE email=?', (email,)).fetchone()
        if not row:
            raise HTTPException(400, 'Önce doğrulama kodu iste.')
        if row['attempts'] >= 5:
            raise HTTPException(429, 'Çok fazla hatalı deneme. Yeni kod iste.')
        try:
            if utcnow() > datetime.fromisoformat(row['expires_at']):
                raise HTTPException(400, 'Kodun süresi dolmuş. Yeni kod iste.')
        except ValueError:
            raise HTTPException(400, 'Kodun süresi dolmuş. Yeni kod iste.')

        if not secrets.compare_digest(row['code_hash'], code_hash(email, code)):
            c.execute('UPDATE email_verifications SET attempts=attempts+1 WHERE email=?', (email,))
            raise HTTPException(400, 'Doğrulama kodu hatalı.')

        c.execute('UPDATE email_verifications SET verified_at=? WHERE email=?', (utcnow().isoformat(), email))

    return {'ok': True, 'verified': True}


def require_verified_email(email: str):
    email = email.lower()
    with app_v2.db() as c:
        row = c.execute('SELECT verified_at,expires_at FROM email_verifications WHERE email=?', (email,)).fetchone()
    if not row or not row['verified_at']:
        raise HTTPException(403, 'Önce e-posta adresini doğrula.')
    try:
        if utcnow() > datetime.fromisoformat(row['expires_at']) + timedelta(minutes=20):
            raise HTTPException(403, 'E-posta doğrulamanın süresi dolmuş. Tekrar kod iste.')
    except ValueError:
        raise HTTPException(403, 'E-posta doğrulamanın süresi dolmuş. Tekrar kod iste.')


@app.post('/api/mentor/register-verified')
def mentor_register_verified(d: MentorVerifiedRegister):
    require_verified_email(str(d.email))
    # Reuse the existing mentor registration model/handler.
    payload = app_mentor_bridge.MentorRegisterIn(
        email=str(d.email),
        password=d.password,
        full_name=d.full_name,
        professional_title=d.professional_title,
        organization=d.organization,
        expertise=d.expertise,
        bio=d.bio,
        linkedin_url=d.linkedin_url,
    )
    return app_mentor_bridge.mentor_register(payload)

# ---------- UI layer ----------
html = app_v2.HTML

ui_css = r'''
<style>
.genc-header{position:relative;z-index:40;padding:18px 0}.genc-header-inner{height:64px;border:1px solid rgba(255,255,255,.09);background:rgba(11,24,35,.72);backdrop-filter:blur(18px);border-radius:18px;padding:0 12px 0 20px;display:flex;align-items:center;justify-content:space-between;gap:18px;box-shadow:0 18px 60px rgba(0,0,0,.2)}
.genc-header-mid{display:flex;align-items:center;gap:6px;color:#9db0bf;font-size:13px;font-weight:800}.genc-header-mid span{padding:8px 10px;border-radius:9px}.genc-header-actions{display:flex;align-items:center;gap:8px}.genc-login{background:transparent!important;color:#e9f2f4!important;border:1px solid rgba(255,255,255,.11)!important}.genc-join{box-shadow:0 0 0 1px rgba(104,227,196,.08),0 10px 30px rgba(104,227,196,.08)}
.role-overlay{position:fixed;inset:0;z-index:100;background:rgba(2,8,13,.72);backdrop-filter:blur(12px);display:flex;align-items:center;justify-content:center;padding:18px}.role-dialog{width:min(760px,100%);background:#0c1823;border:1px solid rgba(255,255,255,.11);border-radius:24px;padding:24px;box-shadow:0 28px 100px rgba(0,0,0,.5)}.role-head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:18px}.role-head h3{font-size:28px;letter-spacing:-.04em;margin:3px 0 5px}.role-head p{margin:0;color:#92a6b6}.close-role{width:38px;height:38px;border-radius:11px;border:1px solid rgba(255,255,255,.1);background:#122535;color:#fff;cursor:pointer}.role-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.role-card{border:1px solid rgba(255,255,255,.09);background:#0f2130;border-radius:17px;padding:19px;text-align:left;color:#f2f7f8;cursor:pointer;transition:.2s}.role-card:hover{transform:translateY(-2px);border-color:rgba(104,227,196,.38);background:#112838}.role-chip{width:38px;height:38px;border-radius:12px;background:rgba(104,227,196,.11);display:flex;align-items:center;justify-content:center;color:#68e3c4;font-weight:900;margin-bottom:15px}.role-card b{display:block;font-size:17px;margin-bottom:5px}.role-card small{color:#91a5b4;line-height:1.5}.role-foot{margin-top:14px;color:#6f8798;font-size:12px}.verify-box{border:1px solid rgba(104,227,196,.18);background:rgba(104,227,196,.045);border-radius:14px;padding:14px;display:grid;gap:10px}.verify-row{display:flex;gap:8px}.verify-row .in{flex:1}.verify-state{font-size:12px;color:#91a5b4}.verified-ok{color:#68e3c4;font-weight:800}.mail-note{font-size:12px;color:#7890a0;line-height:1.5}.mentor-login-card{position:relative;overflow:hidden}.mentor-login-card:before{content:'';position:absolute;width:180px;height:180px;border-radius:50%;background:rgba(104,227,196,.06);right:-70px;top:-80px;filter:blur(4px)}
@media(max-width:850px){.genc-header{padding:10px 0}.genc-header-inner{height:58px;border-radius:15px;padding:0 9px 0 15px}.genc-header-mid{display:none}.genc-header-actions .genc-login{display:none}.genc-header-actions .btn{padding:10px 12px;font-size:13px}.role-overlay{align-items:flex-end;padding:0}.role-dialog{border-radius:24px 24px 0 0;padding:20px 16px 24px}.role-grid{grid-template-columns:1fr}.role-card{display:grid;grid-template-columns:44px 1fr;column-gap:12px;align-items:center;padding:14px}.role-chip{margin:0;grid-row:1/3}.role-card b{margin:0}.role-card small{margin-top:3px}.verify-row{flex-direction:column}}
</style>
'''

ui_js = r'''
<script>
let emailVerified = false;
function closeRolePicker(){let x=document.getElementById('roleOverlay');if(x)x.remove()}
function openRolePicker(mode='login'){
  closeRolePicker();
  const login=mode==='login';
  const paths=login?{student:'/student/login',company:'/company/login',mentor:'/mentor/login'}:{student:'/student/register',company:'/company/register',mentor:'/mentor/register'};
  const title=login?'Nasıl devam etmek istiyorsun?':'G.E.N.C’e nasıl katılacaksın?';
  document.body.insertAdjacentHTML('beforeend',`<div class="role-overlay" id="roleOverlay" onclick="if(event.target===this)closeRolePicker()"><div class="role-dialog"><div class="role-head"><div><div class="ey">G.E.N.C erişim</div><h3>${title}</h3><p>Tek bir kalabalık menü yerine rolünü seç, doğru alana geç.</p></div><button class="close-role" onclick="closeRolePicker()">✕</button></div><div class="role-grid"><button class="role-card" onclick="closeRolePicker();go('${paths.student}')"><span class="role-chip">Ö</span><b>Öğrenci</b><small>Görevleri yap, becerilerini kanıtla ve kariyer profilini geliştir.</small></button><button class="role-card" onclick="closeRolePicker();go('${paths.company}')"><span class="role-chip">Ş</span><b>Şirket</b><small>Görev yayınla, gerçek performansı değerlendir ve yetenek keşfet.</small></button><button class="role-card" onclick="closeRolePicker();go('${paths.mentor}')"><span class="role-chip">M</span><b>Eğitmen / Mentor</b><small>Bilgini ücretsiz paylaş ve gençlerin gelişimine katkı sağla.</small></button></div><div class="role-foot">G.E.N.C · Deneyim, gelişim ve yetenek ağı</div></div></div>`)
}

const _homeV4 = home;
home = function(){
  if(token&&role) return _homeV4();
  return `<main class="hero"><div class="wrap genc-header"><div class="genc-header-inner">${brand(false)}<div class="genc-header-mid"><span>Deneyim</span><span>Ücretsiz gelişim</span><span>Yetenek keşfi</span></div><div class="genc-header-actions"><button class="btn genc-login" onclick="openRolePicker('login')">Giriş yap</button><button class="btn genc-join" onclick="openRolePicker('register')">Ücretsiz katıl →</button></div></div></div><div class="wrap main"><div><div class="ey">Kariyer ve deneyim platformu</div><h1>Deneyimin yoksa,<br><em>burada kazan.</em></h1><p>Gerçek iş senaryolarında kendini geliştir. Yeteneklerini kanıtla. Alanında çalışan mentorların ücretsiz içeriklerinden öğren.</p><div class="actions"><button class="btn" onclick="openRolePicker('register')">G.E.N.C’e katıl →</button><button class="btn alt" onclick="openRolePicker('login')">Zaten hesabım var</button></div></div></div><div class="wrap values"><span>Gerçek görevler</span><b>•</b><span>Ücretsiz öğrenme</span><b>•</b><span>Şirket keşfi</span></div></main>`
}

// The original hashchange listener was attached before mentor routes existed.
// Force a second role-aware render so mentor pages never fall back to an empty/home state.
const _goV4 = go;
go = function(x){_goV4(x); if(x.startsWith('/mentor/')) setTimeout(()=>render(),0)};
addEventListener('hashchange',()=>{const x=path();if(x.startsWith('/mentor/'))setTimeout(()=>render(),0)});

async function requestVerifyCode(emailId, stateId){
  const email=document.getElementById(emailId)?.value?.trim();
  const state=document.getElementById(stateId);
  if(!email){toast('Önce e-posta adresini yaz.');return}
  try{await api('/email/request-code',{method:'POST',body:JSON.stringify({email})});emailVerified=false;if(state)state.textContent='Kod gönderildi. Gmail gelen kutunu ve spam klasörünü kontrol et.';toast('6 haneli kod gönderildi.')}catch(e){if(state)state.textContent=e.message;toast(e.message)}
}
async function confirmVerifyCode(emailId, codeId, stateId){
  const email=document.getElementById(emailId)?.value?.trim();const code=document.getElementById(codeId)?.value?.trim();const state=document.getElementById(stateId);
  try{await api('/email/confirm-code',{method:'POST',body:JSON.stringify({email,code})});emailVerified=true;if(state){state.textContent='✓ E-posta doğrulandı';state.classList.add('verified-ok')}toast('E-posta doğrulandı.')}catch(e){emailVerified=false;if(state)state.textContent=e.message;toast(e.message)}
}
function verifyBlock(emailId,prefix){return `<div class="verify-box"><div><b>E-posta doğrulama</b><div class="mail-note">G.E.N.C, e-posta adresine 6 haneli tek kullanımlık kod gönderir.</div></div><button type="button" class="btn alt" onclick="requestVerifyCode('${emailId}','${prefix}state')">Kodu e-postama gönder</button><div class="verify-row"><input id="${prefix}code" class="in" inputmode="numeric" maxlength="6" placeholder="6 haneli kod"><button type="button" class="btn alt" onclick="confirmVerifyCode('${emailId}','${prefix}code','${prefix}state')">Doğrula</button></div><div id="${prefix}state" class="verify-state">Henüz doğrulanmadı</div></div>`}

// Mentor register/login rebuilt cleanly so the route never renders blank.
mentorRegisterPage = function(){emailVerified=false;return mentorShell(`<div class="card"><div class="ey">Eğitmen / Mentor Kaydı</div><h2>Uzmanlığını gençlerle paylaş.</h2><form class="form" onsubmit="mentorRegisterV4(event)"><div class="field"><label>Ad soyad</label><input id="mname" class="in" required></div><div class="row"><div class="field"><label>Mesleki unvan</label><input id="mtitle" class="in" placeholder="Örn. Frontend Developer"></div><div class="field"><label>Kurum / şirket</label><input id="morg" class="in" placeholder="Opsiyonel"></div></div><div class="field"><label>Uzmanlık alanları</label><input id="mexpert" class="in" placeholder="Yazılım, UI/UX, finans..."></div><div class="field"><label>Kısa bio</label><textarea id="mbio" class="in"></textarea></div><div class="field"><label>LinkedIn</label><input id="mlink" class="in"></div><div class="field"><label>E-posta</label><input id="memail" type="email" class="in" required oninput="emailVerified=false"></div>${verifyBlock('memail','mv')}<div class="field"><label>Şifre</label><input id="mpw" type="password" minlength="8" class="in" required></div><div class="notice">Mentor hesabı incelemeye alınır. Yayınlanan içerikler öğrencilere ücretsiz olur ve önce kalite kontrolünden geçer.</div><button class="btn">Mentor hesabı oluştur</button><button type="button" class="btn alt" onclick="go('/')">← Ana sayfa</button></form></div>`)};
mentorLoginPage = function(){return mentorShell(`<div class="card mentor-login-card"><div class="ey">Eğitmen / Mentor</div><h2>Bilgi paylaşım alanına dön.</h2><p class="muted">Ücretsiz içeriklerini yönet, yeni rehber veya mini eğitim gönder.</p><form class="form" onsubmit="mentorLogin(event)"><div class="field"><label>E-posta</label><input id="mle" type="email" class="in" required></div><div class="field"><label>Şifre</label><input id="mlp" type="password" class="in" required></div><button class="btn">Mentor paneline gir →</button><button type="button" class="btn alt" onclick="go('/mentor/register')">Mentor hesabı oluştur</button><button type="button" class="btn ghost" onclick="go('/')">← Ana sayfa</button></form></div>`)};
async function mentorRegisterV4(e){e.preventDefault();if(!emailVerified){toast('Önce e-posta adresini doğrula.');return}try{let d=await api('/mentor/register-verified',{method:'POST',body:JSON.stringify({email:memail.value,password:mpw.value,full_name:mname.value,professional_title:mtitle.value,organization:morg.value,expertise:mexpert.value,bio:mbio.value,linkedin_url:mlink.value})});token=d.token;role='mentor';localStorage.genc_token=token;localStorage.genc_role=role;go('/dashboard')}catch(err){toast(err.message)}}

// Re-render after this script overrides the landing/header functions.
if(document.readyState!=='loading'){setTimeout(()=>render(),0)}
</script>
'''

html = html.replace('</head>', ui_css + '</head>')
html = html.replace('</body></html>', ui_js + '</body></html>')
app_v2.HTML = html
