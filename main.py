import discord
from discord.ext import commands

# === Настройка бота ===
intents = discord.Intents.default()
intents.voice_states = True  # Для отслеживания подключения к голосовым каналам
intents.message_content = True  # Для обработки команд

bot = commands.Bot(command_prefix="!", intents=intents)

# Импортируем настройки из config.py
from config import TOKEN, TEMP_CHANNEL_NAMES, CATEGORY_NAMES, DEFAULT_USER_LIMITS

# Хранилище комнат и их настроек
active_rooms = {}  # {channel_id: {"owner": member, "private": bool, "allowed_users": set()}


@bot.event
async def on_ready():
    print(f'Бот {bot.user} запущен!')
    for guild in bot.guilds:
        for category_type in CATEGORY_NAMES:
            category_name = CATEGORY_NAMES[category_type]
            category = discord.utils.get(guild.categories, name=category_name)
            if not category:
                category = await guild.create_category(category_name)

            temp_channel_name = TEMP_CHANNEL_NAMES[category_type]
            temp_channel = None
            for channel in category.voice_channels:
                if channel.name == temp_channel_name:
                    temp_channel = channel
                    break
            if not temp_channel:
                await guild.create_voice_channel(temp_channel_name, category=category)


@bot.event
async def on_voice_state_update(member, before, after):
    global active_rooms

    # 1. Подключение к кнопке создания
    if after.channel:
        for category_type in CATEGORY_NAMES:
            category_name = CATEGORY_NAMES[category_type]
            category = discord.utils.get(member.guild.categories, name=category_name)
            if after.channel and after.channel.category == category:
                if after.channel.name == TEMP_CHANNEL_NAMES[category_type]:
                    overwrites = {
                        member.guild.default_role: discord.PermissionOverwrite(connect=False),
                        member: discord.PermissionOverwrite(connect=True, manage_channels=True)
                    }

                    user_limit = DEFAULT_USER_LIMITS[category_type]
                    new_channel = await member.guild.create_voice_channel(
                        name=f"Комната {member.display_name}",
                        category=category,
                        user_limit=user_limit,
                        overwrites=overwrites
                    )

                    await member.move_to(new_channel)

                    active_rooms[new_channel.id] = {
                        "owner": member,
                        "private": False,
                        "allowed_users": set()
                    }

    # 2. Удаление пустого канала
    if before.channel:
        for category_type in CATEGORY_NAMES:
            category_name = CATEGORY_NAMES[category_type]
            category = discord.utils.get(member.guild.categories, name=category_name)
            if before.channel.category == category and before.channel.name != TEMP_CHANNEL_NAMES[category_type]:
                if len(before.channel.members) == 0:
                    await before.channel.delete()
                    if before.channel.id in active_rooms:
                        del active_rooms[before.channel.id]


# ==== Команды управления ботом ====

@bot.command(name="settempchannel")
async def set_temp_channel(ctx, *, args: str):
    """Изменяет название 'кнопочного' канала"""
    try:
        category_type, new_name = args.split(" ", 1)
        if category_type.lower() not in TEMP_CHANNEL_NAMES:
            return await ctx.send("Неверный тип категории.")
        
        TEMP_CHANNEL_NAMES[category_type.lower()] = new_name
        await ctx.send(f"Название кнопочного канала для `{category_type}` изменено на: `{new_name}`")
    except ValueError:
        await ctx.send("Правильное использование: `!settempchannel <тип> <название>`")


@bot.command(name="setcategory")
async def set_category(ctx, *, args: str):
    """Изменяет название категории временных комнат"""
    try:
        category_type, new_name = args.split(" ", 1)
        if category_type.lower() not in CATEGORY_NAMES:
            return await ctx.send("Неверный тип категории.")
        
        CATEGORY_NAMES[category_type.lower()] = new_name
        await ctx.send(f"Название категории для `{category_type}` изменено на: `{new_name}`")
    except ValueError:
        await ctx.send("Правильное использование: `!setcategory <тип> <название>`")


