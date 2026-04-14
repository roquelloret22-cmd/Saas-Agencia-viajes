import os
from flask import Flask, render_template
from leads_route import leads_bp, init_leads_table

app = Flask(__name__)
app.register_blueprint(leads_bp)

@app.route("/")
def index():
    return render_template("index.html")

with app.app_context():
    init_leads_table()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(debug=True, host="0.0.0.0", port=port) 
