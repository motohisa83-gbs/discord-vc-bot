import os
import asyncio
import discord
from discord.ext import commands, tasks

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ▼ 環境に応じて変更
TARGET_VC_CHANNEL_ID = 1352188801023479863
NOTIFY_TEXT_CHANNEL_ID = 1359151599238381852
NOTIFY_ROLE_ID = 1356581455337099425

pending_alerts = {}
active_vc_timer = {}

@bot.event
async def on_ready():
    print(f"{bot.user} has connected!")
    periodic_vc_summary.start()

@bot.event
async def on_voice_state_update(member, before, after):
    text_channel = member.guild.get_channel(NOTIFY_TEXT_CHANNEL_ID)
    role = member.guild.get_role(NOTIFY_ROLE_ID)

    # VC参加
    if after.channel and after.channel.id == TARGET_VC_CHANNEL_ID and (before.channel is None or before.channel.id != TARGET_VC_CHANNEL_ID):
        vc = after.channel
        count = len(vc.members)

        if text_channel:
            if count == 1:
                await text_channel.send(f"🎉 {member.display_name}がラウンジにきたぞー！！！You go ,We Go！！")
                if vc.id not in pending_alerts:
                    task = asyncio.create_task(alert_if_alone(vc, text_channel, role))
                    pending_alerts[vc.id] = task
            elif count == 2:
                await text_channel.send(f"🎧 2人目参加！{member.display_name}が合流！おしゃべりスタート？ {role.mention}")
                if vc.id in pending_alerts:
                    pending_alerts[vc.id].cancel()
                    del pending_alerts[vc.id]
                active_vc_timer[vc.id] = discord.utils.utcnow()
            else:
                await text_channel.send(f"🔥 {member.display_name}さんも参戦！VCがにぎやかになってきたよ！")

    # VC退出
    elif before.channel and before.channel.id == TARGET_VC_CHANNEL_ID and (after.channel is None or after.channel.id != TARGET_VC_CHANNEL_ID):
        vc = before.channel
        count = len(vc.members)

        if text_channel:
            await text_channel.send(f"🚪 {member.display_name} さんが退出しました。現在VC参加者: {count}人")
            if count == 1:
                # 1人だけになったら再度タイマー開始
                if vc.id not in pending_alerts:
                    task = asyncio.create_task(alert_if_alone(vc, text_channel, role))
                    pending_alerts[vc.id] = task
            elif count == 0:
                if vc.id in pending_alerts:
                    pending_alerts[vc.id].cancel()
                    del pending_alerts[vc.id]
                if vc.id in active_vc_timer:
                    del active_vc_timer[vc.id]

# 延期通知 (5分間一人)
async def alert_if_alone(vc_channel, text_channel, role):
    try:
        await asyncio.sleep(300)
        if len(vc_channel.members) == 1:
            await text_channel.send(f"🏋️{vc_channel.members[0].display_name}がラウンジで待ってるよ。{role.mention} みんな集まれ！きみが行くなら俺も行く!!")
    except asyncio.CancelledError:
        pass

# 定期通知 (10分ごと)
@tasks.loop(minutes=10)
async def periodic_vc_summary():
    for guild in bot.guilds:
        vc = guild.get_channel(TARGET_VC_CHANNEL_ID)
        text_channel = guild.get_channel(NOTIFY_TEXT_CHANNEL_ID)
        role = guild.get_role(NOTIFY_ROLE_ID)
        if vc and text_channel and len(vc.members) >= 2:
            names = ", ".join([m.display_name for m in vc.members])
            await text_channel.send(f"👀 現在のVC参加者：{len(vc.members)}名（{names}） {role.mention}")

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
