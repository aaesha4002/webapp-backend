from pathlib import Path
from tempfile import NamedTemporaryFile
import io
import os
import sqlite3, hashlib, secrets, base64, uuid, shutil

from flask import Flask, request, jsonify, send_file, render_template, after_this_request, make_response, send_from_directory
from werkzeug.utils import secure_filename

from stegano import hide as steg_hide, reveal as steg_retrieve

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 30 MB upload guard

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.db')

# Setup the uploads directory
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password_hash TEXT)''')
    conn.commit()
    conn.close()

init_db()


@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        res = make_response()
        origin = request.headers.get("Origin")
        if origin:
            res.headers["Access-Control-Allow-Origin"] = origin
            res.headers["Access-Control-Allow-Credentials"] = "true"
        else:
            res.headers["Access-Control-Allow-Origin"] = "*"
            
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Requested-With, Authorization, Accept, Origin, Cache-Control"
        res.headers["Access-Control-Allow-Private-Network"] = "true"
        res.headers["Access-Control-Max-Age"] = "86400"
        return res


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    else:
        response.headers["Access-Control-Allow-Origin"] = "*"
        
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Requested-With, Authorization, Accept, Origin, Cache-Control"
    response.headers["Access-Control-Expose-Headers"] = "Content-Type, X-Alias, Content-Disposition, Content-Length"
    return response


def _cleanup(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _temp_path(suffix: str) -> str:
    tmp = NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.close()
    return tmp.name


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pwd_hash))
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists."}), 400
    finally:
        conn.close()
    
    return jsonify({"status": "success", "message": "User registered."})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    
    if row and row[0] == pwd_hash:
        token = secrets.token_hex(16)
        return jsonify({"status": "success", "token": token, "username": username})
    return jsonify({"error": "Invalid credentials."}), 401

@app.route('/uploads/<filename>')
def serve_upload(filename):
    response = send_from_directory(UPLOAD_FOLDER, filename)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'

    return response

@app.route("/api/hide", methods=["POST"])
def api_hide():
    cover = request.files.get("cover")
    payload_file = request.files.get("payload_file")
    payload_text = (request.form.get("payload_text") or "").strip()
    alias = (request.form.get("alias") or "").strip()
    key = request.form.get("key") or ""

    if not cover:
        return jsonify({"status": "error", "message": "Cover image is required."}), 400
    if payload_file and payload_text:
        return jsonify({"status": "error", "message": "Choose text or file payload, not both."}), 400
    if not payload_file and not payload_text:
        return jsonify({"status": "error", "message": "Add payload text or upload a payload file."}), 400

    cover_path = _temp_path(".png")
    cover.save(cover_path)

    if payload_file:
        payload_bytes = payload_file.read()
        cleaned_name = secure_filename(payload_file.filename) or "payload.bin"
        final_alias = alias or cleaned_name
    else:
        payload_bytes = payload_text.encode("utf-8")
        final_alias = alias or "message.txt"

    # Generate UUID and setup output path
    file_id = uuid.uuid4().hex
    out_filename = f"{file_id}.png"
    out_path = os.path.join(UPLOAD_FOLDER, out_filename)

    try:
        steg_hide(Path(cover_path), payload_bytes, final_alias, Path(out_path), key)
    except Exception as exc:
        _cleanup(cover_path)
        return jsonify({"status": "error", "message": str(exc)}), 400

    # Clean up the temporary cover image
    _cleanup(cover_path)
    
    # Construct the full URL for the client to fetch
    image_url = f"{request.host_url.rstrip('/')}/uploads/{out_filename}"

    return jsonify({
        "status": "success",
        "message": "Stego image generated successfully.",
        "image": image_url
    })


@app.route("/api/retrieve", methods=["POST"])
def api_retrieve():
    stego = request.files.get("stego")
    key = request.form.get("key") or ""
    if not stego:
        return jsonify({"status": "error", "message": "Stego image is required."}), 400

    stego_path = _temp_path(".png")
    stego.save(stego_path)
    
    # We use a temporary bin path first because we don't know the file extension yet
    temp_out = _temp_path(".bin")

    try:
        recovered_path, alias = steg_retrieve(Path(stego_path), Path(temp_out), key)
    except Exception as exc:  
        _cleanup(stego_path)
        _cleanup(temp_out)
        return jsonify({"status": "error", "message": str(exc)}), 400

    # Clean up the stego container immediately
    _cleanup(stego_path)

    # Determine final filename. Prepend a UUID so multiple users extracting 
    # a file named "secret.txt" don't overwrite each other in the uploads folder.
    file_id = uuid.uuid4().hex
    original_filename = alias or "recovered.bin"
    safe_filename = f"{file_id}_{secure_filename(original_filename)}"
    final_out_path = os.path.join(UPLOAD_FOLDER, safe_filename)

    # Move the recovered file from temp storage to the public uploads folder
    shutil.move(recovered_path, final_out_path)

    # Construct the full URL for the client
    file_url = f"{request.host_url.rstrip('/')}/uploads/{safe_filename}"

    return jsonify({
        "status": "success",
        "message": "Data retrieved successfully.",
        "filename": original_filename, # Send the original name so your frontend knows what to call it
        "image": file_url,             # Kept as 'image' to strictly match your schema
        "file_url": file_url           # Also provided as 'file_url' since it might be a .txt or .zip file!
    })

    download_name = Path(alias or "recovered.bin").name
    response = send_file(recovered_path, mimetype="application/octet-stream", as_attachment=True, download_name=download_name)
    response.headers["X-Alias"] = download_name
    return response


@app.route("/api/ai-hide", methods=["POST"])
def api_ai_hide():
    cover = request.files.get("cover")
    secret = request.files.get("secret")
    if not cover or not secret:
        return jsonify({"status": "error", "message": "Both a cover image and a secret image are required."}), 400
    
    try:
        from ai_stegano import ai_hide
        container = ai_hide(cover.read(), secret.read())
    except RuntimeError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": f"AI model error: {exc}"}), 500

    # Generate UUID and save directly to uploads folder
    file_id = uuid.uuid4().hex
    out_filename = f"{file_id}.png"
    out_path = os.path.join(UPLOAD_FOLDER, out_filename)

    try:
        with open(out_path, "wb") as f:
            f.write(container)
    except Exception as e:
         return jsonify({"status": "error", "message": f"Failed to save image to disk: {e}"}), 500

    image_url = f"{request.host_url.rstrip('/')}/uploads/{out_filename}"

    return jsonify({
        "status": "success",
        "message": "AI Stego container generated successfully.",
        "image": image_url
    })


@app.route("/api/ai-extract", methods=["POST"])
def api_ai_extract():
    container = request.files.get("container")
    
    if not container:
        return jsonify({"status": "error", "message": "Container image is required."}), 400
        
    try:
        from ai_stegano import ai_extract
        revealed = ai_extract(container.read())
    except Exception as exc:
        return jsonify({"status": "error", "message": f"AI model error: {exc}"}), 500
    
    # Generate UUID and save the revealed image directly to the uploads folder
    file_id = uuid.uuid4().hex
    out_filename = f"revealed_{file_id}.png"
    out_path = os.path.join(UPLOAD_FOLDER, out_filename)

    try:
        with open(out_path, "wb") as f:
            f.write(revealed)
    except Exception as e:
         return jsonify({"status": "error", "message": f"Failed to save image to disk: {e}"}), 500

    # Construct the full URL for the client
    image_url = f"{request.host_url.rstrip('/')}/uploads/{out_filename}"

    return jsonify({
        "status": "success",
        "message": "Secret image revealed successfully.",
        "image": image_url
    })


@app.route("/api/ai-text-hide", methods=["POST"])
def api_ai_text_hide():
    cover = request.files.get("cover")
    text = (request.form.get("text") or "").strip()
    if not cover:
        return jsonify({"status": "error", "message": "Cover image is required."}), 400
    if not text:
        return jsonify({"status": "error", "message": "Text message is required."}), 400
    
    try:
        from ai_text_stegano import ai_text_hide, MAX_CHARS
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]
        container = ai_text_hide(cover.read(), text)
    except Exception as exc:
        return jsonify({"status": "error", "message": f"AI text model error: {exc}"}), 500
    
    # Generate UUID and save directly to uploads folder
    file_id = uuid.uuid4().hex
    out_filename = f"{file_id}.png"
    out_path = os.path.join(UPLOAD_FOLDER, out_filename)

    try:
        with open(out_path, "wb") as f:
            f.write(container)
    except Exception as e:
         return jsonify({"status": "error", "message": f"Failed to save image to disk: {e}"}), 500

    image_url = f"{request.host_url.rstrip('/')}/uploads/{out_filename}"

    return jsonify({
        "status": "success",
        "message": "AI text container generated successfully.",
        "image": image_url
    })


@app.route("/api/ai-text-extract", methods=["POST"])
def api_ai_text_extract():
    stego = request.files.get("stego")
    if not stego:
        return jsonify({"status": "error", "message": "Stego image is required."}), 400
        
    try:
        from ai_text_stegano import ai_text_extract
        text = ai_text_extract(stego.read())
    except Exception as exc:
        return jsonify({"status": "error", "message": f"AI text model error: {exc}"}), 500
        
    return jsonify({
        "status": "success",
        "message": "Text extracted successfully.",
        "text": text
    })

from waitress import serve

if __name__ == "__main__":
    # Waitress handles concurrent mobile requests much more stably than Flask's dev server
    print(">>> Trollexa Server starting on http://0.0.0.0:5000")
    serve(app, host="0.0.0.0", port=5000, threads=6)