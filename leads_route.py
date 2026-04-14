# leads_route.py
# Ruta Flask para recibir leads del formulario de contacto de la landing page.
# Se registra como Blueprint en tu app principal.
#
# Dependencias:
#   pip install flask psycopg2-binary sendgrid requests python-dotenv
#
# Variables de entorno necesarias (.env):
#   DATABASE_URL        → postgresql://user:pass@host:port/dbname
#   SENDGRID_API_KEY    → SG.xxxx
#   SENDGRID_FROM       → noreply@tudominio.com
#   WASSENGER_API_KEY   → token de Wassenger
#   WASSENGER_DEVICE_ID → ID del dispositivo WhatsApp en Wassenger
#   AGENCIA_EMAIL       → email del dueño que recibe el lead
#   AGENCIA_WHATSAPP    → número del dueño en formato internacional (34666123456)
#   AGENCIA_NOMBRE      → nombre de la agencia (para los mensajes)

import os
import json
import logging
from datetime import datetime

import psycopg2
import psycopg2.extras
import requests
from flask import Blueprint, request, jsonify
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

leads_bp = Blueprint("leads", __name__)
logger = logging.getLogger(__name__)


# ── HELPERS DE CONEXIÓN ────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])


# ── INICIALIZACIÓN DE TABLA (ejecutar una vez al arrancar la app) ──────────────

def init_leads_table():
    """Crea la tabla leads si no existe. Llamar desde create_app()."""
    sql = """
    CREATE TABLE IF NOT EXISTS leads (
        id              SERIAL PRIMARY KEY,
        tenant_id       VARCHAR(64) NOT NULL DEFAULT 'default',
        nombre          VARCHAR(200) NOT NULL,
        email           VARCHAR(200) NOT NULL,
        telefono        VARCHAR(50)  NOT NULL,
        viajeros        VARCHAR(20),
        destino         VARCHAR(200) NOT NULL,
        presupuesto     VARCHAR(50),
        fecha_viaje     VARCHAR(20),
        duracion        VARCHAR(20),
        mensaje         TEXT,
        estado          VARCHAR(20)  NOT NULL DEFAULT 'nuevo',
        ip_origen       VARCHAR(45),
        created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_leads_tenant  ON leads(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_leads_estado  ON leads(estado);
    CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at DESC);
    """
    conn = get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        logger.info("Tabla leads lista.")
    finally:
        conn.close()


# ── RUTA PRINCIPAL ─────────────────────────────────────────────────────────────

