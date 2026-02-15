from maintenance import check_maintenance
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
from config import PAYMENT_METHODS, ADMIN_IDS, TRANSACTION_CHANNEL_ID, MIN_TOPUP_RP, get_realtime_price
from database import load_db, save_db
from states import TOPUP_AMOUNT, TOPUP_METHOD, TOPUP_NAME, TOPUP_PROOF

# =========================
# /topup COMMAND
# =========================
async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_maintenance(update, context):
        return

    context.user_data.clear()
    context.user_data["state"] = TOPUP_AMOUNT

    # Tampilkan harga realtime token sebagai referensi
    try:
        rates = get_realtime_price()  # dict: {"BTC": 500000000, "ETH": 30000000}
        rate_text = "\n".join([f"{t}: Rp {int(rates[t]):,}" for t in rates])
    except Exception as e:
        rate_text = "⚠️ Gagal fetch harga realtime"

    await update.message.reply_text(
        f"💰 Masukkan jumlah topup (Rp)\n\nHarga realtime token (referensi):\n{rate_text}"
    )


# =========================
# INPUT HANDLER
# =========================
from config import MIN_TOPUP_RP

async def input_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    state = context.user_data.get("state")
    db = load_db()

    # -------------------------
    # INPUT AMOUNT
    # -------------------------
    if state == TOPUP_AMOUNT:
        try:
            amount = int(update.message.text.replace(".", "").replace(",", ""))
            if amount <= 0:
                raise ValueError
        except:
            await update.message.reply_text("❌ Masukkan angka yang valid.")
            return

        # =========================
        # 🔻 MINIMAL TOPUP (TAMBAHAN)
        # =========================
        if amount < MIN_TOPUP_RP:
            await update.message.reply_text(
                f"⚠️ *Nominal Topup Terlalu Kecil*\n\n"
                f"Minimal topup adalah:\n"
                f"Rp {MIN_TOPUP_RP:,}\n\n"
                f"Silakan masukkan ulang nominal.",
                parse_mode="Markdown"
            )
            return

        # =========================
        # LOGIC ASLI (TIDAK DIUBAH)
        # =========================
        context.user_data["topup_amount"] = amount
        context.user_data["state"] = TOPUP_METHOD

        # Tampilkan tombol metode
        buttons = [
            [InlineKeyboardButton(k, callback_data=f"pay_{k}")]
            for k in PAYMENT_METHODS
        ]

        # Estimasi token dari harga realtime
        try:
            rates = get_realtime_price()
            rate_text = "\n".join([
                f"{t}: {amount / rates[t]:.6f} {t}"
                for t in rates
            ])
        except Exception:
            rate_text = "⚠️ Gagal fetch harga realtime"

        await update.message.reply_text(
            f"💳 Pilih metode pembayaran:\n\n"
            f"Estimasi token dari nominal:\n{rate_text}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return


    # -------------------------
    # INPUT NAMA PENGIRIM
    # -------------------------
    if state == TOPUP_NAME:
        sender_name = update.message.text.strip()
        if not sender_name:
            await update.message.reply_text("❌ Masukkan nama pengirim")
            return

        context.user_data["sender_name"] = sender_name
        context.user_data["state"] = TOPUP_PROOF

        method = context.user_data.get("topup_method")
        instruction = PAYMENT_METHODS.get(method, "-")

        await update.message.reply_text(
            f"📸 Kirim bukti transfer (foto) untuk topup kamu.\n\n"
            f"💳 Metode: {method}\n"
            f"✏️ Nama pengirim: {sender_name}\n"
            f"💰 Jumlah: Rp {context.user_data['topup_amount']:,}"
        )
        return

    # -------------------------
    # INPUT BUKTI (FOTO)
    # -------------------------
    if state == TOPUP_PROOF:
        if not update.message.photo:
            await update.message.reply_text("❌ Kirim bukti berupa FOTO")
            return

        file_id = update.message.photo[-1].file_id
        amount = context.user_data["topup_amount"]
        method = context.user_data["topup_method"]
        sender_name = context.user_data["sender_name"]

        # simpan pending topup
        db.setdefault("topups", {})
        topup_id = str(len(db["topups"]) + 1)
        db["topups"][topup_id] = {
            "user_id": uid,
            "amount": amount,
            "method": method,
            "sender_name": sender_name,
            "bukti": file_id,
            "status": "pending",
            "created": datetime.now().isoformat()
        }
        save_db(db)

        # tombol admin approve/reject
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"topup|approve|{topup_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"topup|reject|{topup_id}")
        ]])

        caption = (
            f"🧾 *PERMINTAAN TOPUP*\n\n"
            f"👤 User ID: `{uid}`\n"
            f"💰 Amount: Rp {amount:,}\n"
            f"💳 Metode: {method}\n"
            f"✏️ Nama Pengirim: {sender_name}\n"
            f"🏦 Alamat / Instruksi: {PAYMENT_METHODS.get(method,'-')}"
        )

        # kirim FOTO ke semua admin
        for admin in ADMIN_IDS:
            await context.bot.send_photo(
                chat_id=admin,
                photo=file_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )

        context.user_data.clear()
        await update.message.reply_text("⏳ Bukti diterima, menunggu approval admin")
        return

  # =========================
