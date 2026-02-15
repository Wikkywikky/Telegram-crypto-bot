from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
from config import ADMIN_IDS, WITHDRAW_METHODS, TRANSACTION_CHANNEL_ID, MIN_WITHDRAW_RP, get_realtime_price
from states import WD_METHOD, WD_TARGET, WD_NAME, WD_AMOUNT
from database import load_db, save_db, get_user, create_withdraw
from maintenance import check_maintenance

# =========================
# STEP 1 – START WITHDRAW
# =========================
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_maintenance(update, context):
        return

    context.user_data.clear()
    context.user_data["state"] = WD_METHOD

    keyboard = [
        [InlineKeyboardButton(m, callback_data=f"wdmethod|{m}")] for m in WITHDRAW_METHODS
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        rates = get_realtime_price()
        rate_text = "\n".join([f"{t}: Rp {int(rates[t]):,}" for t in rates])
    except Exception:
        rate_text = "⚠️ Gagal fetch harga realtime"

    await update.message.reply_text(
        f"💸 *WITHDRAW IDR*\n\nPilih metode:\n\nHarga realtime token (referensi):\n{rate_text}",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# =========================
# STEP 2 – METODE INLINE CALLBACK
# =========================
async def withdraw_method_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if context.user_data.get("state") != WD_METHOD:
        await q.answer("❌ Tidak dalam proses withdraw", show_alert=True)
        return

    method = q.data.split("|")[1]
    context.user_data["method"] = method
    context.user_data["state"] = WD_TARGET

    await q.edit_message_text(
        f"💳 Metode dipilih: *{method}*\n\nMasukkan nomor tujuan (HP / Rekening):",
        parse_mode="Markdown"
    )

# =========================
# STEP 3 – TARGET
# =========================
async def withdraw_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != WD_TARGET:
        return

    context.user_data["target"] = update.message.text.strip()
    context.user_data["state"] = WD_NAME
    await update.message.reply_text("Masukkan nama penerima:")

# =========================
# STEP 4 – NAME
# =========================
async def withdraw_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != WD_NAME:
        return

    context.user_data["name"] = update.message.text.strip()
    context.user_data["state"] = WD_AMOUNT
    await update.message.reply_text("Masukkan jumlah withdraw (Rp):")

# =========================
# STEP 5 – AMOUNT & SUBMIT
# =========================
async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != WD_AMOUNT:
        return

    uid = str(update.effective_user.id)

    try:
        amount = int(update.message.text.replace(".", "").replace(",", ""))
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Nominal tidak valid.")
        return

    db = load_db()
    user = get_user(db, uid)

    if amount < MIN_WITHDRAW_RP:
        await update.message.reply_text(
            f"⚠️ *Withdraw Ditolak*\nMinimal withdraw adalah Rp {MIN_WITHDRAW_RP:,}\n\n"
             "Masukan jumlah yang benar.",
            parse_mode="Markdown"
        )
        return

    if amount > user["balance"]:
        await update.message.reply_text("❌ Saldo tidak mencukupi.")
        return

    method = context.user_data["method"]
    target = context.user_data["target"]
    name = context.user_data["name"]

    try:
        rates = get_realtime_price()
        token_estimate_text = "\n".join([f"{t}: {amount / rates[t]:.6f} {t}" for t in rates])
    except Exception:
        token_estimate_text = "⚠️ Gagal fetch harga realtime"

    await update.message.reply_text(f"💡 Estimasi token dari nominal withdraw:\n{token_estimate_text}")

    withdraw_id = create_withdraw(db, uid, amount, method, target, name)
    save_db(db)
    context.user_data.clear()

    await update.message.reply_text("⏳ Withdraw diajukan, menunggu approval admin.")

    # tombol admin
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"wd|approve|{withdraw_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"wd|reject|{withdraw_id}")
    ]])

    msg = (
        f"🛑 *WITHDRAW REQUEST*\n\n"
        f"ID: `{withdraw_id}`\nUser: `{uid}`\nJumlah: Rp {amount:,}\n"
        f"Metode: {method}\nRekening: {target}\nPenerima: {name}\n⏳ Status: Pending"
    )

    for admin in ADMIN_IDS:
        await context.bot.send_message(chat_id=admin, text=msg, parse_mode="Markdown", reply_markup=keyboard)

    if TRANSACTION_CHANNEL_ID:
        await context.bot.send_message(
            TRANSACTION_CHANNEL_ID,
            f"🟠 WITHDRAW REQUEST\nID: {withdraw_id}\nUser: {uid}\nRp {amount:,}"
        )

  # =========================
# ADMIN APPROVE / REJECT
# =========================
async def withdraw_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    try:
        _, action, withdraw_id = q.data.split("|")
    except:
        await q.edit_message_text("❌ Callback data tidak valid")
        return

    admin_uid = str(q.from_user.id)
    if admin_uid not in [str(a) for a in ADMIN_IDS]:
        await q.answer("❌ Kamu bukan admin", show_alert=True)
        return

    db = load_db()
    wd = db.get("withdraws", {}).get(withdraw_id)
    if not wd:
        await q.edit_message_text("❌ Withdraw tidak ditemukan")
        return

    uid = wd["user_id"]
    amount = wd["amount"]
    method = wd.get("method", "-")
    target = wd.get("target", "-")
    name = wd.get("name", "-")

    if wd.get("status") != "pending":
        await q.edit_message_text("⚠️ Withdraw sudah diproses", reply_markup=None)
        return

    user = db.get("users", {}).get(uid)
    if not user:
        db["users"][uid] = {"balance": 0, "wallet": None}
        user = db["users"][uid]

    time_now = datetime.now().isoformat()

    if action == "approve":
        if user.get("balance", 0) < amount:
            await q.answer("❌ Saldo user tidak cukup", show_alert=True)
            return

        user["balance"] -= amount
        wd["status"] = "approved"
        wd["approved_by"] = admin_uid
        wd["approved_at"] = time_now

        await context.bot.send_message(uid, f"✅ Withdraw Rp {amount:,} telah disetujui oleh admin.")

        msg = (
            f"✅ Withdraw APPROVED\nUser: `{uid}`\nJumlah: Rp {amount:,}\n"
            f"Metode: {method}\nRekening: {target}\nPenerima: {name}"
        )
    else:  # reject
        wd["status"] = "rejected"
        wd["rejected_by"] = admin_uid
        wd["rejected_at"] = time_now

        await context.bot.send_message(uid, f"❌ Withdraw Rp {amount:,} ditolak admin.")

        msg = (
            f"❌ Withdraw REJECTED\nUser: `{uid}`\nJumlah: Rp {amount:,}\n"
            f"Metode: {method}\nRekening: {target}\nPenerima: {name}"
        )

    save_db(db)
    await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=None)

    if TRANSACTION_CHANNEL_ID:
        await context.bot.send_message(
            TRANSACTION_CHANNEL_ID,
            f"💸 *WITHDRAW TRANSACTION*\n{msg}\nWaktu: {time_now}",
            parse_mode="Markdown"
        )
