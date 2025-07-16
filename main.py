# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import imaplib
import email
from email.header import decode_header
import re
import traceback
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback_key")

# ✅ Platform ayarları
PLATFORM_SETTINGS = {
    "disney": {
        "EMAIL": os.getenv("DISNEY_EMAIL"),
        "PASSWORD": os.getenv("DISNEY_PASSWORD"),
        "IMAP_SERVER": os.getenv("DISNEY_IMAP", "imap.gmail.com"),
        "ALLOWED_SENDERS": ["disneyplus@trx.mail2.disneyplus.com"],
        "SUBJECTS": [
            "Giriş kodu",
            "Disney+ için tek seferlik kodunuz",
            "Disney+ için tek seferlik kodunuz burada"
        ],
        "CODE_LENGTH": 6,
        "KEY_FILE": "DISNEY_keys.txt"
    },
    "netflix": {
        "EMAIL": os.getenv("NETFLIX_EMAIL"),
        "PASSWORD": os.getenv("NETFLIX_PASSWORD"),
        "IMAP_SERVER": os.getenv("NETFLIX_IMAP", "imap.gmail.com"),
        "ALLOWED_SENDERS": ["info@account.netflix.com"],
        "SUBJECTS": ["Giriş kodunuz", "Netflix: Oturum açma kodunuz"],
        "CODE_LENGTH": 4,
        "KEY_FILE": "NETFLIX_keys.txt"
    },
    "steam": {
        "EMAIL": os.getenv("STEAM_EMAIL"),
        "PASSWORD": os.getenv("STEAM_PASSWORD"),
        "IMAP_SERVER": os.getenv("STEAM_IMAP", "imap.gmail.com"),
        "ALLOWED_SENDERS": ["noreply@steampowered.com", "cnecati434@gmail.com"],
        "SUBJECTS": ["Steam hesabınız: Yeni bilgisayardan erişim", "Steam hesabınız: Yeni tarayıcıdan veya mobil cihazdan erişim"],
        "CODE_LENGTH": 5,
        "KEY_FILE": "STEAM_keys.txt"
    }
}

# ✅ Ürün anahtarlarını yükle
def load_valid_keys():
    keys = {}
    for platform, settings in PLATFORM_SETTINGS.items():
        path = settings["KEY_FILE"]
        if os.path.exists(path):
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if "|" in line:
                        key, limit = line.split("|", 1)
                        if key and limit.isdigit():
                            keys[key] = {"platform": platform, "limit": int(limit)}
    return keys

# ✅ Kullanım hakkını azalt
def decrement_key_usage(product_key):
    valid_keys = load_valid_keys()
    key_info = valid_keys.get(product_key)
    if not key_info:
        return

    key_file = PLATFORM_SETTINGS[key_info["platform"]]["KEY_FILE"]
    updated_lines = []
    with open(key_file, "r") as f:
        for line in f:
            line = line.strip()
            if "|" in line:
                key, limit = line.split("|", 1)
                if key == product_key:
                    new_limit = max(0, int(limit) - 1)
                    updated_lines.append(f"{key}|{new_limit}")
                else:
                    updated_lines.append(line)
    with open(key_file, "w") as f:
        f.write("\n".join(updated_lines) + "\n")

# ✅ Kod geçmişi
last_codes_per_key = {}

