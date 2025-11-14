# src/alert_api.py
# API Flask pour déclencher les alertes de congestion
# Utilise le module src/alert.py pour la logique métier

from flask import Flask, jsonify
from src.alert import run_alerts

app = Flask(__name__)

# Endpoint Flask

@app.route("/run_alerts", methods=['POST'])
def run_alerts_endpoint():
    """
    Endpoint Flask pour déclencher les alertes.
    Analyse les congestions et envoie des alertes WhatsApp aux chauffeurs concernés.
    """
    result = run_alerts()
    return jsonify(result)

@app.route("/health", methods=['GET'])
def health():
    """Endpoint de santé pour vérifier que l'API est opérationnelle."""
    return jsonify({"status": "ok", "service": "alert_api"})

# Lancer le service

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
