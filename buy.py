from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime
from web3 import Web3
from maintenance import check_maintenance

from config import (
    CRYPTO_LIST,
    TOKEN_CONTRACTS,
    TRANSACTION_CHANNEL_ID,
    FEATURES_ENABLED,
    MIN_BUY_RP,
    BUY_FEE_PERCENT,
    BUY_FEE_MIN,
    RPC_ARB,
    RPC_BY_NETWORK,
    get_realtime_price
)
from database import load_db, save_db, get_user
from wallet import send_token, get_hot_wallet_token_balance
from states import (
    BUY_TOKEN, BUY_NETWORK, BUY_AMOUNT, BUY_WALLET, BUY_CONFIRM
)

# =========================
# START BUY
# =========================
async def buy(update, context):
    # =========================
    # CEK FITUR AKTIF / MATI
    # =========================
    if await check_maintenance(update, context):
        return

    if not FEATURES_ENABLED.get("buy", True):
        await update.message.reply_text("⚠️ Fitur buy sedang dalam perbaikan.")
        return

    # =========================
    # FUNGSI ASLI BUY
    # =========================
    context.user_data.clear()
    context.user_data["state"] = BUY_TOKEN

    buttons = [
        [InlineKeyboardButton(t, callback_data=f"buytoken|{t}")]
        for t in CRYPTO_LIST
    ]

    try:
        rates = get_realtime_price()
        rate_text = "\n".join([f"{t}: Rp {int(rates.get(t,0)):,}" for t in CRYPTO_LIST])
    except Exception:
        rate_text = "⚠️ Gagal fetch harga realtime"

    await update.message.reply_text(
        f"🛒 *BELI CRYPTO*\n\nPilih token:\n{rate_text}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# =========================
# TOKEN
# =========================
async def buy_token(update, context):
    q = update.callback_query
    await q.answer()

    if context.user_data.get("state") != BUY_TOKEN:
        return

    token = q.data.split("|")[1]
    context.user_data["token"] = token
    context.user_data["state"] = BUY_NETWORK

    try:
        buttons = [
            [InlineKeyboardButton(n, callback_data=f"buynet|{n}")]
            for n in CRYPTO_LIST[token]
        ]
    except KeyError:
        await q.edit_message_text("❌ Token tidak tersedia", reply_markup=None)
        return

    await q.edit_message_text(
        f"Token: *{token}*\n\nPilih network:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# =========================
# NETWORK
# =========================
async def buy_network(update, context):
    q = update.callback_query
    await q.answer()

    if context.user_data.get("state") != BUY_NETWORK:
        return

    context.user_data["network"] = q.data.split("|")[1]
    context.user_data["state"] = BUY_AMOUNT

    await q.edit_message_text("Masukkan jumlah beli (Rp):")

# =========================
# BUY AMOUNT
# =========================
async def buy_amount(update, context):
    if context.user_data.get("state") != BUY_AMOUNT:
        return

    try:
        amount = int(update.message.text.replace(".", "").replace(",", ""))
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Nominal tidak valid.")
        return

    # =========================
    # 🔻 MINIMAL PEMBELIAN
    # =========================
    if amount < MIN_BUY_RP:
        await update.message.reply_text(
            "⚠️ *Nominal Terlalu Kecil*\n\n"
            f"Minimal pembelian adalah:\n"
            f"Rp {MIN_BUY_RP:,}\n\n"
            "Silakan masukkan ulang nominal.",
            parse_mode="Markdown"
        )
        return

    # =========================
    # 🧾 HITUNG FEE (DIPOTONG)
    # =========================
    fee = int(amount * BUY_FEE_PERCENT / 100)
    if fee < BUY_FEE_MIN:
        fee = BUY_FEE_MIN

    net_amount = amount - fee
    if net_amount <= 0:
        await update.message.reply_text(
            "❌ Nominal terlalu kecil setelah dipotong fee.\n"
            "Silakan naikkan jumlah pembelian."
        )
        return

    # =========================
    # LOGIC ASLI (TETAP)
    # =========================
    uid = str(update.effective_user.id)
    db = load_db()
    user = get_user(db, uid)

    # ❌ SALDO USER (TETAP PAKAI amount)
    if user["balance"] < amount:
        await update.message.reply_text("❌ Saldo tidak mencukupi.")
        context.user_data.clear()
        return

  # =========================
    # SIMPAN KE CONTEXT
    # =========================
    context.user_data["amount"] = amount          # total potong saldo
    context.user_data["fee"] = fee                # fee admin
    context.user_data["net_amount"] = net_amount  # nilai beli bersih

    context.user_data["state"] = BUY_WALLET

    await update.message.reply_text(
        "Masukkan alamat wallet tujuan:\n\n"
        f"💰 Nominal      : Rp {amount:,}\n"
        f"🧾 Fee admin   : Rp {fee:,}\n"
        f"✅ Nilai beli  : Rp {net_amount:,}"
    )


    # =========================
    # 🔥 CEK SALDO HOT WALLET
    # =========================
    token = context.user_data["token"]
    network = context.user_data["network"]

    try:
        rates = get_realtime_price()
        rate = rates.get(token, 0)
        token_amount = amount / rate if rate > 0 else 0
    except:
        token_amount = 0

    try:
        token_data = TOKEN_CONTRACTS[token][network]
    except KeyError:
        await update.message.reply_text("❌ Data token/network tidak ditemukan.")
        context.user_data.clear()
        return

    from wallet import get_hot_wallet_token_balance
    hot_balance = get_hot_wallet_token_balance(
        token_data["address"],
        token_data["decimals"],
        rpc=ARB_RPC if network == "ARB_TEST" else None
    )


    # 🔴 JIKA HOT WALLET TIDAK CUKUP
    if token_amount > hot_balance:
        await update.message.reply_text(
            "⚠️ *Likuiditas Hot Wallet Tidak Mencukupi*\n\n"
            f"Permintaan estimasi : *{token_amount:.6f} {token}*\n"
            f"Saldo tersedia     : *{hot_balance:.6f} {token}*\n\n"
            "Silakan masukkan ulang nominal\n"
            f"(maksimum setara {hot_balance:.6f} {token}).",
            parse_mode="Markdown"
        )
        return

    # =========================
    # ✅ LANJUT NORMAL
    # =========================
    context.user_data["amount"] = amount
    context.user_data["state"] = BUY_WALLET

    await update.message.reply_text("Masukkan alamat wallet tujuan:")

# =========================
# WALLET
# =========================
async def buy_wallet(update, context):
    if context.user_data.get("state") != BUY_WALLET:
        return

    wallet = update.message.text.strip()

    if not Web3.is_address(wallet):
        await update.message.reply_text("❌ Alamat wallet tidak valid")
        return

    context.user_data["wallet"] = Web3.to_checksum_address(wallet)
    context.user_data["state"] = BUY_CONFIRM

    await update.message.reply_text(
        "⚠️ *Konfirmasi Pembelian*\n\n"
        f"Token  : {context.user_data['token']}\n"
        f"Network: {context.user_data['network']}\n"
        f"Rp     : {context.user_data['amount']:,}\n"
        f"Wallet : `{context.user_data['wallet']}`\n\n"
        "Ketik *YA* untuk lanjut",
        parse_mode="Markdown"
    )

# =========================
# CONFIRM & EXECUTE
# =========================
async def buy_confirm(update, context):
    if context.user_data.get("state") != BUY_CONFIRM:
        return

    if update.message.text.upper() != "YA":
        await update.message.reply_text("❌ Transaksi dibatalkan")
        context.user_data.clear()
        return

    uid = str(update.effective_user.id)
    db = load_db()
    user = get_user(db, uid)

    # =========================
    # DATA ASLI (TIDAK DIUBAH)
    # =========================
    amount_rp = context.user_data["amount"]  # total potong saldo
    token = context.user_data["token"]
    network = context.user_data["network"]
    wallet_to = context.user_data["wallet"]

    # =========================
    # 🔧 UPGRADE: NET AMOUNT
    # =========================
    net_amount = context.user_data.get("net_amount", amount_rp)
    fee = context.user_data.get("fee", 0)

    # =========================
    # CEK SALDO
    # =========================
    if user["balance"] < amount_rp:
        await update.message.reply_text("❌ Saldo tidak cukup")
        context.user_data.clear()
        return

  # =========================
    # POTONG SALDO (LOCK)
    # =========================
    user["balance"] -= amount_rp
    save_db(db)

    # =========================
    # HITUNG TOKEN (PAKAI NET)
    # =========================
    try:
        rates = get_realtime_price()
        rate = rates.get(token, 0)
        token_amount = net_amount / rate if rate > 0 else 0
    except Exception:
        token_amount = 0

    try:
        token_data = TOKEN_CONTRACTS[token][network]
    except KeyError:
        await update.message.reply_text("❌ Data token/network tidak ditemukan")
        user["balance"] += amount_rp  # rollback
        save_db(db)
        context.user_data.clear()
        return

    try:
        tx_hash = send_token(
            token_address=token_data["address"],
            to=wallet_to,
            amount=token_amount,
            decimals=token_data["decimals"],
            rpc=RPC_BY_NETWORK.get(network)
        )


    except Exception as e:
        # =========================
        # ROLLBACK
        # =========================
        user["balance"] += amount_rp
        save_db(db)
        await update.message.reply_text(f"❌ Transaksi gagal\n{str(e)}")
        context.user_data.clear()
        return

    context.user_data.clear()

    # =========================
    # OUTPUT USER
    # =========================
    await update.message.reply_text(
        "✅ *BELI BERHASIL*\n\n"
        f"Token        : {token}\n"
        f"Jumlah       : {token_amount:.6f}\n"
        f"Network      : {network}\n"
        f"Nominal      : Rp {amount_rp:,}\n"
        f"Fee admin    : Rp {fee:,}\n"
        f"Nilai beli   : Rp {net_amount:,}\n\n"
        f"TX Hash:\n`{tx_hash}`",
        parse_mode="Markdown"
    )

    # =========================
    # LOG CHANNEL
    # =========================
    if TRANSACTION_CHANNEL_ID:
        await context.bot.send_message(
            TRANSACTION_CHANNEL_ID,
            "💰 *BUY*\n"
            f"User : `{uid}`\n"
            f"Nominal : Rp {amount_rp:,}\n"
            f"Fee     : Rp {fee:,}\n"
            f"Net     : Rp {net_amount:,}\n"
            f"TX      : `{tx_hash}`",
            parse_mode="Markdown"
        )