# PAYMENT METHOD CALLBACK
# =========================
async def pay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    method = q.data.replace("pay_", "")
    context.user_data["topup_method"] = method
    context.user_data["state"] = TOPUP_NAME

    instruction = PAYMENT_METHODS.get(method, "-")
    await q.message.reply_text(
        f"💳 Kamu memilih metode {method}.\n"
        f"🏦 Alamat Topup: {instruction}\n\n"
        "Masukkan NAMA PENGIRIM untuk konfirmasi:"
    )


# =========================
# ADMIN APPROVE / REJECT CALLBACK
# =========================
async def topup_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    data = q.data  # contoh: topup|approve|1
    try:
        _, action, topup_id = data.split("|")
    except:
        if q.message.photo:
            await q.edit_message_caption("❌ Callback data tidak valid", reply_markup=None)
        else:
            await q.edit_message_text("❌ Callback data tidak valid", reply_markup=None)
        return

    admin_uid = str(q.from_user.id)
    if admin_uid not in [str(a) for a in ADMIN_IDS]:
        await q.answer("❌ Kamu bukan admin", show_alert=True)
        return

    db = load_db()
    topup = db.get("topups", {}).get(topup_id)
    if not topup:
        if q.message.photo:
            await q.edit_message_caption("❌ Topup tidak ditemukan", reply_markup=None)
        else:
            await q.edit_message_text("❌ Topup tidak ditemukan", reply_markup=None)
        return

    uid = topup["user_id"]
    amount = topup["amount"]
    method = topup.get("method", "-")
    sender_name = topup.get("sender_name", f"User {uid}")

    # CEK STATUS
    if topup["status"] != "pending":
        if q.message.photo:
            await q.edit_message_caption("⚠️ Topup sudah diproses", reply_markup=None)
        else:
            await q.edit_message_text("⚠️ Topup sudah diproses", reply_markup=None)
        return

    # pastikan user ada di DB
    db.setdefault("users", {})
    user = db["users"].get(uid)
    if not user:
        db["users"][uid] = {"balance": 0, "wallet": None}
        user = db["users"][uid]

    time_now = datetime.now().isoformat()

    # -------------------------
    # PROSES APPROVE / REJECT
    # -------------------------
    if action == "approve":
        user["balance"] += amount
        topup["status"] = "approved"
        topup["approved_by"] = admin_uid
        topup["approved_at"] = time_now

        await context.bot.send_message(
            uid,
            f"✅ Topup Rp {amount:,} telah disetujui oleh admin."
        )

        msg = (
            f"✅ Topup APPROVED\n"
            f"👤 User: `{uid}`\n"
            f"✏️ Nama Pengirim: {sender_name}\n"
            f"💰 Jumlah: Rp {amount:,}\n"
            f"💳 Metode: {method}"
        )
    else:  # reject
        topup["status"] = "rejected"
        topup["rejected_by"] = admin_uid
        topup["rejected_at"] = time_now

        await context.bot.send_message(
            uid,
            f"❌ Topup Rp {amount:,} ditolak admin."
        )

        msg = (
            f"❌ Topup REJECTED\n"
            f"👤 User: `{uid}`\n"
            f"✏️ Nama Pengirim: {sender_name}\n"
            f"💰 Jumlah: Rp {amount:,}\n"
            f"💳 Metode: {method}"
        )

    save_db(db)

    # =========================
    # HILANGKAN TOMBOL ADMIN
    # =========================
    try:
        if q.message.photo:
            await q.edit_message_caption(msg, parse_mode="Markdown", reply_markup=None)
        else:
            await q.edit_message_text(msg, parse_mode="Markdown", reply_markup=None)
    except Exception as e:
        print("ERROR EDIT MESSAGE:", e)

    # =========================
    # KIRIM KE CHANNEL TRANSPARANSI
    # =========================
    if TRANSACTION_CHANNEL_ID:
        await context.bot.send_message(
            TRANSACTION_CHANNEL_ID,
            f"💰 *TOPUP TRANSACTION*\n{msg}\nWaktu: {time_now}",
            parse_mode="Markdown"
        )
