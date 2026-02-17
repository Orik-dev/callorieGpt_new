# app/tasks/broadcast.py
import logging
import asyncio
from app.db.mysql import mysql
from app.bot.bot import bot
logger = logging.getLogger(__name__)
from arq.connections import ArqRedis

REDIS_KEY_ADMIN = "broadcast:admin_id"

async def send_broadcast(ctx, data: dict):
    redis: ArqRedis = ctx["redis"]

    users = await mysql.fetchall("SELECT tg_id FROM users_tbl")
    total = len(users)
    sent = 0
    failed = 0

    logger.info(f"[Broadcast] Начинаем рассылку для {total} пользователей.")

    for user in users:
        user_id = user["tg_id"]
        try:
            if data.get("photo_id"):
                await bot.send_photo(
                    user_id, 
                    data["photo_id"], 
                    caption=data.get("text", ""),
                    parse_mode="HTML"  # ← ДОБАВЛЕНО
                )
            elif data.get("animation_id"):
                await bot.send_animation(
                    user_id, 
                    data["animation_id"], 
                    caption=data.get("text", ""),
                    parse_mode="HTML"  # ← ДОБАВЛЕНО
                )
            elif data.get("video_id"):
                await bot.send_video(
                    user_id, 
                    data["video_id"], 
                    caption=data.get("text", ""),
                    parse_mode="HTML"  # ← ДОБАВЛЕНО
                )
            elif data.get("text"):
                await bot.send_message(
                    user_id, 
                    data["text"],
                    parse_mode="HTML"  # ← ДОБАВЛЕНО
                )
            else:
                continue

            sent += 1

        except Exception as e:
            logger.warning(f"[Broadcast] Ошибка отправки {user_id}: {e}")
            failed += 1

        await asyncio.sleep(0.1)

    admin_id = await redis.get(REDIS_KEY_ADMIN)
    if admin_id:
        try:
            await bot.send_message(
                int(admin_id), 
                f"📬 Рассылка завершена.\n✅ Успешно: {sent}\n❌ Ошибок: {failed}"
            )
        except Exception as e:
            logger.warning(f"[Broadcast] Не удалось отправить отчёт администратору: {e}")

    logger.info(f"[Broadcast] Рассылка завершена: {sent} отправлено, {failed} ошибок.")