@leads_bp.route("/api/leads", methods=["POST"])
def crear_lead():
    """
    Recibe el JSON del formulario de contacto, lo guarda en PostgreSQL
    y dispara notificaciones por email (SendGrid) y WhatsApp (Wassenger).
    Devuelve 201 si todo fue bien, 400 si faltan campos obligatorios.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON requerido"}), 400

    # ── Validación de campos obligatorios ──────────────────────────────────────
    required = ["nombre", "email", "telefono", "destino"]
    missing = [f for f in required if not data.get(f, "").strip()]
    if missing:
        return jsonify({"error": f"Campos obligatorios: {', '.join(missing)}"}), 400

    # ── Construcción del objeto lead ───────────────────────────────────────────
    lead = {
        "tenant_id":    data.get("tenant_id", "default").strip(),
        "nombre":       data["nombre"].strip(),
        "email":        data["email"].strip().lower(),
        "telefono":     data["telefono"].strip(),
        "viajeros":     data.get("viajeros", "").strip(),
        "destino":      data["destino"].strip(),
        "presupuesto":  data.get("presupuesto", "").strip(),
        "fecha_viaje":  data.get("fecha", "").strip(),
        "duracion":     data.get("duracion", "").strip(),
        "mensaje":      data.get("mensaje", "").strip(),
        "ip_origen":    request.remote_addr,
    }

    # ── 1. Guardar en PostgreSQL ───────────────────────────────────────────────
    lead_id = _guardar_lead(lead)
    if not lead_id:
        return jsonify({"error": "Error al guardar el lead"}), 500

    lead["id"] = lead_id

    # ── 2. Notificación por email (no bloquea si falla) ───────────────────────
    try:
        _enviar_email(lead)
    except Exception as e:
        logger.error(f"[lead {lead_id}] Error email: {e}")

    # ── 3. Notificación por WhatsApp (no bloquea si falla) ───────────────────
    try:
        _enviar_whatsapp(lead)
    except Exception as e:
        logger.error(f"[lead {lead_id}] Error WhatsApp: {e}")

    return jsonify({
        "ok": True,
        "lead_id": lead_id,
        "message": "Lead recibido correctamente"
    }), 201


# ── HELPERS PRIVADOS ───────────────────────────────────────────────────────────

def _guardar_lead(lead: dict) -> int | None:
    """Inserta el lead en PostgreSQL y devuelve el ID generado."""
    sql = """
    INSERT INTO leads
        (tenant_id, nombre, email, telefono, viajeros, destino,
         presupuesto, fecha_viaje, duracion, mensaje, ip_origen)
    VALUES
        (%(tenant_id)s, %(nombre)s, %(email)s, %(telefono)s, %(viajeros)s,
         %(destino)s, %(presupuesto)s, %(fecha_viaje)s, %(duracion)s,
         %(mensaje)s, %(ip_origen)s)
    RETURNING id;
    """
    conn = get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, lead)
                return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"Error guardando lead: {e}")
        return None
    finally:
        conn.close()


def _formato_fecha(fecha_code: str) -> str:
    """Convierte '2026-03' → 'Marzo 2026', 'flexible' → 'Fechas flexibles'."""
    if not fecha_code or fecha_code == "flexible":
        return "Fechas flexibles"
    meses = {
        "01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril",
        "05": "Mayo",  "06": "Junio",   "07": "Julio", "08": "Agosto",
        "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre"
    }
    try:
        year, month = fecha_code.split("-")
        return f"{meses.get(month, month)} {year}"
    except ValueError:
        return fecha_code


def _formato_presupuesto(code: str) -> str:
    mapa = {
        "<1000":    "Hasta 1.000 €",
        "1000-3000":"1.000 – 3.000 €",
        "3000-6000":"3.000 – 6.000 €",
        ">6000":    "Más de 6.000 €",
    }
    return mapa.get(code, code or "No especificado")


def _formato_duracion(code: str) -> str:
    mapa = {
        "3-5":  "3–5 días",
        "7-10": "7–10 días",
        "11-15":"11–15 días",
        "15+":  "Más de 15 días",
    }
    return mapa.get(code, code or "No especificada")


def _enviar_email(lead: dict):
    """
    Envía un email al dueño de la agencia con todos los datos del lead.
    Usa SendGrid. Si SENDGRID_API_KEY no está configurada, loguea y sale.
    """
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        logger.warning("SENDGRID_API_KEY no configurada — email no enviado.")
        return

    agencia     = os.environ.get("AGENCIA_NOMBRE", "la agencia")
    dest_email  = os.environ.get("AGENCIA_EMAIL")
    from_email  = os.environ.get("SENDGRID_FROM", "noreply@example.com")

    if not dest_email:
        logger.warning("AGENCIA_EMAIL no configurada — email no enviado.")
        return

    fecha_fmt  = _formato_fecha(lead["fecha_viaje"])
    presu_fmt  = _formato_presupuesto(lead["presupuesto"])
    duracion_fmt = _formato_duracion(lead["duracion"])
    timestamp  = datetime.now().strftime("%d/%m/%Y a las %H:%M")

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#0F0E0C;padding:24px 32px">
        <p style="color:#C4973A;font-size:12px;letter-spacing:2px;text-transform:uppercase;margin:0">
          {agencia}
        </p>
        <h1 style="color:#FDFAF5;font-size:22px;font-weight:400;margin:8px 0 0">
          Nueva consulta de viaje
        </h1>
      </div>
      <div style="background:#1C1A16;padding:24px 32px">
        <div style="background:#111;border-left:3px solid #C4973A;padding:16px 20px;margin-bottom:20px">
          <p style="color:#C4973A;font-size:11px;text-transform:uppercase;margin:0 0 6px">
            Lead #{lead['id']} · {timestamp}
          </p>
          <p style="color:#FDFAF5;font-size:18px;font-weight:500;margin:0">{lead['nombre']}</p>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          {''.join(_fila_email(k, v) for k, v in [
              ("Destino",     lead['destino']),
              ("Viajeros",    lead['viajeros'] or "No especificado"),
              ("Fecha viaje", fecha_fmt),
              ("Duración",    duracion_fmt),
              ("Presupuesto", presu_fmt),
              ("Email",       lead['email']),
              ("Teléfono",    lead['telefono']),
          ])}
        </table>
        {f'''
        <div style="margin-top:20px;padding:16px;background:#111;border:1px solid #333">
          <p style="color:#8A8070;font-size:11px;text-transform:uppercase;margin:0 0 8px">Mensaje del cliente</p>
          <p style="color:#F5EFE4;font-size:14px;line-height:1.7;margin:0;font-style:italic">
            "{lead['mensaje']}"
          </p>
        </div>
        ''' if lead.get('mensaje') else ''}
        <div style="margin-top:24px;display:flex;gap:12px">
          <a href="mailto:{lead['email']}"
             style="background:#C4973A;color:#0F0E0C;padding:12px 24px;text-decoration:none;
                    font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase">
            Responder por email
          </a>
          <a href="https://wa.me/{lead['telefono'].replace(' ','').replace('+','')}"
             style="background:#25D366;color:#fff;padding:12px 24px;text-decoration:none;
                    font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase">
            Abrir WhatsApp
          </a>
        </div>
      </div>
      <div style="background:#0F0E0C;padding:16px 32px">
        <p style="color:#8A8070;font-size:11px;margin:0">
          Lead guardado automáticamente · ID #{lead['id']} ·
          IP: {lead['ip_origen']}
        </p>
      </div>
    </div>
    """

    message = Mail(
        from_email=from_email,
        to_emails=dest_email,
        subject=f"[{agencia}] Nueva consulta — {lead['destino']} · {lead['nombre']}",
        html_content=html,
    )
    sg = SendGridAPIClient(api_key)
    response = sg.send(message)
    logger.info(f"[lead {lead['id']}] Email enviado → status {response.status_code}")


