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
            "👋 **مرحباً بك يا إدمن!**\n\n"
            "📱 جهاز جديد: أرسل Device ID للتفعيل.\n"
            "📤 نقل ترخيص: أرسل رسالة النقل كما تأتي من التطبيق.\n\n"
            "🔧 أوامر الإدمن:\n"
            "/pending - الطلبات المعلقة\n"
            "/approve USER_ID - تفعيل طلب\n"
            "/reject USER_ID - رفض طلب\n"
            "/getcode DEVICE_ID - استرجاع كود\n"
            "/list - عرض كل الأجهزة\n"
            "/revoke DEVICE_ID - إلغاء ترخيص\n"
            "/help - مساعدة",
        )
    else:
        bot.reply_to(
            message,
            "👋 بوت تفعيل MediTrack\n\n"
            "📱 من داخل تطبيق MediTrack اضغط:\n"
            "• «احصل على كود التفعيل» لتفعيل جهاز جديد\n"
            "• «نقل الترخيص إلى هذا الجهاز» لنقل ترخيصك من جهازك القديم\n\n"
            "سيتم تحويلك هنا مع رسالة جاهزة، أرسلها فقط.",
        )


@bot.message_handler(commands=["myid"])
def get_my_id(message):
    bot.reply_to(message, f"رقم ID الخاص بك: `{message.from_user.id}`")


@bot.message_handler(commands=["test"])
def test_bot(message):
    bot.reply_to(message, "✅ البوت يعمل بشكل صحيح!")


@bot.message_handler(commands=["pending"])
def show_pending(message):
    if not is_admin(message.from_user.id):
        return
    rows = db.get_all()
    pending = [r for r in rows if r["status"] == db.STATUS_PENDING]
    if not pending:
        bot.reply_to(message, "لا توجد طلبات معلقة")
        return
    text = "📋 الطلبات المعلقة:\n\n"
    for r in pending:
        text += f"👤 User ID: `{r['telegram_id']}`\n"
        text += f"📱 Device: `{r['device_id']}`\n"
        text += f"💳 الحوالة: {r.get('transfer_number') or 'لم يرسل بعد'}\n"
        text += f"📅 {r.get('date', 'غير معروف')}\n"
        text += f"للتفعيل: /approve {r['telegram_id']}\n"
        text += f"للرفض: /reject {r['telegram_id']}\n\n"
    bot.reply_to(message, text)


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
        bot.reply_to(
            message,
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
        bot.reply_to(message, "❌ هذا الجهاز غير مفعل")


@bot.message_handler(commands=["list"])
def list_devices(message):
    if not is_admin(message.from_user.id):
        return
    rows = db.get_all()
    if not rows:
        bot.reply_to(message, "لا توجد أجهزة مسجلة")
        return
    text = "📦 **كل الأجهزة:**\n\n"
    for r in rows:
        text += f"📱 `{r['device_id']}`\n"
        text += f"👤 {r['telegram_id']} — {device_status_label(r['status'])}\n\n"
    bot.reply_to(message, text)


@bot.message_handler(commands=["revoke"])
def revoke_device(message):
    if not is_admin(message.from_user.id):
        return
    try:
        device_id = message.text.split()[1].upper().replace("-", "")
    except Exception:
        bot.reply_to(message, "استخدم: /revoke DEVICE_ID")
        return
    row = db.get_device(device_id)
    if row is None:
        bot.reply_to(message, "❌ هذا الجهاز غير مسجل")
        return
    db.set_status(device_id, db.STATUS_REVOKED)
    bot.reply_to(message, f"🚫 تم إلغاء ترخيص `{device_id}` — سيُقفل الجهاز عند تحققه")


@bot.message_handler(commands=["status"])
def status(message):
    user_id = message.from_user.id
    active = db.get_active_by_telegram(user_id)
    pending = db.get_pending_by_telegram(user_id)
    if active:
        bot.reply_to(
            message,
            "📱 **حالة ترخيصك:**\n\n"
            + "\n".join(f"✅ `{r['device_id']}`" for r in active),
        )
    elif pending:
        bot.reply_to(message, "⏳ لديك طلب تفعيل قيد التحقق.")
    else:
        bot.reply_to(message, "لا يوجد ترخيص مفعّل لديك.")


@bot.message_handler(commands=["reset"])
def reset_devices(message):
    if not is_admin(message.from_user.id):
        return
    db.delete_all()
    bot.reply_to(
        message,
        "🗑️ **تم حذف جميع الأجهزة والطلبات**\n\n"
        "بدأ النظام من جديد. أي جهاز سابق أصبح غير مسجّل.",
    )


@bot.message_handler(commands=["help"])
def help_admin(message):
    if not is_admin(message.from_user.id):
        return
    bot.reply_to(
        message,
        "🔧 **أوامر الإدمن:**\n\n"
        "/pending - الطلبات المعلقة\n"
        "/approve USER_ID - تفعيل طلب\n"
        "/reject USER_ID - رفض طلب\n"
        "/getcode DEVICE_ID - استرجاع كود\n"
        "/list - عرض كل الأجهزة\n"
        "/revoke DEVICE_ID - إلغاء ترخيص\n"
        "/status - حالة المستخدم\n"
        "/test - اختبار البوت\n"
        "/myid - معرفة رقمك",
    )


# ========== معالجة الرسائل ==========

@bot.message_handler(func=lambda m: True)
def handle(message):
    text = message.text.strip()
    user_id = int(message.from_user.id)

    if text.startswith("/"):
        return

    # رسالة نقل الترخيص
    if is_transfer_request(text):
        handle_transfer(message, text, user_id)
        return

    # المستخدم لديه طلب قيد التحقق ← أي رسالة تالية تعتبر رقم الحوالة
    pending = db.get_pending_by_telegram(user_id)
    if pending:
        handle_transfer_number(message, text, user_id, pending)
        return

    handle_activation(message, text, user_id)


def handle_transfer_number(message, text, user_id, pending):
    """استقبال رقم الحوالة بعد طلب التفعيل ثم إشعار الإدمن."""
    transfer_number = re.sub(r"[^0-9A-Za-z]", "", text)
    if len(transfer_number) < 6 or not transfer_number.isdigit():
        bot.reply_to(
            message,
            "❌ رقم الحوالة غير صحيح.\n\n"
            f"أرسل رقم الحوالة فقط كما يظهر في تطبيق البنك، "
            f"حتى أتمكن من إشعار الإدمن لكي يفعّل جهازك.\n\n"
            f"إن لم تكن تنتظر تفعيلاً، فستُعالج رسالتك كرقم حوالة؛ "
            f"الطلب الحالي للجهاز `{pending['device_id']}`.",
        )
        return

    device_id = pending["device_id"]
    db.set_transfer_number(device_id, transfer_number)

    bot.reply_to(
        message,
        "✅ **تم استلام رقم الحوالة**\n\n"
        "⏳ في انتظار تحقق الإدمن... سنتواصل معك قريباً.",
    )

    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"💳 **طلب تفعيل جديد**\n\n"
                f"👤 User ID: `{user_id}`\n"
                f"📱 Device: `{device_id}`\n"
                f"💳 رقم الحوالة: `{transfer_number}`\n"
                f"📅 {db.now_str()}\n\n"
                f"للتفعيل: /approve {user_id}\n"
                f"للرفض: /reject {user_id}",
            )
        except Exception:
            pass


