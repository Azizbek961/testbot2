import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# Logging sozlamalari
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot tokenini shu yerga yozing
BOT_TOKEN = "7899934515:AAHyYgDx12BvpXkzKOAPIEjpU3WLv8iq9dk"

# Database fayli nomi
DB_FILE = "tests.db"

# Conversation holatlari
(
    TEST_NAME,
    TEST_QUESTIONS,
    TEST_OPTIONS,
    TEST_KEY,
    USER_TEST_ID,
    USER_ANSWERS,
) = range(6)

# Admin ID larini ro'yxati
ADMIN_IDS = [1621102297, 1869189785]

# --------------------- Database yordamchi funksiyalari ---------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS tests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  admin_id INTEGER,
                  name TEXT,
                  num_questions INTEGER,
                  num_options INTEGER,
                  answer_key TEXT,
                  created_at TIMESTAMP)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS results
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  test_id INTEGER,
                  user_id INTEGER,
                  username TEXT,
                  full_name TEXT,
                  answers TEXT,
                  correct_count INTEGER,
                  percentage REAL,
                  created_at TIMESTAMP,
                  FOREIGN KEY(test_id) REFERENCES tests(id))"""
    )
    conn.commit()
    conn.close()

def create_test(admin_id: int, name: str, num_questions: int, num_options: int, answer_key: str) -> int:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now()
    c.execute(
        "INSERT INTO tests (admin_id, name, num_questions, num_options, answer_key, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (admin_id, name, num_questions, num_options, answer_key, now),
    )
    test_id = c.lastrowid
    conn.commit()
    conn.close()
    return test_id

def get_test(test_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM tests WHERE id = ?", (test_id,))
    row = c.fetchone()
    conn.close()
    if row:
        columns = [desc[0] for desc in c.description]
        return dict(zip(columns, row))
    return None

def save_result(test_id: int, user_id: int, username: str, full_name: str, answers: str, correct_count: int, percentage: float):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now()
    c.execute(
        "INSERT INTO results (test_id, user_id, username, full_name, answers, correct_count, percentage, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (test_id, user_id, username, full_name, answers, correct_count, percentage, now),
    )
    conn.commit()
    conn.close()

def get_results_for_test(test_id: int) -> List[Dict]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT * FROM results WHERE test_id = ? ORDER BY created_at DESC",
        (test_id,),
    )
    rows = c.fetchall()
    conn.close()
    if rows:
        columns = [desc[0] for desc in c.description]
        return [dict(zip(columns, row)) for row in rows]
    return []

def get_tests_by_admin(admin_id: int) -> List[Dict]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM tests WHERE admin_id = ? ORDER BY created_at DESC", (admin_id,))
    rows = c.fetchall()
    conn.close()
    if rows:
        columns = [desc[0] for desc in c.description]
        return [dict(zip(columns, row)) for row in rows]
    return []

def delete_test(test_id: int, admin_id: int) -> Tuple[bool, str]:
    """Testni va unga bog'liq barcha natijalarni o'chiradi. Qaytaradi: (muvaffaqiyat, xabar)"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Testni egasini tekshirish
        c.execute("SELECT admin_id FROM tests WHERE id = ?", (test_id,))
        row = c.fetchone()
        if not row:
            return False, "Test topilmadi."
        if row[0] != admin_id:
            return False, "Siz bu testni o'chira olmaysiz (test sizga tegishli emas)."
        # Avval natijalarni o'chirish
        c.execute("DELETE FROM results WHERE test_id = ?", (test_id,))
        # Keyin testni o'chirish
        c.execute("DELETE FROM tests WHERE id = ?", (test_id,))
        conn.commit()
        logger.info(f"Test ID {test_id} admin {admin_id} tomonidan o'chirildi.")
        return True, "Test muvaffaqiyatli o'chirildi."
    except Exception as e:
        logger.error(f"Test o'chirishda xatolik: {e}")
        if conn:
            conn.rollback()
        return False, f"Xatolik yuz berdi: {e}"
    finally:
        if conn:
            conn.close()

