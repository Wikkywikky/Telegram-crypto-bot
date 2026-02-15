# maintenance.py
import asyncio
from database import load_db, save_db, set_maintenance, get_maintenance, clear_maintenance
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

# =========================
# ADMIN COMMAND: SET MAINTENANCE
# =========================
async def maintenance_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_IDS

    uid = str(update.effective_user.id)
    if uid not in [str(a) for a in ADMIN_IDS]:
        await update.message.reply_text("❌ Kamu bukan admin.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Gunakan format: /setmaintenance [start] [end] [reason opsional]\n"
            "Contoh: /setmaintenance 2026-02-14_10:00 2026-02-14_12:00 Upgrade sistem"
        )
        return

    try:
        start_time = datetime.strptime(context.args[0], "%Y-%m-%d_%H:%M")
        end_time = datetime.strptime(context.args[1], "%Y-%m-%d_%H:%M")
        reason = " ".join(context.args[2:]) if len(context.args) > 2 else "-"
    except ValueError:
        await update.message.reply_text("Format tanggal salah. Gunakan YYYY-MM-DD_HH:MM")
        return

    db = load_db()
    set_maintenance(db, start_time, end_time, reason)

    await update.message.reply_text(
        f"⚠️ Maintenance diaktifkan\n"
        f"Mulai: {start_time}\n"
        f"Selesai: {end_time}\n"
        f"Alasan: {reason}"
    )

    # 🔔 Notifikasi semua user langsung setelah admin set
    asyncio.create_task(_notify_users(db, context.bot,
                                      f"⚠️ Peringatan: Bot akan maintenance\nMulai: {start_time}\nSelesai: {end_time}\nAlasan: {reason}"))

    # 🔔 Task untuk notifikasi saat maintenance berjalan
    asyncio.create_task(_notify_users_running(db, start_time, end_time, reason, context.bot))

    # 🔔 Task untuk notifikasi selesai maintenance
    asyncio.create_task(_notify_after_maintenance(db, end_time, context.bot))


# =========================
# ADMIN COMMAND: STOP MAINTENANCE
# =========================
async def maintenance_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_IDS

    uid = str(update.effective_user.id)
    if uid not in [str(a) for a in ADMIN_IDS]:
        await update.message.reply_text("❌ Kamu bukan admin.")
        return

    db = load_db()
    clear_maintenance(db)
    await update.message.reply_text("✅ Maintenance dihentikan.")


# =========================
# NOTIFIKASI USER
# =========================
async def _notify_users(db, bot, message: str):
    """
    Kirim notifikasi ke semua user
    """
    users = db.get("users", {})
    for uid in users:
        try:
            await bot.send_message(int(uid), message)
        except Exception as e:
            print(f"Gagal kirim notifikasi ke {uid}: {e}")


async def _notify_users_running(db, start_time: datetime, end_time: datetime, reason: str, bot):
    """
    Tunggu sampai waktu maintenance dan notif semua user bahwa maintenance sedang berlangsung
    """
    now = datetime.now()
    wait_seconds = (start_time - now).total_seconds()
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)

    # Ambil db terbaru
    db = load_db()
    users = db.get("users", {})
    for uid in users:
        try:
            await bot.send_message(
                int(uid),
                f"⚠️ Bot sedang maintenance sekarang!\n"
                f"Waktu mulai: {start_time}\n"
                f"Waktu selesai: {end_time}\n"
                f"Alasan: {reason}\n"
                f"Sistem tidak bisa digunakan sementara."
            )
        except Exception as e:
            print(f"Gagal kirim notifikasi maintenance berjalan ke {uid}: {e}")


async def _notify_after_maintenance(db, end_time: datetime, bot):
    """
    Tunggu sampai maintenance selesai, hapus flag maintenance, notif user
    """
    now = datetime.now()
    wait_seconds = (end_time - now).total_seconds()
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)

    db = load_db()
    clear_maintenance(db)

    # Notifikasi semua user
    users = db.get("users", {})
    for uid in users:
        try:
            await bot.send_message(
                int(uid),
                "✅ Bot sudah selesai maintenance.\nFitur kembali normal."
            )
        except Exception as e:
            print(f"Gagal kirim notifikasi selesai maintenance ke {uid}: {e}")


# =========================
# CHECK MAINTENANCE
# =========================
async def check_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Cek apakah bot sedang maintenance
    Jika iya, kirim pesan ke user dan return True
    """
    db = load_db()
    m = get_maintenance(db)

    if not m:
        return False

    try:
        start_time = datetime.fromisoformat(m["start"])
        end_time = datetime.fromisoformat(m["end"])
        now = datetime.now()

        if start_time <= now <= end_time:
            reason = m.get("reason", "-")
            if update.message:
                await update.message.reply_text(
                    f"⚠️ Bot sedang maintenance\n"
                    f"Waktu: {start_time} s/d {end_time}\n"
                    f"Alasan: {reason}\n"
                    f"Silakan coba lagi nanti."
                )
            return True
    except Exception as e:
        print("Error check maintenance:", e)
        return False

    return False
