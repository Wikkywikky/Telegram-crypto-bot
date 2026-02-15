from maintenance import check_maintenance
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from web3 import Web3
from config import CRYPTO_LIST, TOKEN_CONTRACTS, BOT_WALLET, BSC_RPC, TRANSACTION_CHANNEL_ID, FEATURES_ENABLED, MIN_SELL_FEE_RP, RPC_BY_NETWORK, get_realtime_price
from database import load_db, save_db
from states import SELL_SENDER, SELL_AMOUNT, SELL_TX
from datetime import datetime
from wallet import get_w3
from web3.middleware import geth_poa_middleware

TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex()

# =========================
# GET TOKEN AMOUNT FROM TX
# =========================
def get_token_amount_from_tx(
    tx_hash,
    token_address,
    bot_wallet,
    sender_wallet,
    decimals,
    w3
):
    tx = w3.eth.get_transaction(tx_hash)
    receipt = w3.eth.get_transaction_receipt(tx_hash)

    if not receipt or receipt.status != 1:
        raise Exception("TX gagal atau belum confirmed")

    # =========================
    # ✅ NATIVE COIN (ETH / BNB)
    # =========================
    if token_address is None:
        if tx["to"] is None:
            raise Exception("TX contract creation tidak valid")

        if tx["from"].lower() != sender_wallet.lower():
            raise Exception("Alamat pengirim tidak sesuai")

        if tx["to"].lower() != bot_wallet.lower():
            raise Exception("Wallet tujuan tidak sesuai")

        return w3.from_wei(tx["value"], "ether")

    # =========================
    # ✅ ERC20 TOKEN
    # =========================
    transfer_topic = Web3.keccak(
        text="Transfer(address,address,uint256)"
    ).hex()

    total_amount = 0

    for log in receipt.logs:
        if log.address.lower() != token_address.lower():
            continue

        if log.topics[0].hex() != transfer_topic:
            continue

        from_addr = Web3.to_checksum_address(
            "0x" + log.topics[1].hex()[-40:]
        )
        to_addr = Web3.to_checksum_address(
            "0x" + log.topics[2].hex()[-40:]
        )

        if from_addr.lower() != sender_wallet.lower():
            continue

        if to_addr.lower() != bot_wallet.lower():
            continue

        amount_int = int.from_bytes(log.data, byteorder="big")
        total_amount += amount_int

    if total_amount == 0:
        raise Exception("Transfer valid tidak ditemukan")

    return total_amount / (10 ** decimals)