def handle_activation(message, text, user_id):
    """تفعيل جهاز جديد (تدفق الدفع)."""
    device_id = extract_device_id(text)
    if not device_id or len(device_id) < 8:
        bot.reply_to(
            message,
            "❌ Device ID غير صحيح.\n\n"
            "📱 أرسل الرسالة الجاهزة من داخل تطبيق MediTrack مباشرة.",
        )
        return

    existing = db.get_device(device_id)
    if existing:
        if existing["status"] == db.STATUS_ACTIVE:
            bot.reply_to(
                message,
                f"✅ **هذا الجهاز مفعل بالفعل**\n\n"
                f"🔑 كودك:\n`{existing['code']}`",
            )
            return
        if existing["status"] == db.STATUS_PENDING:
            bot.reply_to(
                message,
                "⏳ هذا الجهاز قيد التحقق، انتظر رسالة التفعيل.",
            )
            return
        if existing["status"] in (db.STATUS_TRANSFERRED, db.STATUS_REVOKED):
            bot.reply_to(
                message,
                "🚫 ترخيص هذا الجهاز ملغي/منقول.\n"
                "للحصول على ترخيص جديد تواصل مع الدعم.",
            )
            return

    pending = db.get_pending_by_telegram(user_id)
    if pending:
        bot.reply_to(
            message,
            f"⏳ لديك طلب قيد التحقق للجهاز `{pending['device_id']}`.\n"
            f"أرسل رقم الحوالة ليتم استكماله.",
        )
        return

    db.insert_device(device_id, user_id, db.STATUS_PENDING)
    bot.reply_to(
        message,
        f"📱 **Device ID:**\n`{device_id}`\n\n"
        f"💰 **السعر:** {PRICE}\n\n"
        f"🏦 **بيانات الدفع:**\n"
        f"الوسيلة: {PAY_METHOD}\n"
        f"رقم المحفظة: `{WALLET_NUMBER}`\n"
        f"الاسم: {ACCOUNT_NAME}\n\n"
        f"📤 **بعد التحويل، أرسل رقم الحوالة هنا**",
    )
    send_copyable(
        int(user_id),
        "📋 **رقم المحفظة للتحويل** — اضغط مطولًا على السطر التالي ثم انسخه:",
        WALLET_NUMBER,
    )

    # إشعار الإدمن بطلب تفعيل جديد (بانتظار رقم الحوالة)
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"🆕 **طلب تفعيل جديد**\n\n"
                f"👤 User ID: `{user_id}`\n"
                f"📱 Device: `{device_id}`\n"
                f"📅 {db.now_str()}\n\n"
                f"بانتظار رقم الحوالة.",
            )
        except Exception:
            pass