def get_latest_code_for_key(product_key):
    valid_keys = load_valid_keys()
    key_info = valid_keys.get(product_key)
    if not key_info or key_info["limit"] <= 0:
        return None

    platform = key_info["platform"]
    settings = PLATFORM_SETTINGS.get(platform)
    if not settings:
        return None

    try:
        mail = imaplib.IMAP4_SSL(settings["IMAP_SERVER"])
        mail.login(settings["EMAIL"], settings["PASSWORD"])
        mail.select("inbox")

        status, messages = mail.search(None, 'UNSEEN')
        mail_ids = messages[0].split()

        if not mail_ids:
            return None

        for i in reversed(mail_ids):
            status, msg_data = mail.fetch(i, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    raw_subject = msg["Subject"]
                    decoded_subject_parts = decode_header(raw_subject)
                    subject = "".join(
                        [part.decode(enc or "utf-8", errors="ignore") if isinstance(part, bytes) else part
                         for part, enc in decoded_subject_parts]
                    )

                    from_email = email.utils.parseaddr(msg.get("From"))[1]
                    if from_email not in settings["ALLOWED_SENDERS"]:
                        continue
                    if not any(s in subject for s in settings["SUBJECTS"]):
                        continue

                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            charset = part.get_content_charset() or "utf-8"
                            if content_type == "text/plain":
                                body = part.get_payload(decode=True).decode(charset, errors="ignore")
                            elif content_type == "text/html" and not body:
                                html = part.get_payload(decode=True).decode(charset, errors="ignore")
                                body = BeautifulSoup(html, "html.parser").get_text()
                    else:
                        content_type = msg.get_content_type()
                        charset = msg.get_content_charset() or "utf-8"
                        if content_type == "text/html":
                            html = msg.get_payload(decode=True).decode(charset, errors="ignore")
                            body = BeautifulSoup(html, "html.parser").get_text()
                        else:
                            body = msg.get_payload(decode=True).decode(charset, errors="ignore")

                    code = extract_code(body, settings["CODE_LENGTH"])
                    if code and code != last_codes_per_key.get(product_key):
                        last_codes_per_key[product_key] = code

                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        with open("logs.txt", "a", encoding="utf-8") as log:
                            log.write(f"{product_key} - {code} - {now}\n")

                        decrement_key_usage(product_key)
                        return code
    except Exception:
        traceback.print_exc()

    return None

def extract_code(body, length=6):
    pattern = rf"\b[A-Z0-9]{{{length}}}\b"
    match = re.search(pattern, body)
    return match.group(0) if match else None

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/get-code", methods=["POST"])
def get_code():
    data = request.get_json()
    product_key = data.get("key")
    requested_platform = data.get("platform")  # HTML'den platform geliyor

    valid_keys = load_valid_keys()

    if not product_key or product_key not in valid_keys:
        return jsonify({"error": "Geçersiz ürün anahtarı"}), 400

    key_info = valid_keys[product_key]
    if key_info["limit"] <= 0:
        return jsonify({"error": "Bu ürün anahtarının kullanım hakkı dolmuştur."}), 403

    if key_info["platform"] != requested_platform:
        return jsonify({"error": "Geçersiz ürün anahtarı"}), 400

    code = get_latest_code_for_key(product_key)
    if code:
        return jsonify({"code": code})
    return jsonify({"error": "Yeni kod bulunamadı"}), 404

@app.route("/kategori/<name>")
def kategori(name):
    try:
        return render_template(f"{name}.html")
    except:
        return "Bu kategori bulunamadı.", 404

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("username") == "admin" and request.form.get("password") == "1234":
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Hatalı kullanıcı adı veya şifre.")
    return render_template("admin_login.html")

@app.route("/admin")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    return render_template("admin_panel.html")

@app.route("/admin/keys/<platform>", methods=["GET", "POST"])
def admin_keys(platform):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    if platform not in PLATFORM_SETTINGS:
        return "Geçersiz platform.", 400

    key_file = PLATFORM_SETTINGS[platform]["KEY_FILE"]
    keys = []
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            keys = f.read().strip().splitlines()

    if request.method == "POST":
        new_keys = request.form.get("keys")
        with open(key_file, "w") as f:
            f.write(new_keys.strip() + "\n")
        return redirect(url_for("admin_keys", platform=platform))

    return render_template("admin_keys.html", platform=platform, keys="\n".join(keys))

@app.route("/admin/logs")
def admin_logs():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    logs = []
    if os.path.exists("logs.txt"):
        with open("logs.txt", "r", encoding="utf-8") as f:
            logs = f.read().strip().splitlines()
    return render_template("admin_logs.html", logs=logs)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

@app.route("/disney")
def disney():
    return render_template("disney.html")

@app.route("/netflix")
def netflix():
    return render_template("netflix.html")

@app.route("/steam")
def steam():
    return render_template("steam.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)