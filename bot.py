import telebot
import hashlib
import os
import re
import sys
import time

import db

# ========== إعدادات ==========
# الأفضل استخدام متغيرات البيئة على منصة الاستضافة (لا تُرفع الأسرار في الملفات).
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]
if not BOT_TOKEN:
    try:
        import config  # احتياطي محلي فقط إن وُجد ملف config.py
        BOT_TOKEN = config.BOT_TOKEN
        if not ADMIN_IDS:
            ADMIN_IDS = config.ADMIN_IDS
    except ImportError:
        pass

# على PythonAnywhere المجاني، اتصالات الخروج تمر عبر بروكسي خاص.
# فعّل عبر متغير بيئة: PA_PROXY=1 (أو شغّل على PythonAnywhere مباشرة)
if os.environ.get("PA_PROXY", "") == "1":
    telebot.apihelper.proxy = {"https": "http://proxy.server:3128"}

SECRET_KEY = "MediTrack2024Key"  # يجب أن يطابق مفتاح LicenseManager.kt

PAY_METHOD = "Sham Cash"
WALLET_NUMBER = "9f9dd7b169278dea153dcbd1a8ff5a27"
ACCOUNT_NAME = "اسامه فاضل الخزعل"
PRICE = "100$ أو ما يعادلها بالليرة السورية"

bot = telebot.TeleBot(BOT_TOKEN)

# ========== دوال مساعدة ==========

def is_admin(user_id):
    return user_id in ADMIN_IDS


def generate_code(device_id: str) -> str:
    text = device_id + ":" + SECRET_KEY
    hash_hex = hashlib.sha256(text.encode("utf-8")).hexdigest().upper()
    chars = "".join(c for c in hash_hex if c.isalnum())[:16]
    if len(chars) < 16:
        return "0000-0000-0000-0000"
    return f"{chars[0:4]}-{chars[4:8]}-{chars[8:12]}-{chars[12:16]}"


def extract_device_id(text: str) -> str:
    """يستخرج الـ Device ID من الرسالة (يُرسله التطبيق في نهاية الرسالة)."""
    text = text.strip().replace("\n", "").replace("\r", "")
    patterns = [
        r"([A-Za-z0-9]{8,40})$",
        r"([A-Fa-f0-9]{16})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("-", "")
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text)
    if len(cleaned) >= 8:
        return cleaned.upper()
    return ""


def is_transfer_request(text: str) -> bool:
    """التطبيق يرسل للنقل: 'أريد نقل ترخيص MediTrack إلى هذا الجهاز الجديد - رقم جهازي: X'"""
    lowered = text.lower()
    return "نقل" in text or "transfer" in lowered


def device_status_label(status):
    labels = {
        db.STATUS_PENDING: "⏳ قيد التحقق",
        db.STATUS_ACTIVE: "✅ مفعّل",
        db.STATUS_TRANSFERRED: "📤 تم النقل",
        db.STATUS_REVOKED: "🚫 ملغى",
    }
    return labels.get(status, status)


def send_copyable(user_id, label, value):
    """يرسل رسالتين: تسمية توضيحية، ثم القيمة وحدها في سطر مستقل.
    هكذا ينسخها المستخدم بالضغط المطوّل ثم Copy (مثل نسخ user id)."""
    try:
        bot.send_message(user_id, label)
        bot.send_message(user_id, f"`{value}`")
    except Exception:
        pass


# ========== أوامر الإدمن ==========

@bot.message_handler(commands=["start"])
def start(message):
    if is_admin(message.from_user.id):
        bot.reply_to(
            message,
            "👋 مرحباً بك يا مدير!\n"
            "الأوامر المتاحة:\n"
            "/pending - عروض قيد التحقق\n"
            "/approve USER_ID - تفعيل المكتسب\n"
            "/reject USER_ID - رفض الطلب\n"
            "/getcode DEVICE_ID - عرض كود جهاز\n"
            "/list - كل الأجهزة\n"
            "/revoke DEVICE_ID - إلغاء ترخيص\n"
            "/status DEVICE_ID - حالة جهاز",
        )
        return
    bot.reply_to(
        message,
        "👋 مرحباً بك في بوت MediTrack!\n"
        "اشترِ ترخيصك بالضغط على زر 'طلب التفعيل' داخل التطبيق.",
    )


@bot.message_handler(commands=["myid"])
def my_id(message):
    bot.reply_to(message, f"🆔 معرفك: `{message.from_user.id}`")


@bot.message_handler(commands=["test"])
def test(message):
    bot.reply_to(message, "✅ البوت يعمل")


