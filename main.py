# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify
import imaplib
import email
from email.header import decode_header
import re
import traceback
import os

app = Flask(__name__)

# 🌐 Ortam değişkenlerinden mail bilgilerini al
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")

# ✅ Geçerli ürün anahtarları
VALID_KEYS = ["ROSEWF2025", "XDR4045674"]

# ✅ Daha önce gösterilen kodları tutmak için
last_codes_per_key = {}

# ✅ Geçerli e-posta başlıkları ve gönderen adres
ACCEPTED_SUBJECTS = ["Giriş kodu", "Disney+ için tek seferlik kodunuz", "Disney+ için tek seferlik kodunuz burada"]
ALLOWED_SENDER = "disneyplus@trx.mail2.disneyplus.com"

# ✅ Kod çıkarma fonksiyonu
def extract_code(body):
    match = re.search(r"\b\d{6}\b", body)
    return match.group(0) if match else None

# ✅ Mailden kodu alma fonksiyonu (HTML destekli)
def get_latest_code_for_key(product_key):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")

        status, messages = mail.search(None, 'UNSEEN')
        mail_ids = messages[0].split()

        if not mail_ids:
            print("[INFO] Hiç okunmamış mail yok.")
            return None

        for i in reversed(mail_ids):
            status, msg_data = mail.fetch(i, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    # ✅ Başlığı UTF-8 ile çöz
                    raw_subject = msg["Subject"]
                    decoded_subject_parts = decode_header(raw_subject)
                    subject = ""
                    for part, enc in decoded_subject_parts:
                        if isinstance(part, bytes):
                            subject += part.decode(enc or "utf-8", errors="ignore")
                        else:
                            subject += part

                    # ✅ Başlık ve gönderen kontrolü
                    if not any(accepted in subject for accepted in ACCEPTED_SUBJECTS):
                        continue
                    from_address = msg.get("From", "").lower()
                    if ALLOWED_SENDER not in from_address:
                        continue

                    # ✅ İçerik (hem HTML hem Plain Text)
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type in ["text/plain", "text/html"]:
                                charset = part.get_content_charset() or "utf-8"
                                body = part.get_payload(decode=True).decode(charset, errors="ignore")
                                if extract_code(body):  # Kod varsa dur
                                    break
                    else:
                        charset = msg.get_content_charset() or "utf-8"
                        body = msg.get_payload(decode=True).decode(charset, errors="ignore")

                    # ✅ Kod çıkar
                    code = extract_code(body)
                    if code and code not in ["707070", "000000"] and code != last_codes_per_key.get(product_key):
                        last_codes_per_key[product_key] = code
                        return code

    except Exception:
        print("❌ Hata oluştu:")
        traceback.print_exc()

    return None

# ✅ Anasayfa route
@app.route("/")
def home():
    return render_template("index.html")

# ✅ Kod alma route
@app.route("/get-code", methods=["POST"])
def get_code():
    data = request.get_json()
    product_key = data.get("key")

    if product_key not in VALID_KEYS:
        return jsonify({"error": "Geçersiz ürün anahtarı"})

    code = get_latest_code_for_key(product_key)
    if code:
        return jsonify({"code": code})
    else:
        return jsonify({"error": "Yeni kod bulunamadı"})

# ✅ Uygulamayı başlat
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
