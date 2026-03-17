"""
serve_static.py
Wraps the backend Flask app and serves the React dist folder as a SPA.
Flask handles /api/* routes; everything else returns index.html.
"""
import os
from flask import send_from_directory, send_file
from main import app  # import the Flask app from main.py

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    """Serve React SPA — fall back to index.html for client-side routing."""
    # Don't intercept API or health routes (already registered in main.py)
    if path.startswith("api/") or path.startswith("health"):
        from flask import abort
        abort(404)

    full_path = os.path.join(STATIC_DIR, path)
    if path and os.path.isfile(full_path):
        return send_from_directory(STATIC_DIR, path)

    # Fallback: SPA index
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return send_file(index)

    return "Frontend not built. Run: npm run build inside /frontend", 503


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
