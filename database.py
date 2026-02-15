import json
import os
from config import DB_FILE
from datetime import datetime

# =========================
# CORE DB
# =========================

def _default_db():
    return {
        "users": {},
        "topups": {},
        "withdraws": {},
        "orders": {},
        "maintenance": None  # ⚡ Tambahan untuk fitur maintenance
    }


def load_db():
    if not os.path.exists(DB_FILE):
        return _default_db()

    with open(DB_FILE, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return _default_db()

    # pastikan semua key default ada
    for k in _default_db():
        data.setdefault(k, None if k == "maintenance" else {})

    return data


def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)


# =========================
# USER
# =========================

def get_user(db, user_id):
    uid = str(user_id)

    if uid not in db["users"]:
        db["users"][uid] = {
            "balance": 0,
            "wallet": None
        }

    return db["users"][uid]


def add_balance(db, user_id, amount):
    get_user(db, user_id)["balance"] += amount


def deduct_balance(db, user_id, amount):
    user = get_user(db, user_id)
    if user["balance"] < amount:
        return False
    user["balance"] -= amount
    return True


# =========================
# TOPUP
# =========================

def create_topup(db, user_id, amount, method):
    tid = str(len(db["topups"]) + 1)

    db["topups"][tid] = {
        "user_id": str(user_id),
        "amount": amount,
        "method": method,
        "status": "pending"
    }

    return tid


# =========================
# WITHDRAW
# =========================

def create_withdraw(db, user_id, amount, method, target, name):
    wid = str(len(db["withdraws"]) + 1)

    db["withdraws"][wid] = {
        "user_id": str(user_id),
        "amount": amount,
        "method": method,
        "target": target,
        "name": name,
        "status": "pending"
    }

    return wid


# =========================
# ORDER / ESCROW
# =========================

def create_order(db, buyer_id, seller_id, amount):
    oid = str(len(db["orders"]) + 1)

    db["orders"][oid] = {
        "buyer_id": str(buyer_id),
        "seller_id": str(seller_id),
        "amount": amount,
        "status": "holding"
    }

    return oid


# =========================
# MAINTENANCE
# =========================

def set_maintenance(db, start_time: datetime, end_time: datetime, reason=""):
    """
    Simpan status maintenance ke DB
    start_time, end_time: datetime object
    """
    db["maintenance"] = {
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "reason": reason
    }
    save_db(db)


def get_maintenance(db):
    """
    Ambil status maintenance dari DB
    """
    return db.get("maintenance")


def clear_maintenance(db):
    """
    Hapus status maintenance
    """
    db["maintenance"] = None
    save_db(db)