@bot.message_handler(commands=["pending"])
def pending_users(message):
    if not is_admin(message.from_user.id):
        return
    rows = db.get_all()
    pending = [r for r in rows if r["status"] == db.STATUS_PENDING]
    if not pending:
        bot.reply_to(message, "لا توجد طلبات معلقة")
        return
    lines = []
    for r in pending:
        tr = r["transfer_number"] or "—"
        lines.append(f"/approve {r['telegram_id']} | {r['device_id']} | حوالة: {tr}")
    bot.reply_to(message, "🕐 **الطلبات المعلقة:**\n\n" + "\n".join(lines))


@bot.message_handler(commands=["approve"])
def approve_user(message):
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "استخدم: /approve USER_ID")
        return
    row = db.get_pending_by_telegram(user_id)
    if row is None:
        bot.reply_to(message, "❌ لا يوجد طلب معلق لهذا المستخدم")
        return
    device_id = row["device_id"]
    if not row["transfer_number"]:
        bot.send_message(
            message.chat.id,
            f"⏳ المستخدم لم يرسل رقم الحوالة بعد للجهاز `{device_id}`.\n"
            f"أخبره بإرساله أو ارفض: /reject {user_id}",
        )
        return
    code = generate_code(device_id)
    db.set_code(device_id, code)
    try:
        bot.send_message(
            int(user_id),
            f"✅ **تم تفعيل جهازك!**\n\n"
            f"📱 Device ID:\n`{device_id}`\n\n"
            f"🔑 كود التفعيل:\n`{code}`\n\n"
            f"انسخه والصقه داخل تطبيق MediTrack.",
        )
        send_copyable(
            int(user_id),
            "🔑 **كود التفعيل** — اضغط مطولًا على السطر التالي ثم انسخه:",
            code,
        )
    except Exception:
        bot.reply_to(message, "⚠️ تم التفعيل لكن لم أتمكن من إرسال الكود للمستخدم")
    bot.reply_to(message, f"✅ تم تفعيل Device: `{device_id}`")


@bot.message_handler(commands=["reject"])
def reject_user(message):
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "استخدم: /reject USER_ID")
        return
    row = db.get_pending_by_telegram(user_id)
    if row is None:
        bot.reply_to(message, "❌ لا يوجد طلب معلق لهذا المستخدم")
        return
    device_id = row["device_id"]
    try:
        bot.send_message(
            int(user_id),
            "❌ **تم رفض طلب التفعيل**\n\n"
            "تأكد من صحة رقم الحوالة وحاول مرة أخرى.",
        )
    except Exception:
        pass
    db.delete_device(device_id)
    bot.reply_to(message, f"❌ تم رفض Device: `{device_id}`")


@bot.message_handler(commands=["getcode"])
def get_code(message):
    if not is_admin(message.from_user.id):
        return
    try:
        device_id = message.text.split()[1].upper().replace("-", "")
    except Exception:
        bot.reply_to(message, "استخدم: /getcode DEVICE_ID")
        return
    row = db.get_device(device_id)
    if row and row["code"]:
        bot.reply_to(
            message,
            f"📱 Device: `{device_id}`\n"
            f"🔑 الكود: `{row['code']}`",
        )
        send_copyable(
            message.chat.id,
            "🔑 **كود التفعيل** — اضغط مطولًا ثم انسخه:",
            row["code"],
        )
    else:
        bot.reply_to(message, "❌ هذا الجهاز غير مفعّل")


@bot.message_handler(commands=["list"])
def list_devices(message):
    if not is_admin(message.from_user.id):
        return
    rows = db.get_all()
    if not rows:
        bot.reply_to(message, "لا توجد أجهزة")
        return
    lines = []
    for r in rows:
        lines.append(
            f"{r['date']} | {r['device_id']} | {r['telegram_id']} | "
            f"{device_status_label(r['status'])}"
        )
    bot.reply_to(message, "📋 **الأجهزة:**\n\n" + "\n".join(lines))


@bot.message_handler(commands=["revoke"])
def revoke_device(message):
    if not is_admin(message.from_user.id):
        return
    try:
        device_id = message.text.split()[1].upper().replace("-", "")
    except Exception:
        bot.reply_to(message, "استخدم: /revoke DEVICE_ID")
        return
    db.set_status(device_id, db.STATUS_REVOKED)
    bot.reply_to(message, f"🚫 تم إلغاء ترخيص: `{device_id}`")


@bot.message_handler(commands=["status"])
def status_device(message):
    if not is_admin(message.from_user.id):
        return
    device_id = message.text.split()[1].upper().replace("-", "") if len(message.text.split()) > 1 else ""
    row = db.get_device(device_id)
    if row:
        bot.reply_to(
            message,
            f"📱 Device: `{row['device_id']}`\n"
            f"👤 User: `{row['telegram_id']}\n"
            f"📊 الحالة: {device_status_label(row['status'])}",
        )
    else:
        bot.reply_to(message, "❌ الجهاز غير موجود")


@bot.message_handler(commands=["status"])
def status_help(message):
    if not is_admin(message.from_user.id):
        return
    bot.reply_to(message, "استخدم: /status DEVICE_ID")
