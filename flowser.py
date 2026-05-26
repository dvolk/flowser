#!/usr/bin/env python3
"""
Simple Flask File Manager
- Single file, no database, no auth
- Thumbnails for images, grid layout
- Multiple file upload
"""

import os
import hashlib
from flask import (
    Flask,
    request,
    redirect,
    url_for,
    send_from_directory,
    render_template_string,
    abort,
)
from werkzeug.utils import secure_filename
from PIL import Image

# ----------------------------------------------------------------------
# Configuration – change the root directory as needed
# ----------------------------------------------------------------------
ROOT_DIR = os.path.abspath(os.environ.get("FILEMANAGER_ROOT", "./files"))
THUMB_DIR = os.path.join(ROOT_DIR, ".thumbnails")  # hidden inside the root

# Create necessary folders on startup
os.makedirs(ROOT_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)

# Recognised image extensions for thumbnail generation
IMG_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "gif", "webp", "avif"}

app = Flask(__name__)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def is_image(filename: str) -> bool:
    """Return True if the file extension is a supported image format."""
    if "." in filename:
        ext = filename.rsplit(".", 1)[1].lower()
        return ext in IMG_EXTENSIONS
    return False


def get_thumbnail_url(rel_path: str, abs_path: str) -> str | None:
    """
    Ensure a thumbnail exists for the given image file and return its URL.
    `rel_path` is the relative path from ROOT_DIR (using forward slashes).
    The thumbnail is saved as <md5 hash>.jpg in THUMB_DIR.
    """
    thumb_name = hashlib.md5(rel_path.encode()).hexdigest() + ".jpg"
    thumb_path = os.path.join(THUMB_DIR, thumb_name)

    # Generate if missing (assume files never change, so never regenerate)
    if not os.path.exists(thumb_path):
        try:
            img = Image.open(abs_path)
            img.thumbnail((200, 200))
            # JPEG requires RGB; convert if necessary
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=85)
        except Exception:
            # If generation fails (e.g. AVIF without libavif support) return None
            return None

    return url_for("serve_thumbnail", filename=thumb_name)


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.route("/")
def index():
    """Redirect to the root directory listing."""
    return redirect(url_for("browse", subpath=""))


@app.route("/browse/", defaults={"subpath": ""})
@app.route("/browse/<path:subpath>")
def browse(subpath: str):
    """Show the contents of a directory as a grid."""
    # Security: prevent escaping the root directory
    dir_path = os.path.abspath(os.path.join(ROOT_DIR, subpath))
    if not dir_path.startswith(os.path.abspath(ROOT_DIR)):
        abort(403)
    if not os.path.isdir(dir_path):
        abort(404)

    # Gather directory entries, skip the thumbnail cache folder
    entries = []
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if entry.name.startswith(".") and entry.name == ".thumbnails":
                    continue
                entries.append(entry)
    except PermissionError:
        abort(403)

    # Directories first, then files (case‑insensitive)
    entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))

    # Breadcrumbs
    rel_dir = os.path.relpath(dir_path, ROOT_DIR)
    crumbs = [("Home", url_for("browse", subpath=""))]
    if rel_dir != ".":
        accum = ""
        for part in rel_dir.split(os.sep):
            accum = os.path.join(accum, part).replace("\\", "/") if accum else part
            crumbs.append((part, url_for("browse", subpath=accum)))

    # Build list of items for the template
    items = []
    for entry in entries:
        name = entry.name
        if entry.is_dir():
            # Directory entry
            item = {
                "type": "dir",
                "name": name,
                "url": url_for(
                    "browse", subpath=os.path.join(subpath, name).replace("\\", "/")
                ),
                "thumbnail": None,
            }
        else:
            # File entry
            rel_path = os.path.relpath(entry.path, ROOT_DIR).replace("\\", "/")
            file_url = url_for("download", filepath=rel_path)
            ext = os.path.splitext(name)[1][1:].lower()

            thumb_url = None
            if is_image(name):
                thumb_url = get_thumbnail_url(rel_path, entry.path)

            item = {
                "type": "file",
                "name": name,
                "url": file_url,
                "ext": ext,
                "thumbnail": thumb_url,
                "is_image": is_image(name),
            }
        items.append(item)

    upload_url = url_for("upload")
    return render_template_string(
        HTML_TEMPLATE,
        items=items,
        crumbs=crumbs,
        current_dir=subpath,
        upload_url=upload_url,
    )


