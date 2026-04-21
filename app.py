import os
import psycopg2
from flask import Flask, render_template, jsonify, send_from_directory
from leads_route import leads_bp, init_leads_table
from admin_route import admin_bp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-cambiar-en-prod")

app.register_blueprint(leads_bp)
app.register_blueprint(admin_bp)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/debug-vars")
def debug_vars():
    return jsonify({
        "ADMIN_USER": os.environ.get("ADMIN_USER", "NO DEFINIDA"),
        "ADMIN_PASSWORD": os.environ.get("ADMIN_PASSWORD", "NO DEFINIDA"),
        "SECRET_KEY": os.environ.get("SECRET_KEY", "NO DEFINIDA"),
    })

def _add_nota_column():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS nota TEXT;")
    finally:
        conn.close()

try:
    with app.app_context():
        init_leads_table()
        _add_nota_column()
except Exception as e:
    print(f"Aviso BD: {e}")

@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory('templates', 'sitemap.xml', mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    return send_from_directory('templates', 'robots.txt', mimetype='text/plain')

@app.errorhandler(404)
def page_not_found(e):
    return send_from_directory('templates', '404.html'), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(debug=True, host="0.0.0.0", port=port)