# =========================
# START SELL
# =========================
async def sell(update, context):
    if await check_maintenance(update, context):
        return

    if not FEATURES_ENABLED.get("sell", True):
        await update.message.reply_text("⚠️ Fitur sell sedang dalam perbaikan.")
        return
    # fungsi sell asli lanjut di sini

    context.user_data.clear()
    buttons = [[InlineKeyboardButton(t, callback_data=f"selltoken_{t}")] for t in CRYPTO_LIST]

    # Tampilkan harga realtime token (opsional)
    try:
        rates = get_realtime_price()
        rate_text = "\n".join([f"{t}: Rp {int(rates.get(t,0)):,}" for t in CRYPTO_LIST])
    except Exception:
        rate_text = "⚠️ Gagal fetch harga realtime"

    await update.message.reply_text(
        f"Pilih token yang ingin dijual:\n{rate_text}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def sell_token(update, context):
    q = update.callback_query
    await q.answer()
    token = q.data.replace("selltoken_", "")
    context.user_data["token"] = token

    try:
        buttons = [[InlineKeyboardButton(n, callback_data=f"sellnet_{n}")] for n in CRYPTO_LIST[token]]
    except KeyError:
        await q.message.edit_text("❌ Token tidak tersedia", reply_markup=None)
        return

    await q.message.edit_text("Pilih network:", reply_markup=InlineKeyboardMarkup(buttons))

async def sell_network(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data["network"] = q.data.replace("sellnet_", "")
    context.user_data["state"] = SELL_SENDER
    await q.message.edit_text(
        "Masukkan *alamat wallet pengirim* (wallet yang akan mengirim token):",
        parse_mode="Markdown"
    )

async def sell_sender(update, context):
    if context.user_data.get("state") != SELL_SENDER:
        return
    sender_wallet = update.message.text.strip()
    if not Web3.is_address(sender_wallet):
        await update.message.reply_text("❌ Alamat wallet tidak valid.")
        return
    context.user_data["sender_wallet"] = Web3.to_checksum_address(sender_wallet)
    context.user_data["state"] = SELL_AMOUNT
    await update.message.reply_text(
        "🧮 Masukkan *jumlah token* yang ingin kamu sell:",
        parse_mode="Markdown"
    )


async def sell_amount(update, context):
    if context.user_data.get("state") != SELL_AMOUNT:
        return

    try:
        amount_token = float(update.message.text.strip())
        if amount_token <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Masukkan jumlah token yang valid (angka > 0).")
        return

    token = context.user_data["token"]

# =========================
    # ESTIMASI NILAI SELL
    # =========================
    try:
        rates = get_realtime_price()
        rate = rates.get(token, 0)
        gross_rp = int(amount_token * rate)
    except Exception:
        gross_rp = 0

    fee_rp = MIN_SELL_FEE_RP
    net_rp = gross_rp - fee_rp

    if net_rp <= 0:
        await update.message.reply_text(
            f"❌ Nilai sell terlalu kecil.\n"
            f"Fee minimal: Rp {MIN_SELL_FEE_RP:,}"
        )
        return

    # =========================
    # SIMPAN DATA (TIDAK MERUBAH SISTEM)
    # =========================
    context.user_data["amount_token"] = amount_token
    context.user_data["gross_rp"] = gross_rp
    context.user_data["fee_rp"] = fee_rp
    context.user_data["net_rp"] = net_rp
    context.user_data["state"] = SELL_TX

    await update.message.reply_text(
        f"""
📤 *KIRIM TOKEN*

Token        : {token}
Jumlah       : {amount_token}
Estimasi Rp  : Rp {gross_rp:,}
Fee admin    : Rp {fee_rp:,}
Diterima     : Rp {net_rp:,}

Silakan transfer token ke wallet BOT:
`{BOT_WALLET}`

Setelah transfer berhasil, kirim *TX HASH* di sini.
""",
        parse_mode="Markdown"
    )

# =========================
# PROCESS TX & ADD BALANCE
# =========================
async def sell_tx(update, context):
    if context.user_data.get("state") != SELL_TX:
        return

    tx_hash = update.message.text.strip()
    uid = str(update.effective_user.id)

    token = context.user_data["token"]
    network = context.user_data["network"]
    sender_wallet = context.user_data["sender_wallet"]
    expected_amount = context.user_data.get("amount_token")

    # =========================
    # TOKEN DATA
    # =========================
    try:
        token_data = TOKEN_CONTRACTS[token][network]
    except KeyError:
        await update.message.reply_text("❌ Data token / network tidak ditemukan")
        context.user_data.clear()
        return

    db = load_db()
    db.setdefault("_used_tx", {})

    if tx_hash in db["_used_tx"]:
        await update.message.reply_text("❌ TX ini sudah pernah digunakan")
        context.user_data.clear()
        return

    try:
        w3 = get_w3(network)
        decimals = token_data["decimals"]

        # =========================
        # NATIVE COIN (ETH / BNB)
        # =========================
        if token_data["address"] is None:
            tx = w3.eth.get_transaction(tx_hash)

            if not tx:
                raise Exception("TX tidak ditemukan")

            if not tx.get("to") or tx["to"].lower() != BOT_WALLET.lower():
                raise Exception("TX bukan ke wallet bot")

            if tx["from"].lower() != sender_wallet.lower():
                raise Exception("Pengirim TX tidak sesuai")

            amount_token = float(w3.from_wei(tx["value"], "ether"))

        # =========================
        # ERC20 TOKEN
        # =========================
        else:
            amount_token = float(get_token_amount_from_tx(
                tx_hash=tx_hash,
                token_address=token_data["address"],
                bot_wallet=BOT_WALLET,
                sender_wallet=sender_wallet,
                decimals=decimals,
                w3=w3
            ))

        # =========================
        # SAFE COMPARISON (WEI)
        # =========================
        expected_wei = int(expected_amount * (10 ** decimals))
        actual_wei = int(amount_token * (10 ** decimals))

        # toleransi 0.5% (anti float & rounding)
        tolerance = max(1, expected_wei // 200)

        if actual_wei + tolerance < expected_wei:
            raise Exception(
                f"Jumlah token di TX ({amount_token}) kurang dari input sell ({expected_amount})"
            )

    except Exception as e:
        await update.message.reply_text(
            f"❌ TX tidak valid atau tidak sesuai\n{str(e)}"
        )
        context.user_data.clear()
        return

    # =========================
    # HITUNG NILAI RP (GROSS)
    # =========================
    try:
        rates = get_realtime_price()
        rp_value = int(amount_token * rates.get(token, 0))
    except Exception:
        rp_value = 0

    if rp_value <= 0:
        await update.message.reply_text("❌ Harga token tidak tersedia")
        context.user_data.clear()
        return

    # =========================
    # FEE SELL
    # =========================
    fee_rp = int(context.user_data.get("fee_rp", MIN_SELL_FEE_RP))
    net_rp = rp_value - fee_rp

    if net_rp <= 0:
        await update.message.reply_text("❌ Nilai sell habis oleh fee admin")
        context.user_data.clear()
        return

  # =========================
    # UPDATE USER BALANCE
    # =========================
    db.setdefault("users", {})
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0, "wallet": None}

    saldo_sebelum = int(db["users"][uid].get("balance", 0))
    saldo_sesudah = saldo_sebelum + net_rp
    db["users"][uid]["balance"] = saldo_sesudah

    # =========================
    # LOCK TX HASH (FINAL)
    # =========================
    db["_used_tx"][tx_hash] = {
        "uid": uid,
        "token": token,
        "network": network,
        "amount_token": amount_token,
        "gross": rp_value,
        "fee": fee_rp,
        "net": net_rp,
        "time": datetime.now().isoformat()
    }

    save_db(db)
    context.user_data.clear()

    # =========================
    # OUTPUT USER
    # =========================
    await update.message.reply_text(
        "✅ *SELL BERHASIL (FULL VERIFIED)*\n\n"
        f"Pengirim     : `{sender_wallet}`\n"
        f"Token        : {token}\n"
        f"Jumlah token : {amount_token:.6f}\n"
        f"Hasil jual   : Rp {rp_value:,}\n"
        f"Fee admin    : Rp {fee_rp:,}\n"
        f"Diterima     : Rp {net_rp:,}\n\n"
        f"Saldo sebelum: Rp {saldo_sebelum:,}\n"
        f"Saldo sekarang: Rp {saldo_sesudah:,}\n\n"
        f"TX HASH:\n`{tx_hash}`",
        parse_mode="Markdown"
    )

    # =========================
    # CHANNEL TRANSPARANSI
    # =========================
    await context.bot.send_message(
        TRANSACTION_CHANNEL_ID,
        "💸 *SELL TRANSACTION*\n"
        f"User ID : `{uid}`\n"
        f"Token   : {token}\n"
        f"Jumlah  : {amount_token:.6f}\n"
        f"Gross   : Rp {rp_value:,}\n"
        f"Fee     : Rp {fee_rp:,}\n"
        f"Net     : Rp {net_rp:,}\n"
        f"Wallet  : `{sender_wallet}`\n"
        f"TX HASH : `{tx_hash}`\n"
        f"Waktu   : {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}",
        parse_mode="Markdown"
    )
