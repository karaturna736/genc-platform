import app_v2

LOVABLE_PANEL = "https://preview--genc-kariyer.lovable.app/panel"

# Reuse the current live backend/app and only change the student navigation layer.
# Company accounts stay on the Railway company dashboard for now.
html = app_v2.HTML

# Inject a single role-aware panel navigator into the existing frontend.
needle = "function go(x){location.hash=x}function path(){return location.hash.slice(1)||'/'}"
replacement = (
    "function go(x){location.hash=x}"
    "function mainPanel(){if(role==='student'){window.location.href='" + LOVABLE_PANEL + "'}else{location.hash='/dashboard'}}"
    "function path(){return location.hash.slice(1)||'/'}"
)
html = html.replace(needle, replacement)

# All explicit dashboard actions become role-aware. For students this opens the
# existing Lovable /panel; companies continue using the Railway dashboard.
html = html.replace("go('/dashboard')", "mainPanel()")

# The replacement above may also affect the helper itself in future source edits;
# guard against accidental self-recursion.
html = html.replace(
    "function mainPanel(){if(role==='student'){window.location.href='" + LOVABLE_PANEL + "'}else{mainPanel()}}",
    "function mainPanel(){if(role==='student'){window.location.href='" + LOVABLE_PANEL + "'}else{location.hash='/dashboard'}}",
)

# Make the clickable wordmark use the same role-aware behaviour when it is meant
# to represent the authenticated home destination.
old_brand = "function brand(toDashboard=false){return `<span class=\"brand\" onclick=\"go('${toDashboard?'/dashboard':'/'}')\">G.E.N<b>.C</b></span>`}"
new_brand = "function brand(toDashboard=false){return `<span class=\"brand\" onclick=\"${toDashboard?'mainPanel()':\"go('/')\"}\">G.E.N<b>.C</b></span>`}"
html = html.replace(old_brand, new_brand)

app_v2.HTML = html
app = app_v2.app
