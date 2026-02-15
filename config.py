import os
from dotenv import load_dotenv
import requests

load_dotenv()


# =========================
# BOT CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = list(
    map(
        int,
        filter(
            None,
            os.getenv("ADMIN_ID", "").split(",")
        )
    )
)

TRANSACTION_CHANNEL_ID = int(                                                                                                                               os.getenv("TRANSACTION_CHANNEL_ID", "-1003747216192")
)


# =========================
# DATABASE
# =========================
DB_FILE = "db.json"

# =========================
# WALLET / BLOCKCHAIN
# =========================
BOT_PRIVATE_KEY = os.getenv("BOT_PRIVATE_KEY")
BOT_WALLET = os.getenv("BOT_WALLET")
BSC_RPC = os.getenv("BSC_RPC")
ARB_RPC = os.getenv("ARB_RPC")

# =========================
# RPC BY NETWORK
# =========================
RPC_BY_NETWORK = {
    "BEP20": BSC_RPC,
    "ARB": os.getenv("ARB_RPC")  # Arbitrum Sepolia
}


# =========================
# BACKWARD COMPATIBILITY
# =========================
RPC_ARB = ARB_RPC


# =========================
# TOPUP (FIAT)
# =========================
PAYMENT_METHODS = {
    "DANA": "0812xxxx",
    "OVO": "0813xxxx",
    "GOPAY": "0814xxxx",
    "BCA": "1234567890",
    "BRI": "63727277",
    "MANDIRI": "637373737"
}

# =========================
# CRYPTO CONFIG
# =========================
CRYPTO_LIST = {
    "USDT": ["BEP20"],
    "ETH": ["ARB"]
}

TOKEN_CONTRACTS = {
    "USDT": {
        "BEP20": {
            "address": "0x7193c21Ca1960b92FdCc92CFb918F337C7bd165e",
            "decimals": 18
        }
    },
    "ETH": {
        "ARB": {  # jaringan Arbitrum Testnet
            "address": None,  # native coin, tidak punya contract
            "decimals": 18
        }
    }
}


# =========================
# PRICE REALTIME
# =========================

RATE_RP = {
    "USDT": 16000
}

# mapping symbol bot → Coingecko ID
COINGECKO_IDS = {
    "USDT": "tether",
    "ETH": "ethereum",

    # bisa ditambahkan token lain: "BTC": "bitcoin", "ETH": "ethereum"
}

def get_realtime_price(symbols=None):
    """
    Ambil harga token dari Coingecko dalam IDR.
    symbols: list token atau single token (default None → semua token di COINGECKO_IDS)
    Return: dict {symbol: price_idr} atau float kalau single symbol
    """
    if symbols is None:
        symbols = list(COINGECKO_IDS.keys())

    single = False
    if isinstance(symbols, str):
        symbols = [symbols]
        single = True

    result = {}
    try:
        ids = [COINGECKO_IDS.get(s, s.lower()) for s in symbols]
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": ",".join(ids), "vs_currencies": "idr"}
        res = requests.get(url, params=params, timeout=5)
        data = res.json()

        for s in symbols:
            cg_id = COINGECKO_IDS.get(s, s.lower())
            price = data.get(cg_id, {}).get("idr")
            if price is None:
                price = RATE_RP.get(s, 0)
            result[s] = float(price)

        return result[symbols[0]] if single else result

    except Exception as e:
        print("⚠️ Error fetch price Coingecko:", e)
        # fallback
        return RATE_RP.get(symbols[0], 0) if single else {s: RATE_RP.get(s, 0) for s in symbols}

  # =========================
# FEATURE SWITCH (admin toggle)
# =========================
FEATURES_ENABLED = {
    "buy": True,   # True = aktif, False = mati
    "sell": True
}

# =========================
# WITHDRAW METHODS
# =========================
WITHDRAW_METHODS = [
    "OVO",
    "DANA",
    "GOPAY",
    "BCA",
    "BRI",
    "MANDIRI"
]

MIN_BUY_RP = 15000
BUY_FEE_PERCENT = 2.0   # contoh: 2%
BUY_FEE_MIN = 5000      # ⬅️ FEE MINIMAL WAJIB Rp 5.000
MIN_SELL_FEE = 5000
MIN_TOPUP_RP = 15000
MIN_WITHDRAW = 15000
