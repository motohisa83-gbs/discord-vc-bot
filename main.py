import os
import asyncio
import discord
import pandas as pd
from discord.ext import commands, tasks
from discord import app_commands, Interaction
from discord.ui import View, Button

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
