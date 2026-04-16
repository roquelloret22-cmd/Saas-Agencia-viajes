# admin_route.py
# Panel de administración para gestionar leads.
# Protegido con usuario y contraseña via sesión Flask.
#
# Variables de entorno necesarias:
#   ADMIN_USER     → usuario del panel (ej: admin)
#   ADMIN_PASSWORD → contraseña del panel
#   SECRET_KEY     → clave secreta Flask para sesiones

import os
import psycopg2
import psycopg2.extras
from flask import (
    Blueprint, render_template_string, request,
    redirect, url_for, session, jsonify
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated


# ── LOGIN ──────────────────────────────────────────────────────────────────────

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("user", "").strip()
        pwd  = request.form.get("password", "").strip()
        if (user == os.environ.get("ADMIN_USER", "admin") and
                pwd == os.environ.get("ADMIN_PASSWORD", "admin123")):
            session["admin_logged_in"] = True
            return redirect(url_for("admin.leads"))
        error = "Usuario o contraseña incorrectos"

    return render_template_string(LOGIN_HTML, error=error)


@admin_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ── LISTA DE LEADS ─────────────────────────────────────────────────────────────

@admin_bp.route("/")
@admin_bp.route("/leads")
@login_required
def leads():
    estado   = request.args.get("estado", "todos")
    busqueda = request.args.get("q", "").strip()

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Contadores por estado
            cur.execute("""
                SELECT estado, COUNT(*) as total
                FROM leads GROUP BY estado
            """)
            contadores = {r["estado"]: r["total"] for r in cur.fetchall()}
            total = sum(contadores.values())

            # Query principal
            conditions = []
            params = []
            if estado != "todos":
                conditions.append("estado = %s")
                params.append(estado)
            if busqueda:
                conditions.append("(nombre ILIKE %s OR email ILIKE %s OR destino ILIKE %s)")
                params += [f"%{busqueda}%"] * 3

            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            cur.execute(f"""
                SELECT id, nombre, email, telefono, destino, viajeros,
                       presupuesto, fecha_viaje, duracion, mensaje,
                       estado, created_at, nota
                FROM leads
                {where}
                ORDER BY created_at DESC
                LIMIT 100
            """, params)
            leads_list = cur.fetchall()
    finally:
        conn.close()

    return render_template_string(
        ADMIN_HTML,
        leads=leads_list,
        estado=estado,
        busqueda=busqueda,
        contadores=contadores,
        total=total,
    )


# ── ACTUALIZAR ESTADO / NOTA ───────────────────────────────────────────────────

@admin_bp.route("/leads/<int:lead_id>/update", methods=["POST"])
@login_required
def update_lead(lead_id):
    data  = request.get_json(silent=True) or {}
    campo = data.get("campo")
    valor = data.get("valor", "")

    if campo not in ("estado", "nota"):
        return jsonify({"error": "Campo no permitido"}), 400

    conn = get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE leads SET {campo} = %s, updated_at = NOW() WHERE id = %s",
                    (valor, lead_id)
                )
    finally:
        conn.close()

    return jsonify({"ok": True})


# ── DETALLE DE UN LEAD ─────────────────────────────────────────────────────────

@admin_bp.route("/leads/<int:lead_id>")
@login_required
def lead_detalle(lead_id):
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM leads WHERE id = %s", (lead_id,))
            lead = cur.fetchone()
    finally:
        conn.close()

    if not lead:
        return "Lead no encontrado", 404

    return render_template_string(DETALLE_HTML, lead=lead)


# ══════════════════════════════════════════════════════════════════════════════
# TEMPLATES HTML
# ══════════════════════════════════════════════════════════════════════════════

LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin · Acceso</title>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'Jost',sans-serif;background:#0F0E0C;color:#F5EFE4;min-height:100vh;display:flex;align-items:center;justify-content:center;}
  .box{background:#1C1A16;border:1px solid rgba(255,255,255,0.07);padding:2.5rem;width:100%;max-width:380px;}
  .logo{font-size:1.3rem;font-weight:600;letter-spacing:0.08em;color:#FDFAF5;margin-bottom:0.3rem;}
  .logo span{color:#C4973A;}
  .sub{font-size:0.75rem;color:#8A8070;margin-bottom:2rem;letter-spacing:0.1em;text-transform:uppercase;}
  label{font-size:0.65rem;letter-spacing:0.15em;text-transform:uppercase;color:#8A8070;display:block;margin-bottom:0.4rem;}
  input{width:100%;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);color:#F5EFE4;padding:0.75rem 1rem;font-family:'Jost',sans-serif;font-size:0.9rem;outline:none;margin-bottom:1.2rem;}
  input:focus{border-color:rgba(196,151,58,0.5);}
  button{width:100%;background:#C4973A;color:#0F0E0C;border:none;padding:0.9rem;font-family:'Jost',sans-serif;font-size:0.75rem;letter-spacing:0.2em;text-transform:uppercase;font-weight:500;cursor:pointer;}
  button:hover{background:#E8C97A;}
  .error{background:rgba(224,82,82,0.1);border:1px solid rgba(224,82,82,0.3);color:#E05252;padding:0.7rem 1rem;font-size:0.82rem;margin-bottom:1.2rem;}
</style>
</head>
<body>
<div class="box">
  <div class="logo">Velada<span>.</span>Viajes</div>
  <div class="sub">Panel de administración</div>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST">
    <label>Usuario</label>
    <input type="text" name="user" autofocus autocomplete="username">
    <label>Contraseña</label>
    <input type="password" name="password" autocomplete="current-password">
    <button type="submit">Entrar</button>
  </form>
</div>
</body>
</html>"""


ADMIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin · Leads</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400&family=Jost:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  :root{--dorado:#C4973A;--negro:#0F0E0C;--carbon:#1C1A16;--arena:#F5EFE4;--muted:#8A8070;}
  body{font-family:'Jost',sans-serif;background:#0F0E0C;color:#F5EFE4;min-height:100vh;}
  /* NAV */
  nav{background:#1C1A16;border-bottom:1px solid rgba(255,255,255,0.06);padding:0.9rem 2rem;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:50;}
  .nav-logo{font-size:1.1rem;font-weight:600;letter-spacing:0.08em;color:#FDFAF5;}
  .nav-logo span{color:#C4973A;}
  .nav-right{display:flex;align-items:center;gap:1.5rem;}
  .nav-link{font-size:0.72rem;letter-spacing:0.12em;text-transform:uppercase;color:#8A8070;text-decoration:none;transition:color 0.2s;}
  .nav-link:hover{color:#F5EFE4;}
  /* MAIN */
  main{padding:2rem;max-width:1200px;margin:0 auto;}
  /* STATS */
  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:2rem;}
  .stat{background:#1C1A16;border:1px solid rgba(255,255,255,0.06);padding:1.2rem 1.4rem;}
  .stat-num{font-family:'Cormorant Garamond',serif;font-size:2rem;font-weight:300;color:#FDFAF5;line-height:1;}
  .stat-label{font-size:0.65rem;letter-spacing:0.15em;text-transform:uppercase;color:#8A8070;margin-top:0.3rem;}
  .stat.dorado .stat-num{color:#C4973A;}
  /* FILTROS */
  .filtros{display:flex;gap:0.6rem;margin-bottom:1.5rem;align-items:center;flex-wrap:wrap;}
  .filtro-btn{font-size:0.7rem;letter-spacing:0.1em;text-transform:uppercase;padding:0.5rem 1rem;border:1px solid rgba(255,255,255,0.1);background:transparent;color:#8A8070;cursor:pointer;text-decoration:none;transition:all 0.2s;}
  .filtro-btn:hover{border-color:rgba(196,151,58,0.4);color:#F5EFE4;}
  .filtro-btn.active{background:#C4973A;border-color:#C4973A;color:#0F0E0C;}
  .search{flex:1;min-width:200px;max-width:300px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);color:#F5EFE4;padding:0.5rem 1rem;font-family:'Jost',sans-serif;font-size:0.85rem;outline:none;}
  .search:focus{border-color:rgba(196,151,58,0.4);}
  /* TABLA */
  .tabla-wrap{overflow-x:auto;}
  table{width:100%;border-collapse:collapse;font-size:0.82rem;}
  thead tr{border-bottom:1px solid rgba(255,255,255,0.08);}
  th{text-align:left;padding:0.7rem 0.9rem;font-size:0.62rem;letter-spacing:0.15em;text-transform:uppercase;color:#8A8070;font-weight:400;}
  tbody tr{border-bottom:1px solid rgba(255,255,255,0.04);transition:background 0.15s;}
  tbody tr:hover{background:rgba(255,255,255,0.02);}
  td{padding:0.85rem 0.9rem;vertical-align:middle;}
  .td-nombre{font-weight:500;color:#FDFAF5;}
  .td-email{color:#8A8070;font-size:0.75rem;}
  .td-destino{color:#C4973A;}
  .td-fecha{color:#8A8070;font-size:0.75rem;white-space:nowrap;}
  /* BADGES ESTADO */
  .badge{display:inline-block;font-size:0.62rem;letter-spacing:0.1em;text-transform:uppercase;padding:0.25rem 0.6rem;font-weight:500;}
  .badge.nuevo{background:rgba(55,138,221,0.15);color:#6BAAEE;border:1px solid rgba(55,138,221,0.2);}
  .badge.contactado{background:rgba(196,151,58,0.15);color:#C4973A;border:1px solid rgba(196,151,58,0.2);}
  .badge.cerrado{background:rgba(29,158,117,0.15);color:#4DC9A0;border:1px solid rgba(29,158,117,0.2);}
  .badge.perdido{background:rgba(224,82,82,0.12);color:#E05252;border:1px solid rgba(224,82,82,0.2);}
  /* SELECT ESTADO */
  .estado-select{background:transparent;border:none;color:inherit;font-family:'Jost',sans-serif;font-size:0.7rem;cursor:pointer;outline:none;padding:0.2rem;}
  /* ACCIONES */
  .btn-ver{font-size:0.65rem;letter-spacing:0.1em;text-transform:uppercase;color:#8A8070;text-decoration:none;border:1px solid rgba(255,255,255,0.08);padding:0.3rem 0.7rem;transition:all 0.2s;}
  .btn-ver:hover{border-color:rgba(196,151,58,0.4);color:#C4973A;}
  /* EMPTY */
  .empty{text-align:center;padding:4rem 2rem;color:#8A8070;}
  .empty p{font-size:0.9rem;}
  /* NOTA INLINE */
  .nota-input{background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,0.06);color:#8A8070;font-family:'Jost',sans-serif;font-size:0.78rem;width:160px;outline:none;padding:0.2rem 0;}
  .nota-input:focus{border-color:rgba(196,151,58,0.4);color:#F5EFE4;}
  /* TOAST */
  .toast{position:fixed;bottom:1.5rem;right:1.5rem;background:#1C1A16;border:1px solid rgba(196,151,58,0.3);color:#C4973A;padding:0.7rem 1.2rem;font-size:0.78rem;letter-spacing:0.05em;opacity:0;transition:opacity 0.3s;pointer-events:none;z-index:999;}
  .toast.show{opacity:1;}
</style>
</head>
<body>

<nav>
  <div class="nav-logo">Velada<span>.</span>Viajes <span style="color:#8A8070;font-weight:300;font-size:0.8rem;margin-left:0.5rem">· Admin</span></div>
  <div class="nav-right">
    <a href="/" target="_blank" class="nav-link">Ver landing</a>
    <a href="/admin/logout" class="nav-link">Salir</a>
  </div>
</nav>

<main>

  <!-- Stats -->
  <div class="stats">
    <div class="stat dorado">
      <div class="stat-num">{{ total }}</div>
      <div class="stat-label">Total leads</div>
    </div>
    <div class="stat">
      <div class="stat-num" style="color:#6BAAEE">{{ contadores.get('nuevo', 0) }}</div>
      <div class="stat-label">Nuevos</div>
    </div>
    <div class="stat">
      <div class="stat-num" style="color:#C4973A">{{ contadores.get('contactado', 0) }}</div>
      <div class="stat-label">Contactados</div>
    </div>
    <div class="stat">
      <div class="stat-num" style="color:#4DC9A0">{{ contadores.get('cerrado', 0) }}</div>
      <div class="stat-label">Cerrados</div>
    </div>
  </div>

  <!-- Filtros -->
  <div class="filtros">
    <a href="/admin/leads" class="filtro-btn {% if estado == 'todos' %}active{% endif %}">Todos</a>
    <a href="/admin/leads?estado=nuevo" class="filtro-btn {% if estado == 'nuevo' %}active{% endif %}">Nuevos</a>
    <a href="/admin/leads?estado=contactado" class="filtro-btn {% if estado == 'contactado' %}active{% endif %}">Contactados</a>
    <a href="/admin/leads?estado=cerrado" class="filtro-btn {% if estado == 'cerrado' %}active{% endif %}">Cerrados</a>
    <a href="/admin/leads?estado=perdido" class="filtro-btn {% if estado == 'perdido' %}active{% endif %}">Perdidos</a>
    <form method="GET" action="/admin/leads" style="display:flex;gap:0.5rem;margin-left:auto;">
      {% if estado != 'todos' %}<input type="hidden" name="estado" value="{{ estado }}">{% endif %}
      <input type="text" name="q" value="{{ busqueda }}" placeholder="Buscar nombre, email, destino…" class="search">
    </form>
  </div>

  <!-- Tabla -->
  {% if leads %}
  <div class="tabla-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Cliente</th>
          <th>Destino</th>
          <th>Viajeros</th>
          <th>Presupuesto</th>
          <th>Fecha viaje</th>
          <th>Recibido</th>
          <th>Estado</th>
          <th>Nota</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for l in leads %}
        <tr id="row-{{ l.id }}">
          <td style="color:#8A8070;font-size:0.72rem">#{{ l.id }}</td>
          <td>
            <div class="td-nombre">{{ l.nombre }}</div>
            <div class="td-email">{{ l.email }}</div>
            <div class="td-email" style="margin-top:2px">{{ l.telefono }}</div>
          </td>
          <td class="td-destino">{{ l.destino }}</td>
          <td style="color:#8A8070">{{ l.viajeros or '—' }}</td>
          <td style="color:#8A8070;font-size:0.75rem">{{ l.presupuesto or '—' }}</td>
          <td class="td-fecha">{{ l.fecha_viaje or '—' }}</td>
          <td class="td-fecha">{{ l.created_at.strftime('%d/%m/%Y %H:%M') if l.created_at else '—' }}</td>
          <td>
            <select class="estado-select badge {{ l.estado }}"
                    onchange="updateLead({{ l.id }}, 'estado', this.value, this)">
              <option value="nuevo"      {% if l.estado=='nuevo' %}selected{% endif %}>Nuevo</option>
              <option value="contactado" {% if l.estado=='contactado' %}selected{% endif %}>Contactado</option>
              <option value="cerrado"    {% if l.estado=='cerrado' %}selected{% endif %}>Cerrado</option>
              <option value="perdido"    {% if l.estado=='perdido' %}selected{% endif %}>Perdido</option>
            </select>
          </td>
          <td>
            <input type="text" class="nota-input"
                   value="{{ l.nota or '' }}"
                   placeholder="Añadir nota…"
                   onblur="updateLead({{ l.id }}, 'nota', this.value, this)"
                   onkeydown="if(event.key==='Enter') this.blur()">
          </td>
          <td>
            <a href="/admin/leads/{{ l.id }}" class="btn-ver">Ver</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="empty">
    <p>No hay leads {% if estado != 'todos' %}con estado "{{ estado }}"{% endif %}{% if busqueda %} que coincidan con "{{ busqueda }}"{% endif %}.</p>
  </div>
  {% endif %}

</main>

<div class="toast" id="toast"></div>

<script>
  function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
  }

  function updateLead(id, campo, valor, el) {
    fetch(`/admin/leads/${id}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ campo, valor })
    })
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        if (campo === 'estado') {
          el.className = 'estado-select badge ' + valor;
          showToast('Estado actualizado');
        } else {
          showToast('Nota guardada');
        }
      }
    })
    .catch(() => showToast('Error al guardar'));
  }
</script>
</body>
</html>"""


DETALLE_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lead #{{ lead.id }} · Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400&family=Jost:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'Jost',sans-serif;background:#0F0E0C;color:#F5EFE4;min-height:100vh;}
  nav{background:#1C1A16;border-bottom:1px solid rgba(255,255,255,0.06);padding:0.9rem 2rem;display:flex;align-items:center;justify-content:space-between;}
  .nav-logo{font-size:1.1rem;font-weight:600;letter-spacing:0.08em;color:#FDFAF5;}
  .nav-logo span{color:#C4973A;}
  .back{font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:#8A8070;text-decoration:none;}
  .back:hover{color:#C4973A;}
  main{padding:2rem;max-width:800px;margin:0 auto;}
  .header{margin-bottom:2rem;}
  .lead-id{font-size:0.65rem;letter-spacing:0.2em;text-transform:uppercase;color:#C4973A;margin-bottom:0.4rem;}
  .lead-nombre{font-family:'Cormorant Garamond',serif;font-size:2.5rem;font-weight:300;color:#FDFAF5;}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;}
  .card{background:#1C1A16;border:1px solid rgba(255,255,255,0.06);padding:1.5rem;}
  .card-title{font-size:0.65rem;letter-spacing:0.2em;text-transform:uppercase;color:#C4973A;margin-bottom:1rem;}
  .field{margin-bottom:0.9rem;}
  .field-label{font-size:0.62rem;letter-spacing:0.12em;text-transform:uppercase;color:#8A8070;margin-bottom:0.2rem;}
  .field-value{font-size:0.88rem;color:#F5EFE4;font-weight:300;}
  .mensaje-box{background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);padding:1rem;font-size:0.88rem;font-weight:300;line-height:1.7;color:rgba(245,239,228,0.8);font-style:italic;grid-column:1/-1;}
  .acciones{display:flex;gap:1rem;margin-top:1.5rem;grid-column:1/-1;}
  .btn{display:inline-block;padding:0.8rem 1.8rem;font-size:0.72rem;letter-spacing:0.15em;text-transform:uppercase;text-decoration:none;font-weight:500;cursor:pointer;border:none;font-family:'Jost',sans-serif;}
  .btn-wa{background:#25D366;color:#fff;}
  .btn-email{background:#C4973A;color:#0F0E0C;}
  .btn-back{background:transparent;border:1px solid rgba(255,255,255,0.1);color:#8A8070;}
  .btn-back:hover{border-color:rgba(196,151,58,0.4);color:#C4973A;}
</style>
</head>
<body>
<nav>
  <div class="nav-logo">Velada<span>.</span>Viajes <span style="color:#8A8070;font-weight:300;font-size:0.8rem;margin-left:0.5rem">· Admin</span></div>
  <a href="/admin/leads" class="back">← Volver a leads</a>
</nav>
<main>
  <div class="header">
    <p class="lead-id">Lead #{{ lead.id }} · {{ lead.created_at.strftime('%d/%m/%Y a las %H:%M') if lead.created_at else '' }}</p>
    <h1 class="lead-nombre">{{ lead.nombre }}</h1>
  </div>
  <div class="grid">
    <div class="card">
      <p class="card-title">Contacto</p>
      <div class="field"><div class="field-label">Email</div><div class="field-value">{{ lead.email }}</div></div>
      <div class="field"><div class="field-label">Teléfono</div><div class="field-value">{{ lead.telefono }}</div></div>
    </div>
    <div class="card">
      <p class="card-title">Viaje</p>
      <div class="field"><div class="field-label">Destino</div><div class="field-value" style="color:#C4973A">{{ lead.destino }}</div></div>
      <div class="field"><div class="field-label">Viajeros</div><div class="field-value">{{ lead.viajeros or '—' }}</div></div>
      <div class="field"><div class="field-label">Fecha</div><div class="field-value">{{ lead.fecha_viaje or '—' }}</div></div>
      <div class="field"><div class="field-label">Duración</div><div class="field-value">{{ lead.duracion or '—' }}</div></div>
      <div class="field"><div class="field-label">Presupuesto</div><div class="field-value">{{ lead.presupuesto or '—' }}</div></div>
    </div>
    {% if lead.mensaje %}
    <div class="mensaje-box">"{{ lead.mensaje }}"</div>
    {% endif %}
    <div class="acciones">
      <a href="https://wa.me/{{ lead.telefono | replace(' ','') | replace('+','') }}" target="_blank" class="btn btn-wa">Abrir WhatsApp</a>
      <a href="mailto:{{ lead.email }}" class="btn btn-email">Enviar email</a>
      <a href="/admin/leads" class="btn btn-back">Volver</a>
    </div>
  </div>
</main>
</body>
</html>"""