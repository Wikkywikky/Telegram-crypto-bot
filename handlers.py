from maintenance import maintenance_set, maintenance_stop
from telegram import Update
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from database import load_db, save_db, get_user

# =========================
# IMPORT MODULE
# =========================
from topup import topup, pay_callback, input_topup, topup_admin_callback

from buy import (
    buy,
    buy_token,
    buy_network,
    buy_amount,
    buy_wallet,
    buy_confirm
)

from sell import (
    sell,
    sell_token,
    sell_network,
    sell_amount,
    sell_tx,
    sell_sender
)

from withdraw import (
    withdraw_start,
    withdraw_method_inline,
    withdraw_target,
    withdraw_name,
    withdraw_amount,
    withdraw_admin
)

from states import (
    # TOPUP
    TOPUP_AMOUNT,
    TOPUP_METHOD,
    TOPUP_PROOF,
    TOPUP_NAME,

    # BUY
    BUY_AMOUNT,
    BUY_WALLET,
    BUY_CONFIRM,

    # SELL
    SELL_AMOUNT,
    SELL_TX,
    SELL_SENDER,

    # WITHDRAW
    WD_METHOD,
    WD_TARGET,
    WD_NAME,
    WD_AMOUNT
)

# =========================
# IMPORT CONFIG UNTUK HARGA REALTIME
# =========================                                                                                                                                                                                          from config import FEATURES_ENABLED, ADMIN_IDS, get_realtime_price

# =========================
# TEXT ROUTER (STATE BASED)
# =========================
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")

    # ---------- TOPUP ----------
    if state in [TOPUP_AMOUNT, TOPUP_METHOD, TOPUP_NAME, TOPUP_PROOF]:
        await input_topup(update, context)

    # ---------- BUY ----------
    elif state == BUY_AMOUNT:
        await buy_amount(update, context)
    elif state == BUY_WALLET:
        await buy_wallet(update, context)
    elif state == BUY_CONFIRM:
        await buy_confirm(update, context)

    # ---------- SELL ----------
    elif state == SELL_AMOUNT:
        await sell_amount(update, context)
    elif state == SELL_TX:
        await sell_tx(update, context)
    elif state == SELL_SENDER:
        await sell_sender(update, context)

    # ---------- WITHDRAW ----------
    elif state == WD_METHOD:
        await withdraw_method_inline(update, context)
    elif state == WD_TARGET:
        await withdraw_target(update, context)
    elif state == WD_NAME:
        await withdraw_name(update, context)
    elif state == WD_AMOUNT:
        await withdraw_amount(update, context)

    else:
        if update.message:
            await update.message.reply_text(
                "⚠   Perintah tidak dikenali.\n"
                "⬇️    Gunakan perintah yang tersedia."
            )

# =========================
# ADMIN TOGGLE FEATURE
# =========================
async def toggle_feature(update, context):
    uid = str(update.effective_user.id)
    if uid not in [str(a) for a in ADMIN_IDS]:
        await update.message.reply_text("❌ Kamu bukan admin.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Gunakan format: /toggle [buy|sell] [on|off]")
        return

    feature, status = context.args
    feature = feature.lower()
    status = status.lower()

    if feature not in ["buy", "sell"]:
        await update.message.reply_text("Fitur hanya: buy / sell")
        return

    FEATURES_ENABLED[feature] = (status == "on")
    await update.message.reply_text(f"⚡ Fitur {feature} sekarang {'aktif' if status=='on' else 'mati'}")

# =========================
# COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    db = load_db()
    get_user(db, uid)
    save_db(db)

    try:
        rates = get_realtime_price()
        usdt_price = rates.get("USDT", 0)
    except Exception:
        usdt_price = 0

    await update.message.reply_text(
        f"👋 *Selamat datang di Paxi Tip Bot*\n\n"
        f"Harga realtime USDT: Rp {usdt_price:,}\n\n"
        "/topup – Isi saldo\n"
        "/saldo – Cek saldo\n"
        "/buy – Beli crypto\n"
        "/sell – Jual crypto\n"
        "/withdraw – Tarik saldo\n"
        "/cancel – Batalkan proses",
        parse_mode="Markdown"
    )

async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    db = load_db()
    user = get_user(db, uid)
    save_db(db)

    try:
        rates = get_realtime_price()
        usdt_price = rates.get("USDT", 0)
    except Exception:
        usdt_price = 0

    await update.message.reply_text(
        f"💰 *Saldo kamu*\nRp {user['balance']:,}\n\n"
        f"Harga USDT realtime: Rp {usdt_price:,}",
        parse_mode="Markdown"
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Proses dibatalkan.")

# =========================
# ERROR HANDLER
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("ERROR:", context.error)

# =========================
# REGISTER HANDLERS
# =========================
def register(app):
    # ---------- COMMAND ----------
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(CommandHandler("topup", topup))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("sell", sell))
    app.add_handler(CommandHandler("toggle", toggle_feature))
    app.add_handler(CommandHandler("withdraw", withdraw_start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("setmaintenance", maintenance_set))
    app.add_handler(CommandHandler("stopmaintenance", maintenance_stop))

    # ---------- CALLBACK ----------
    app.add_handler(CallbackQueryHandler(pay_callback, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(topup_admin_callback, pattern="^topup\\|"))

    # BUY
    app.add_handler(CallbackQueryHandler(buy_token, pattern="^buytoken\\|"))
    app.add_handler(CallbackQueryHandler(buy_network, pattern="^buynet\\|"))

    # SELL
    app.add_handler(CallbackQueryHandler(sell_token, pattern="^selltoken_"))
    app.add_handler(CallbackQueryHandler(sell_network, pattern="^sellnet_"))

    # WITHDRAW
    app.add_handler(CallbackQueryHandler(withdraw_admin, pattern=r"^wd\|"))
    app.add_handler(CallbackQueryHandler(withdraw_method_inline, pattern=r"^wdmethod\|"))

    # ---------- MESSAGE ----------
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, input_topup))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    # ---------- ERROR ----------
    app.add_error_handler(error_handler)