def _fila_email(label: str, value: str) -> str:
    return f"""
    <tr style="border-bottom:1px solid #333">
      <td style="color:#8A8070;padding:10px 0;width:35%">{label}</td>
      <td style="color:#F5EFE4;padding:10px 0;font-weight:500">{value}</td>
    </tr>
    """


def _enviar_whatsapp(lead: dict):
    """
    Envía un mensaje de WhatsApp al dueño via Wassenger.
    Reutiliza la integración que ya tienes del sistema de fichajes.
    """
    api_key   = os.environ.get("WASSENGER_API_KEY")
    device_id = os.environ.get("WASSENGER_DEVICE_ID")
    numero    = os.environ.get("AGENCIA_WHATSAPP")
    agencia   = os.environ.get("AGENCIA_NOMBRE", "Tu agencia")

    if not all([api_key, device_id, numero]):
        logger.warning("Wassenger no configurado — WhatsApp no enviado.")
        return

    fecha_fmt    = _formato_fecha(lead["fecha_viaje"])
    presu_fmt    = _formato_presupuesto(lead["presupuesto"])
    duracion_fmt = _formato_duracion(lead["duracion"])

    # Mensaje formateado para WhatsApp (markdown de WA)
    texto = (
        f"*{agencia} · Lead nuevo #{lead['id']}*\n\n"
        f"👤 *{lead['nombre']}*\n"
        f"📍 {lead['destino']}"
        + (f" · {lead['viajeros']} viajeros" if lead.get('viajeros') else "")
        + f"\n📅 {fecha_fmt}"
        + (f" · {duracion_fmt}" if lead.get('duracion') else "")
        + f"\n💶 {presu_fmt}\n"
        f"📱 {lead['telefono']}\n"
        f"✉️ {lead['email']}\n"
        + (f"\n_\"{lead['mensaje'][:200]}{'…' if len(lead['mensaje'])>200 else ''}\"_\n"
           if lead.get('mensaje') else "")
        + f"\nResponde aquí y el bot retransmite al cliente."
    )

    url = f"https://api.wassenger.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "Token": api_key,
    }
    payload = {
        "device":  device_id,
        "phone":   numero,
        "message": texto,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    logger.info(f"[lead {lead['id']}] WhatsApp enviado → status {resp.status_code}")
