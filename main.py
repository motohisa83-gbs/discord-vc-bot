import os
import random
import asyncio
import discord
import pandas as pd
from discord.ext import commands, tasks
from discord import app_commands, Interaction
from discord.ui import View, Button
from collections import defaultdict

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ▼ VC通知用設定
TARGET_VC_CHANNEL_ID = 1352188801023479863
NOTIFY_TEXT_CHANNEL_ID = 1359151599238381852
NOTIFY_ROLE_ID = 1356581455337099425
pending_alerts = {}
active_vc_timer = {}
schedule_votes = {}  # スケジュール投票の記録用（message_id: [date_list]）

# クイズファイルの読み込み
df = pd.read_excel("mba_quiz_multiple_choice_template_fill.xlsx")

class QuizView(View):
    def __init__(self, correct_answers, explanation):
        super().__init__(timeout=60)
        self.correct = set(correct_answers.upper().replace(" ", "").split(","))
        self.explanation = explanation
        self.user_answers = set()

        for label in ["A", "B", "C", "D"]:
            self.add_item(QuizButton(label, self))

        self.add_item(SubmitButton(self))

class QuizButton(Button):
    def __init__(self, label, view):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.view_ref = view

    async def callback(self, interaction: Interaction):
        label = self.label
        if label in self.view_ref.user_answers:
            self.view_ref.user_answers.remove(label)
            await interaction.response.send_message(f"❌ {label} を選択解除しました。", ephemeral=True)
        else:
            self.view_ref.user_answers.add(label)
            await interaction.response.send_message(f"✅ {label} を選択しました。", ephemeral=True)

class SubmitButton(Button):
    def __init__(self, view):
        super().__init__(label="✅ 回答を確定", style=discord.ButtonStyle.success)
        self.view_ref = view

    async def callback(self, interaction: Interaction):
        selected = self.view_ref.user_answers
        correct = self.view_ref.correct
        if selected == correct:
            result = "🟢 正解です！お見事！"
        else:
            result = f"🔴 不正解です…\n正解は: {', '.join(correct)}"

        msg = f"{result}\n\n💡 解説: {self.view_ref.explanation}"
        for item in self.view_ref.children:
            item.disabled = True
        await interaction.response.edit_message(content=msg, view=self.view_ref)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"{bot.user} has connected!")
    periodic_vc_summary.start()

@tree.command(name="quiz", description="MBAクイズを出題します")
async def quiz_command(interaction: Interaction):
    quiz = df.sample(1).iloc[0]
    question = quiz["Question"]
    options = [quiz["OptionA"], quiz["OptionB"], quiz["OptionC"], quiz["OptionD"]]
    answer = quiz["Answer"]
    explanation = quiz["Explanation"]

    text = f"📘 **MBAクイズ**\n\n❓ {question}\n"
    labels = ["A", "B", "C", "D"]
    for i, opt in enumerate(options):
        if pd.notna(opt):
            text += f"{labels[i]}. {opt}\n"

    view = QuizView(answer, explanation)
    await interaction.response.send_message(text, view=view)

@tree.command(name="group_split", description="VC参加者を指定人数でグループ分けします")
@app_commands.describe(group_size="1グループあたりの人数")
async def group_split(interaction: Interaction, group_size: int):
    vc_channel = interaction.guild.get_channel(TARGET_VC_CHANNEL_ID)
    text_channel = interaction.guild.get_channel(NOTIFY_TEXT_CHANNEL_ID)

    if vc_channel is None or len(vc_channel.members) == 0:
        await interaction.response.send_message("VCに参加しているメンバーがいません。", ephemeral=True)
        return

    members = vc_channel.members
    random.shuffle(members)

    groups = [members[i:i + group_size] for i in range(0, len(members), group_size)]
    result_lines = []
    for idx, group in enumerate(groups, 1):
        names = ", ".join([member.display_name for member in group])
        result_lines.append(f"グループ{idx}: {names}")

    result_message = "\n".join(result_lines)
    await text_channel.send(f"🎲 **VCグループ分け結果（{group_size}人ずつ）**\n{result_message}")
    await interaction.response.send_message("グループ分け結果をVCコメント欄に投稿しました。", ephemeral=True)

@tree.command(name="schedule", description="日程調整用の投票を作成します")
@app_commands.describe(dates="カンマ区切りで日程を入力（例: 5/10, 5/11, 5/12）")
async def schedule(interaction: Interaction, dates: str):
    date_list = [d.strip() for d in dates.split(",") if d.strip()]

    if not date_list:
        await interaction.response.send_message("日程が正しく入力されていません。", ephemeral=True)
        return

    text_channel = interaction.channel
    msg_text = "📅 **日程調整 投票**\nリアクションで希望日程を選んでください！\n"
    for idx, date in enumerate(date_list, 1):
        msg_text += f"{idx}. {date}\n"

    message = await text_channel.send(msg_text)

    reactions = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i in range(len(date_list)):
        if i < len(reactions):
            await message.add_reaction(reactions[i])

    schedule_votes[message.id] = date_list
    asyncio.create_task(schedule_result_report(message, date_list, delay_hours=48))

    await interaction.response.send_message("日程調整用の投票を作成しました！", ephemeral=True)

async def schedule_result_report(message, date_list, delay_hours=48):
    await asyncio.sleep(delay_hours * 3600)
    await message.channel.fetch_message(message.id)  # 再取得
    message = await message.channel.fetch_message(message.id)

    reactions = message.reactions
    counts = defaultdict(int)
    for i, reaction in enumerate(reactions):
        users = await reaction.users().flatten()
        counts[date_list[i]] = len([u for u in users if not u.bot])

    sorted_dates = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    result_lines = [f"{date}: {count}票" for date, count in sorted_dates]

    await message.channel.send("🗳️ **日程調整 結果発表（48時間後）**\n" + "\n".join(result_lines))

@bot.event
async def on_voice_state_update(member, before, after):
    text_channel = member.guild.get_channel(NOTIFY_TEXT_CHANNEL_ID)
    role = member.guild.get_role(NOTIFY_ROLE_ID)

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

    elif before.channel and before.channel.id == TARGET_VC_CHANNEL_ID and (after.channel is None or after.channel.id != TARGET_VC_CHANNEL_ID):
        vc = before.channel
        count = len(vc.members)

        if text_channel:
            await text_channel.send(f"🚪 {member.display_name} さんが退出しました。現在VC参加者: {count}人")
            if count == 1:
                if vc.id not in pending_alerts:
                    task = asyncio.create_task(alert_if_alone(vc, text_channel, role))
                    pending_alerts[vc.id] = task
            elif count == 0:
                if vc.id in pending_alerts:
                    pending_alerts[vc.id].cancel()
                    del pending_alerts[vc.id]
                if vc.id in active_vc_timer:
                    del active_vc_timer[vc.id]

async def alert_if_alone(vc_channel, text_channel, role):
    try:
        await asyncio.sleep(300)
        if len(vc_channel.members) == 1:
            await text_channel.send(f"🏋️{vc_channel.members[0].display_name}がラウンジで待ってるよ。{role.mention} みんな集まれ！きみが行くなら俺も行く!!")
    except asyncio.CancelledError:
        pass

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
