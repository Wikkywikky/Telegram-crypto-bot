from telegram.ext import ApplicationBuilder
from config import BOT_TOKEN
from handlers import register
from database import load_db, save_db

def main():
    # pastikan database siap saat bot start
    db = load_db()
    save_db(db)

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    register(app)

    print("🤖 Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
