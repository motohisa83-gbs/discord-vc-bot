import os
import asyncio
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ▼ 以下をあなたのDiscordの実環境に合わせて変更してください ▼
TARGET_VC_CHANNEL_ID = 1352188801023479863        # 監視したいVCチャンネルのID
NOTIFY_TEXT_CHANNEL_ID = 1359151599238381852     # 通知を送るテキストチャンネルのID
NOTIFY_ROLE_ID = 1356581455337099425             # メンションしたいロールID
DELAY_SECONDS = 300  # 5分（秒で指定）

# ▼ この辞書で、遅延通知がすでにスケジュールされてるかを記録します
pending_alerts = {}

@bot.event
async def on_ready():
    print(f"{bot.user} has connected!")

@bot.event
async def on_voice_state_update(member, before, after):
    text_channel = member.guild.get_channel(NOTIFY_TEXT_CHANNEL_ID)
    role = member.guild.get_role(NOTIFY_ROLE_ID)

    # VC参加時（対象VCに入ったとき）
    if after.channel and after.channel.id == TARGET_VC_CHANNEL_ID and (before.channel is None or before.channel.id != TARGET_VC_CHANNEL_ID):
        vc = after.channel
        count = len(vc.members)

        # 通知
        if text_channel:
            if count == 1:
                await text_channel.send(f"🎶 {member.display_name} さんが VC に入りました！誰か一緒にどう？")

                # 1人だけだった場合、遅延通知をスケジュール
                if vc.id not in pending_alerts:
                    task = asyncio.create_task(alert_if_alone(vc, text_channel, role))
                    pending_alerts[vc.id] = task

            elif count == 2:
                names = [m.display_name for m in vc.members]
                await text_channel.send(f"🎉 {names[0]} さんと {names[1]} さんが集まりました！雑談スタート！？")
                # 2人以上になったので遅延通知をキャンセル（あれば）
                if vc.id in pending_alerts:
                    pending_alerts[vc.id].cancel()
                    del pending_alerts[vc.id]
            else:
                await text_channel.send(f"🗣️ {vc.name} に現在 {count}人が参加中！にぎやか〜")

    # VC退出時
    elif before.channel and before.channel.id == TARGET_VC_CHANNEL_ID and (after.channel is None or after.channel.id != TARGET_VC_CHANNEL_ID):
        vc = before.channel
        count = len(vc.members)

        if text_channel:
            if count == 0:
                await text_channel.send(f"👋 {member.display_name} さんが退出しました。VCは今誰もいません〜")
                # 全員いなくなったので遅延通知をキャンセル
                if vc.id in pending_alerts:
                    pending_alerts[vc.id].cancel()
                    del pending_alerts[vc.id]
            else:
                await text_channel.send(f"🚶‍♂️ {member.display_name} さんが退出しました。今は {count}人が残っています。")

# 🔁 遅延タスク：1人だけで時間が経ったら通知
async def alert_if_alone(vc_channel, text_channel, role):
    try:
        await asyncio.sleep(DELAY_SECONDS)
        # 再確認：まだ1人なら通知
        if len(vc_channel.members) == 1:
            await text_channel.send(f"⌛ {vc_channel.members[0].display_name} さんが5分間ひとりで待ってます！{role.mention}、よければ参加しませんか？")
    except asyncio.CancelledError:
        # 他の人が入ってキャンセルされた場合
        pass


bot.run(os.getenv("DISCORD_BOT_TOKEN"))

