from aiohttp import web
import asyncio

routes = web.RouteTableDef()

@routes.post("/api/order")
async def create_order(request):
    data = await request.json()
    perfume_name = data.get("name")
    user_contact = data.get("contact")
    if not perfume_name or not user_contact:
        return web.json_response({"error": "Invalid data"}, status=400)

    # Отправляем сообщение продавцу в Telegram
    await bot.send_message(
        chat_id="@Kolychij14",  # или конкретный ID
        text=f"Новый заказ!\n💎 Парфюм: {perfume_name}\n📱 Контакт: {user_contact}"
    )
    return web.json_response({"status": "ok"})

async def start_web_app():
    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 3002)
    await site.start()

# В main() нужно запускать вместе с ботом
async def main():
    await bot.set_my_commands([])
    await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_app()
    )