@bot.command(name="setdefaultlimit")
async def set_default_limit(ctx, *, args: str):
    """Изменяет лимит участников по умолчанию"""
    try:
        category_type, limit_str = args.split(" ", 1)
        limit = int(limit_str)
        if limit < 0 or limit > 99:
            return await ctx.send("Лимит должен быть от 0 до 99.")

        if category_type.lower() not in DEFAULT_USER_LIMITS:
            return await ctx.send("Неверный тип категории.")

        DEFAULT_USER_LIMITS[category_type.lower()] = limit
        await ctx.send(f"Лимит участников для `{category_type}` установлен: `{limit}`")
    except ValueError:
        await ctx.send("Правильное использование: `!setdefaultlimit <тип> <лимит>`")


# === Команда для проверки текущих настроек ===

@bot.command(name="settings")
async def show_settings(ctx):
    """Показывает текущие настройки бота"""
    embed = discord.Embed(title="⚙️ Настройки бота", color=discord.Color.blue())

    for category_type in CATEGORY_NAMES:
        embed.add_field(
            name=f"{category_type.capitalize()} каналы",
            value=(
                f"Кнопка: `{TEMP_CHANNEL_NAMES[category_type]}`\n"
                f"Категория: `{CATEGORY_NAMES[category_type]}`\n"
                f"Лимит участников: `{DEFAULT_USER_LIMITS[category_type]}`"
            ),
            inline=False
        )

    await ctx.send(embed=embed)


# ==== Команды управления комнатой ====

@bot.command(name="setlimit")
async def set_limit(ctx, limit: int):
    """Устанавливает лимит участников в текущей комнате"""
    room_data = None
    for data in active_rooms.values():
        if data["owner"] == ctx.author:
            room_data = data
            break

    if not room_data:
        return await ctx.send("Вы не являетесь владельцем этой комнаты.")

    voice_channel = ctx.author.voice.channel if ctx.author.voice else None
    if not voice_channel or voice_channel.name in TEMP_CHANNEL_NAMES.values():
        return await ctx.send("Вы должны находиться в своей временной комнате.")

    await voice_channel.edit(user_limit=limit)
    await ctx.send(f"Лимит участников установлен: {limit}")


@bot.command(name="private")
async def make_private(ctx):
    """Делает комнату приватной (только по приглашениям)"""
    room_data = None
    for ch_id, data in active_rooms.items():
        if data["owner"] == ctx.author:
            room_data = data
            break

    if not room_data:
        return await ctx.send("Вы не владеете этой комнатой.")

    voice_channel = ctx.author.voice.channel
    await voice_channel.set_permissions(ctx.guild.default_role, connect=False)
    room_data["private"] = True
    await ctx.send("Комната теперь приватная.")


@bot.command(name="public")
async def make_public(ctx):
    """Делает комнату открытой (все могут подключаться)"""
    room_data = None
    for ch_id, data in active_rooms.items():
        if data["owner"] == ctx.author:
            room_data = data
            break

    if not room_data:
        return await ctx.send("Вы не владеете этой комнатой.")

    voice_channel = ctx.author.voice.channel
    await voice_channel.set_permissions(ctx.guild.default_role, connect=True)
    room_data["private"] = False
    await ctx.send("Комната теперь общедоступная.")


@bot.command(name="allow")
async def allow_user(ctx, member: discord.Member):
    """Позволяет пользователю присоединиться к приватной комнате"""
    room_data = None
    for ch_id, data in active_rooms.items():
        if data["owner"] == ctx.author:
            room_data = data
            break

    if not room_data:
        return await ctx.send("Вы не владеете этой комнатой.")

    voice_channel = ctx.author.voice.channel
    await voice_channel.set_permissions(member, connect=True)
    room_data["allowed_users"].add(member)
    await ctx.send(f"{member.display_name} теперь может присоединиться к вашей комнате.")


# ==== Запуск бота ====
bot.run(TOKEN)