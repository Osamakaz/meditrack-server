import os

from flask import Flask, request
import telebot

import bot
import db

app = Flask(__name__)

PORT = int(os.environ.get("PORT", 5000))

# عنوان منصتك الكامل مثل https://myapp.onrender.com أو https://user.pella.app
BASE_URL = os.environ.get("BASE_URL", "")


@app.route("/")
def index():
    return "MediTrack License Server ✅"


@app.route("/verify")
def verify():
    """GET /verify?device_id=XXXX...
    يعيد نصاً صريحاً: active / transferred / revoked / not_found / trial
    """
    device_id = (request.args.get("device_id") or "").strip().upper().replace("-", "")
    if not device_id:
        return "not_found", 400

    status = db.verify_status(device_id)
    if status == db.STATUS_PENDING:
        return "trial"
    return status


@app.route("/webhook", methods=["POST"])
def webhook():
    """تيليغرام يرسل هنا كل تحديث (رسالة جديدة) في وضع webhook."""
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_update(update)
    except Exception as e:
        app.logger.error(f"webhook error: {e}")
    return "OK"


@app.route("/ping")
def ping():
    return "pong"


# تهيئة قاعدة البيانات عند بدء التطبيق (يُستدعى أيضاً عبر import بواسطة gunicorn)
db.init_db()

# تسجيل webhook تلقائياً عند توفر التوكن والرابط
if bot.BOT_TOKEN and BASE_URL:
    try:
        bot.set_webhook(BASE_URL.rstrip("/") + "/webhook")
    except Exception as e:
        print(f"⚠️  فشل تسجيل webhook: {e}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