# --------------------- Yordamchi funksiyalar ---------------------
def parse_answer_key(text: str, num_questions: int, num_options: int) -> Optional[str]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != num_questions:
        return None
    indices = []
    allowed_letters = [chr(ord('A') + i) for i in range(num_options)]
    for part in parts:
        if len(part) < 2:
            return None
        num_part = ""
        letter_part = ""
        for ch in part:
            if ch.isdigit():
                num_part += ch
            elif ch.isalpha():
                letter_part += ch.upper()
            else:
                return None
        if not num_part or not letter_part or len(letter_part) != 1:
            return None
        try:
            q_num = int(num_part)
        except ValueError:
            return None
        if q_num < 1 or q_num > num_questions:
            return None
        letter = letter_part[0]
        if letter not in allowed_letters:
            return None
        indices.append(str(ord(letter) - ord('A')))
    return ",".join(indices)

def parse_user_answers(text: str, test: Dict) -> Tuple[Optional[List[int]], Optional[str]]:
    num_questions = test["num_questions"]
    num_options = test["num_options"]
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != num_questions:
        return None, f"Javoblar soni {num_questions} ta bo‘lishi kerak."
    indices = []
    allowed_letters = [chr(ord('A') + i) for i in range(num_options)]
    for i, part in enumerate(parts, start=1):
        if len(part) < 2:
            return None, f"{i}-javob noto‘g‘ri formatda."
        num_part = ""
        letter_part = ""
        for ch in part:
            if ch.isdigit():
                num_part += ch
            elif ch.isalpha():
                letter_part += ch.upper()
            else:
                return None, f"{i}-javob noto‘g‘ri belgi: {ch}"
        if not num_part or not letter_part or len(letter_part) != 1:
            return None, f"{i}-javob raqam va harfdan iborat bo‘lishi kerak."
        try:
            q_num = int(num_part)
        except ValueError:
            return None, f"{i}-javob raqami noto‘g‘ri."
        if q_num != i:
            return None, f"{i}-javob raqami {i} bo‘lishi kerak, siz {q_num} yozdingiz."
        letter = letter_part[0]
        if letter not in allowed_letters:
            return None, f"{i}-javob uchun harf {', '.join(allowed_letters)} dan bo‘lishi kerak."
        indices.append(ord(letter) - ord('A'))
    return indices, None

def compare_answers(user_indices: List[int], key_indices: List[int]) -> Tuple[int, float]:
    correct = 0
    total = len(key_indices)
    for u, k in zip(user_indices, key_indices):
        if u == k:
            correct += 1
    percentage = (correct / total) * 100 if total else 0
    return correct, percentage

def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS

# --------------------- Bot handlerlari ---------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keyboard = []
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("➕ Test yaratish", callback_data="create_test")])
        keyboard.append([InlineKeyboardButton("📋 Mening testlarim", callback_data="my_tests")])
    keyboard.append([InlineKeyboardButton("✅ Testni tekshirish", callback_data="take_test")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Assalomu alaykum! Botimizga xush kelibsiz.\nQuyidagi tugmalardan birini tanlang:",
        reply_markup=reply_markup,
    )

# --------------------- My tests handler (with delete buttons) ---------------------
async def my_tests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return
    tests = get_tests_by_admin(query.from_user.id)
    if not tests:
        await query.edit_message_text("Siz hali test yaratmagansiz.")
        return

    text = "Sizning testlaringiz (o'chirish uchun tugmani bosing):\n\n"
    keyboard = []
    for t in tests:
        text += f"🆔 {t['id']} - {t['name']} ({t['num_questions']} ta savol)\n"
        keyboard.append([InlineKeyboardButton(f"❌ {t['id']} - {t['name']} ni o'chirish", callback_data=f"delete_test_{t['id']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

# --------------------- Delete test (direct) ---------------------
async def delete_test_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Testni to'g'ridan-to'g'ri o'chiradi (tasdiq so'ramaydi)."""
    query = update.callback_query
    await query.answer()
    data = query.data
    test_id = int(data.split("_")[2])
    admin_id = query.from_user.id

    success, message = delete_test(test_id, admin_id)
    if success:
        text = f"✅ Test ID {test_id} muvaffaqiyatli o'chirildi."
    else:
        text = f"❌ Xatolik: {message}"

    # O'chirilgandan so'ng, testlar ro'yxatiga qaytish tugmasi
    keyboard = [[InlineKeyboardButton("📋 Testlar ro'yxatiga qaytish", callback_data="my_tests")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

# --------------------- Test yaratish conversation ---------------------
async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return ConversationHandler.END
    await query.edit_message_text("Test nomini kiriting:")
    return TEST_NAME

async def test_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["test_name"] = update.message.text
    await update.message.reply_text("Testdagi savollar sonini kiriting (masalan: 10):")
    return TEST_QUESTIONS

async def test_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        num = int(update.message.text)
        if num <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Iltimos, musbat butun son kiriting.")
        return TEST_QUESTIONS
    context.user_data["num_questions"] = num
    await update.message.reply_text("Har bir savol uchun variantlar sonini kiriting (masalan: 4):")
    return TEST_OPTIONS

async def test_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        num = int(update.message.text)
        if num < 2 or num > 9:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Iltimos, 2 dan 9 gacha bo‘lgan son kiriting.")
        return TEST_OPTIONS
    context.user_data["num_options"] = num
    allowed_letters = [chr(ord('A') + i) for i in range(num)]
    await update.message.reply_text(
        f"Endi test kalitini kiriting. Format: har bir savol uchun raqam va harf, vergul bilan ajrating.\n"
        f"Misol: 1a,2b,3c,... (harflar {', '.join(allowed_letters)} dan bo‘lishi kerak)\n"
        f"Savollar soni: {context.user_data['num_questions']}"
    )
    return TEST_KEY

async def test_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    num_questions = context.user_data["num_questions"]
    num_options = context.user_data["num_options"]

    key_indices_str = parse_answer_key(text, num_questions, num_options)
    if key_indices_str is None:
        allowed_letters = [chr(ord('A') + i) for i in range(num_options)]
        await update.message.reply_text(
            f"Kalit noto‘g‘ri formatda yoki savollar soni mos kelmadi.\n"
            f"Qaytadan kiriting. Harflar {', '.join(allowed_letters)} dan bo‘lishi kerak.\n"
            f"Masalan: {','.join([f'{i+1}{chr(65+i%num_options)}' for i in range(min(5, num_questions))])}..."
        )
        return TEST_KEY

    test_name = context.user_data["test_name"]
    admin_id = update.effective_user.id

    test_id = create_test(admin_id, test_name, num_questions, num_options, key_indices_str)

    await update.message.reply_text(
        f"✅ Test muvaffaqiyatli yaratildi!\n\n"
        f"🆔 Test ID: {test_id}\n"
        f"📝 Nomi: {test_name}\n"
        f"📊 Savollar: {num_questions}\n"
        f"🔤 Variantlar: {num_options}\n"
        f"Kalit: {text}\n\n"
        f"Foydalanuvchilar natijalarini ko‘rish uchun: /results {test_id}"
    )
    return ConversationHandler.END

# --------------------- Test topshirish conversation ---------------------
async def take_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Iltimos, test ID sini kiriting:")
    return USER_TEST_ID

async def user_test_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        test_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Test ID raqam bo‘lishi kerak. Qaytadan kiriting:")
        return USER_TEST_ID

    test = get_test(test_id)
    if not test:
        await update.message.reply_text("Bunday ID lik test topilmadi. Qaytadan kiriting:")
        return USER_TEST_ID

    context.user_data["test"] = test
    num_questions = test["num_questions"]
    num_options = test["num_options"]
    allowed_letters = [chr(ord('A') + i) for i in range(num_options)]
    await update.message.reply_text(
        f"Test: {test['name']}\n"
        f"Savollar soni: {num_questions}\n"
        f"Variantlar: {', '.join(allowed_letters)}\n\n"
        f"Endi o‘z javoblaringizni kiriting. Format: har bir savol uchun raqam va harf, vergul bilan ajrating.\n"
        f"Misol: 1a,2b,3c,..."
    )
    return USER_ANSWERS

async def user_answers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    test = context.user_data["test"]
    num_questions = test["num_questions"]
    num_options = test["num_options"]

    user_indices, error = parse_user_answers(text, test)
    if error:
        allowed_letters = [chr(ord('A') + i) for i in range(num_options)]
        await update.message.reply_text(
            f"{error}\n"
            f"Qaytadan kiriting. Harflar {', '.join(allowed_letters)} dan bo‘lishi kerak.\n"
            f"Masalan: {','.join([f'{i+1}{chr(65+i%num_options)}' for i in range(min(5, num_questions))])}..."
        )
        return USER_ANSWERS

    key_indices = [int(x) for x in test["answer_key"].split(",")]
    correct, percentage = compare_answers(user_indices, key_indices)

    user = update.effective_user
    save_result(
        test["id"],
        user.id,
        user.username,
        user.full_name,
        text,
        correct,
        percentage,
    )

    await update.message.reply_text(
        f"✅ Natijalar:\n"
        f"To‘g‘ri javoblar: {correct} / {num_questions}\n"
        f"Foiz: {percentage:.1f}%"
    )
    return ConversationHandler.END

# --------------------- Natijalarni ko‘rish komandasi ---------------------
async def results_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return
    if not context.args:
        await update.message.reply_text("Iltimos, test ID sini kiriting: /results <test_id>")
        return
    try:
        test_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Test ID raqam bo‘lishi kerak.")
        return
    test = get_test(test_id)
    if not test:
        await update.message.reply_text("Bunday test mavjud emas.")
        return
    if ADMIN_IDS and test["admin_id"] != user_id:
        await update.message.reply_text("Siz bu testni ko‘rish huquqiga ega emassiz.")
        return
    results = get_results_for_test(test_id)
    if not results:
        await update.message.reply_text(f"Test ID {test_id} uchun hali natijalar mavjud emas.")
        return
    text = f"📊 Test: {test['name']} (ID: {test_id})\n"
    text += f"Jami ishlaganlar: {len(results)}\n\n"
    for r in results:
        user_info = r['full_name'] or r['username'] or f"User {r['user_id']}"
        text += f"👤 {user_info}: {r['correct_count']}/{test['num_questions']} ({r['percentage']:.1f}%)\n"
        text += f"   Javoblar: {r['answers']}\n"
        text += f"   Vaqt: {r['created_at'][:19]}\n\n"
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000])
    else:
        await update.message.reply_text(text)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Amal bekor qilindi.")
    return ConversationHandler.END

# --------------------- Asosiy funksiya ---------------------
def main() -> None:
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    # My tests handler
    application.add_handler(CallbackQueryHandler(my_tests_callback, pattern="^my_tests$"))

    # Delete test handler (direct)
    application.add_handler(CallbackQueryHandler(delete_test_callback, pattern="^delete_test_"))

    # Create test conversation
    create_test_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_test_start, pattern="^create_test$")],
        states={
            TEST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, test_name)],
            TEST_QUESTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, test_questions)],
            TEST_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, test_options)],
            TEST_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, test_key)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(create_test_conv)

    # Take test conversation
    take_test_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(take_test_start, pattern="^take_test$")],
        states={
            USER_TEST_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_test_id)],
            USER_ANSWERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_answers)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(take_test_conv)

    # Other handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("results", results_command))

    application.run_polling()

if __name__ == "__main__":
    main()