def handle_transfer(message, text, user_id):
    """نقل الترخيص من الجهاز القديم (A) إلى الجهاز الجديد (B)."""
    new_device_id = extract_device_id(text)
    if not new_device_id or len(new_device_id) < 8:
        bot.reply_to(
            message,
            "❌ Device ID غير صحيح.\n\n"
            "📱 أرسل الرسالة الجاهزة من داخل تطبيق MediTrack على جهازك الجديد مباشرة.",
        )
        return

    active_devices = db.get_active_by_telegram(user_id)
    if not active_devices:
        bot.reply_to(
            message,
            "❌ **لا يوجد ترخيص مفعّل لنقله**\n\n"
            "لا توجد أجهزة مفعّلة مرتبطة بحسابك.\n"
            "إذا كان جهازك القديم مفعّلاً، تأكد من استخدام نفس حساب تيليغرام "
            "الذي فعّلت به جهازك الأول.",
        )
        return

    # الجهاز القديم هو آخر جهاز مفعّل (الأكثر حداثة)
    old_device = active_devices[0]

    if old_device["device_id"] == new_device_id:
        bot.reply_to(
            message,
            "❌ هذا هو نفس الجهاز المفعّل بالفعل، لا حاجة للنقل.",
        )
        return

    existing_new = db.get_device(new_device_id)
    if existing_new and existing_new["status"] == db.STATUS_ACTIVE:
        bot.reply_to(
            message,
            "❌ هذا الجهاز مفعل بالفعل بحساب آخر.\nتواصل مع الدعم.",
        )
        return

    # 1) إلغاء ترخيص الجهاز القديم
    db.set_status(old_device["device_id"], db.STATUS_TRANSFERRED)

    # 2) إنشاء ترخيص للجهاز الجديد
    new_code = generate_code(new_device_id)
    db.insert_device(new_device_id, user_id, db.STATUS_ACTIVE, code=new_code)

    # 3) إشعار المستخدم
    bot.reply_to(
        message,
        f"✅ **تم نقل الترخيص بنجاح!**\n\n"
        f"📤 الجهاز القديم:\n`{old_device['device_id']}`\n"
        f"(سيتوقف عن العمل تلقائياً)\n\n"
        f"📱 الجهاز الجديد:\n`{new_device_id}`\n\n"
        f"🔑 كود التفعيل:\n`{new_code}`\n\n"
        f"انسخ الكود والصقه داخل تطبيق MediTrack على جهازك الجديد.",
    )
    send_copyable(
        int(user_id),
        "🔑 **كود التفعيل** — اضغط مطولًا على السطر التالي ثم انسخه:",
        new_code,
    )

    # 4) إشعار الإدمن
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"📤 **نقل ترخيص**\n\n"
                f"👤 المستخدم: `{user_id}`\n"
                f"من: `{old_device['device_id']}`\n"
                f"إلى: `{new_device_id}`\n"
                f"📅 {db.now_str()}",
            )
        except Exception:
            pass


def process_update(update) -> None:
    """يستقبل تحديثاً واحداً من تيليغرام (وضع webhook) ويعالجه عبر معالجات البوت."""
    if BOT_TOKEN:
        bot.process_new_updates([update])


def set_webhook(url: str) -> None:
    """يسجل عنوان السيرفر الذي سيرسل إليه تيليغرام التحديثات."""
    if BOT_TOKEN and url:
        bot.set_webhook(url)


def poll_once(duration: float = 50) -> None:
    """يجلب التحديثات ويعالجها لمدة قصيرة ثم يتوقف.
    يُستعمل مع GitHub Actions (تشغيل مجدول كل بضع دقائق)."""
    try:
        bot.delete_webhook()
    except Exception:
        pass
    offset = 0
    end = time.time() + duration
    while time.time() < end:
        try:
            updates = bot.get_updates(offset=offset, timeout=1)
        except Exception as e:
            print("⚠️  get_updates فشل:", e)
            time.sleep(3)
            continue
        for u in updates:
            bot.process_new_updates([u])
            if u.update_id >= offset:
                offset = u.update_id + 1


if __name__ == "__main__":
    db.init_db()
    if not BOT_TOKEN:
        print("⚠️  ضع التوكن: TELEGRAM_BOT_TOKEN=... python bot.py")
        raise SystemExit(1)
    if "--once" in sys.argv:
        print("✅ جولة واحدة (GitHub Actions)...")
        poll_once()
        db.export_status_json("status.json")
        print("✅ انتهت الجولة وحدّثت status.json")
    else:
        print("✅ البوت يعمل (polling)...")
        bot.infinity_polling()
