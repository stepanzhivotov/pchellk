import os
import json
import asyncio
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# Файл для хранения данных пользователей
USERS_FILE = "users.json"

# Загрузка пользователей
def load_users():
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

# Сохранение пользователей
def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

# Список устройств
SUPPORTED_DEVICES = {
    "iPhone 11": "iPhone12,1",
    "iPhone 11 Pro": "iPhone12,3",
    "iPhone 11 Pro Max": "iPhone12,5",
    "iPhone SE (2nd Gen)": "iPhone12,8",
    "iPhone SE (3rd Gen)": "iPhone14,4",
    "iPhone 12": "iPhone13,2",
    "iPhone 12 Mini": "iPhone13,1",
    "iPhone 12 Pro": "iPhone13,3",
    "iPhone 12 Pro Max": "iPhone13,4",
    "iPhone 13": "iPhone14,5",
    "iPhone 13 Mini": "iPhone14,4",
    "iPhone 13 Pro": "iPhone14,2",
    "iPhone 13 Pro Max": "iPhone14,3",
    "iPhone 14": "iPhone14,7",
    "iPhone 14 Plus": "iPhone14,8",
    "iPhone 14 Pro": "iPhone14,2",
    "iPhone 14 Pro Max": "iPhone14,3",
    "iPhone 15": "iPhone15,2",
    "iPhone 15 Plus": "iPhone15,3",
    "iPhone 15 Pro": "iPhone15,4",
    "iPhone 15 Pro Max": "iPhone15,5",
}

# Получение версий iOS
def get_ios_versions(device_identifier, version_type="signed"):
    url = f"https://api.ipsw.me/v4/device/{device_identifier}?type=ipsw"
    response = requests.get(url)
    data = response.json()
    
    versions = []
    for fw in data["firmwares"]:
        if version_type == "signed" and fw["signed"]:
            versions.append(fw)
        elif version_type == "unsigned" and not fw["signed"] and not fw.get("beta", False):
            versions.append(fw)
        elif version_type == "beta" and fw.get("beta", False):
            versions.append(fw)
    return versions

# Создание картинки версии
def create_version_image(version_type, version_number):
    width, height = 600, 300
    bg_colors = {"signed": (100, 200, 100), "unsigned": (200, 100, 100), "beta": (100, 100, 200)}
    text_labels = {"signed": "Актуальная версия iOS", "unsigned": "Неактуальная версия iOS", "beta": "Beta / Developer версия iOS"}

    img = Image.new("RGB", (width, height), color=bg_colors.get(version_type, (200,200,200)))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except:
        font = ImageFont.load_default()

    text = f"{text_labels.get(version_type, 'iOS версия')}\n{version_number}"
    text_w, text_h = draw.multiline_textsize(text, font=font)
    x = (width - text_w) / 2
    y = (height - text_h) / 2
    draw.multiline_text((x, y), text, fill=(255,255,255), font=font, align="center")

    bio = BytesIO()
    bio.name = 'version.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio

# Клавиатуры
def get_device_keyboard():
    keyboard = [[InlineKeyboardButton(device, callback_data=f"device|{device}")] for device in SUPPORTED_DEVICES.keys()]
    return InlineKeyboardMarkup(keyboard)

def get_version_type_keyboard(device_name):
    keyboard = [
        [InlineKeyboardButton("Актуальные версии", callback_data=f"type|signed|{device_name}")],
        [InlineKeyboardButton("Отозванные версии", callback_data=f"type|unsigned|{device_name}")],
        [InlineKeyboardButton("Beta/Developer версии", callback_data=f"type|beta|{device_name}")],
        [InlineKeyboardButton("Выбрать другое устройство", callback_data="back|devices")]
    ]
    return InlineKeyboardMarkup(keyboard)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Выбери устройство:", reply_markup=get_device_keyboard())

# Обработка кнопок
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    users = load_users()

    if data.startswith("device|"):
        device_name = data.split("|")[1]
        user_id = str(query.from_user.id)
        users[user_id] = {"device": device_name, "last_notified": ""}
        save_users(users)
        await query.edit_message_text(f"Вы выбрали {device_name}. Выберите тип версий iOS:", reply_markup=get_version_type_keyboard(device_name))

    elif data.startswith("type|"):
        parts = data.split("|")
        version_type = parts[1]
        device_name = parts[2]
        device_identifier = SUPPORTED_DEVICES[device_name]

        versions = get_ios_versions(device_identifier, version_type)
        if versions:
            for fw in versions[:5]:
                version_number = fw["version"]
                release_date = fw.get("releasedate", "Неизвестно")
                desc = fw.get("description", "Нет описания")
                status = "Актуальная" if fw.get("signed") else "Отозванная"
                beta_flag = "Beta/Developer" if fw.get("beta", False) else "Стабильная"

                image = create_version_image(version_type, version_number)
                caption = f"Версия: {version_number}\nСтатус: {status}\nТип: {beta_flag}\nДата выхода: {release_date}\nОписание: {desc}"
                await context.bot.send_photo(chat_id=query.message.chat_id, photo=image, caption=caption)

            await query.edit_message_text(f"Показаны версии {version_type} для {device_name}.", reply_markup=get_version_type_keyboard(device_name))
        else:
            await query.edit_message_text("Для этого устройства нет версий выбранного типа.", reply_markup=get_version_type_keyboard(device_name))

    elif data == "back|devices":
        await query.edit_message_text("Выберите устройство:", reply_markup=get_device_keyboard())

# Фоновая проверка новых версий
async def check_new_versions(app):
    while True:
        users = load_users()
        for user_id, info in users.items():
            device_name = info["device"]
            last_notified = info.get("last_notified", "")
            device_identifier = SUPPORTED_DEVICES[device_name]

            versions = get_ios_versions(device_identifier, "signed")
            if versions:
                latest_version = versions[0]["version"]
                if latest_version != last_notified:
                    users[user_id]["last_notified"] = latest_version
                    save_users(users)

                    release_date = versions[0].get("releasedate", "Неизвестно")
                    desc = versions[0].get("description", "Нет описания")

                    image = create_version_image("signed", latest_version)
                    caption = f"Новая актуальная версия для {device_name}!\nВерсия: {latest_version}\nСтатус: Актуальная\nТип: Стабильная\nДата выхода: {release_date}\nОписание: {desc}"
                    await app.bot.send_photo(chat_id=int(user_id), photo=image, caption=caption)
        await asyncio.sleep(3600)  # проверка каждый час

# Получение токена из переменной окружения
TOKEN = os.environ.get("8483656371:AAH0O3xW7CJbLw3uiAWQJssd6P4MKuEjM_0")

# Запуск бота
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_callback))

# Фоновая задача
async def main():
    asyncio.create_task(check_new_versions(app))
    await app.run_polling()

asyncio.run(main())


