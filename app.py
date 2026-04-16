import os
from flask import Flask, render_template
from leads_route import leads_bp, init_leads_table
from admin_route import admin_bp

app = Flask(__name__)

# SECRET_KEY necesaria para las sesiones del admin
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-cambiar-en-prod")

app.register_blueprint(leads_bp)
app.register_blueprint(admin_bp)

@app.route("/")
def index():
    return render_template("index.html")

try:
    with app.app_context():
        init_leads_table()
        _add_nota_column()
except Exception as e:
    print(f"Aviso BD: {e}")

def _add_nota_column():
    """Añade columna nota si no existe (migración segura)."""
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS nota TEXT;
                """)
    finally:
        conn.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(debug=True, host="0.0.0.0", port=port)