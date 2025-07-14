from flask import Flask, render_template, request, jsonify
import imaplib, email, re, traceback

app = Flask(__name__)

EMAIL = "rosewfotomatikkod@gmail.com"
PASSWORD = "eawsvuirmhekwbvs"
IMAP_SERVER = "imap.gmail.com"

# ✅ Tanımlı ürün anahtarları
VALID_KEYS = ["ROSEWF2025", "XDR4045674"]

# ✅ Her ürün anahtarı için son gösterilen kodu saklayan yapı
last_codes_per_key = {}

def get_latest_code_for_key(product_key):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")

        status, messages = mail.search(None, '(UNSEEN)')
        mail_ids = messages[0].split()

        if not mail_ids:
            print("📭 Hiç okunmamış mail yok.")
            return None

        for i in reversed(mail_ids):
            status, msg_data = mail.fetch(i, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    body = ""

                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode(errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(errors="ignore")

                    code = extract_code(body)

                    # ✅ Bu ürün anahtarına ait son kodla karşılaştır
                    if code and code != last_codes_per_key.get(product_key):
                        last_codes_per_key[product_key] = code
                        return code

    except Exception:
        print("❌ HATA:")
        traceback.print_exc()

    return None

def extract_code(body):
    """
    Mail gövdesindeki ilk 6 haneli sayıyı yakalar.
    """
    match = re.search(r"\b\d{6}\b", body)
    return match.group(0) if match else None

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/get-code", methods=["POST"])
def get_code():
    data = request.get_json()
    product_key = data.get("key")

    if product_key not in VALID_KEYS:
        return jsonify({"error": "Geçersiz ürün anahtarı"})

    code = get_latest_code_for_key(product_key)
    return jsonify({"code": code})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