@app.route("/download/<path:filepath>")
def download(filepath: str):
    """Serve a raw file from the root directory."""
    abs_path = os.path.abspath(os.path.join(ROOT_DIR, filepath))
    if not abs_path.startswith(os.path.abspath(ROOT_DIR)):
        abort(403)
    if not os.path.isfile(abs_path):
        abort(404)
    return send_from_directory(ROOT_DIR, filepath)


@app.route("/thumbnails/<filename>")
def serve_thumbnail(filename: str):
    """Serve a cached thumbnail from the thumbnail directory."""
    return send_from_directory(THUMB_DIR, filename)


@app.route("/upload", methods=["POST"])
def upload():
    """Handle multiple file uploads to the current directory."""
    directory = request.form.get("directory", "")
    upload_dir = os.path.abspath(os.path.join(ROOT_DIR, directory))
    if not upload_dir.startswith(os.path.abspath(ROOT_DIR)):
        abort(403)
    if not os.path.isdir(upload_dir):
        abort(404)

    files = request.files.getlist("files")
    for file in files:
        if file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(upload_dir, filename))

    return redirect(url_for("browse", subpath=directory))


# ----------------------------------------------------------------------
# HTML Template (inline)
# ----------------------------------------------------------------------
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simple File Manager</title>
    <style>
        :root {
            --bg: #f5f5f5;
            --card-bg: #fff;
            --text: #333;
            --border: #ddd;
        }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0; padding: 20px;
        }
        h1 { margin-top: 0; }
        .breadcrumbs {
            margin-bottom: 15px;
            padding: 8px 12px;
            background: var(--card-bg);
            border-radius: 6px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .breadcrumbs a {
            color: #0066cc;
            text-decoration: none;
            margin: 0 4px;
        }
        .breadcrumbs a:hover { text-decoration: underline; }
        .breadcrumbs span { color: #888; margin: 0 2px; }

        .upload-form {
            margin-bottom: 20px;
            padding: 12px;
            background: var(--card-bg);
            border-radius: 6px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }
        .upload-form input[type="file"] { flex: 1; }
        .upload-form button {
            background: #0066cc;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 12px;
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 8px;
            text-align: center;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            transition: transform 0.1s;
        }
        .card:hover { transform: scale(1.02); }
        .card img {
            width: 100%;
            height: 120px;
            object-fit: cover;
            border-radius: 4px;
            background: #f0f0f0;
        }
        .card .name {
            margin-top: 6px;
            font-size: 0.85em;
            word-break: break-all;
            line-height: 1.3;
        }
        .card a {
            text-decoration: none;
            color: inherit;
            display: block;
        }
        .folder-svg {
            width: 100%;
            height: 120px;
        }
    </style>
</head>
<body>
    <h1>File Manager</h1>

    <!-- Breadcrumbs -->
    <div class="breadcrumbs">
        {% for label, url in crumbs %}
            {% if not loop.last %}
                <a href="{{ url }}">{{ label }}</a> <span>/</span>
            {% else %}
                <strong>{{ label }}</strong>
            {% endif %}
        {% endfor %}
    </div>

    <!-- Upload form -->
    <form class="upload-form" action="{{ upload_url }}" method="post" enctype="multipart/form-data">
        <input type="hidden" name="directory" value="{{ current_dir }}">
        <input type="file" name="files" multiple>
        <button type="submit">Upload</button>
    </form>

    <!-- Grid of files/folders -->
    <div class="grid">
        {% for item in items %}
        <div class="card">
            <a href="{{ item.url }}" {% if item.type == 'file' and not item.is_image %}download{% endif %}>
                {% if item.type == 'dir' %}
                    <!-- Folder icon (simple SVG) -->
                    <svg class="folder-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
                        <path d="M10 20 H40 L50 35 H90 V80 H10 Z" fill="#e2a745" stroke="#b87d2a" stroke-width="3"/>
                    </svg>
                {% elif item.thumbnail %}
                    <!-- Image thumbnail -->
                    <img src="{{ item.thumbnail }}" alt="{{ item.name }}">
                {% else %}
                    <!-- Generic file placeholder with extension -->
                    <svg class="folder-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
                        <rect width="100" height="100" fill="#d0d0d0" rx="8"/>
                        <text x="50" y="65" font-size="36" text-anchor="middle" fill="#fff" font-family="system-ui, sans-serif">
                            {{ item.ext[:4] }}
                        </text>
                    </svg>
                {% endif %}
                <div class="name">{{ item.name }}</div>
            </a>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

# ----------------------------------------------------------------------
# Run the application
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Serving files from: {ROOT_DIR}")
    app.run(debug=True, host="0.0.0.0", port=8080)
