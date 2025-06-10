import os
import discord
from discord.ext import commands, tasks
import random
import json
from threading import Thread
from flask import Flask
from datetime import datetime

# ------------------ BALANCE MANAGEMENT ------------------

BALANCE_FILE = "balances.json"

def load_balances():
    try:
        with open(BALANCE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_balances(balances):
    with open(BALANCE_FILE, "w") as f:
        json.dump(balances, f)

def get_balance(user_id):
    balances = load_balances()
    return balances.get(str(user_id), 1000)

def set_balance(user_id, amount):
    balances = load_balances()
    balances[str(user_id)] = amount
    save_balances(balances)

def add_balance(user_id, amount):
    balances = load_balances()
    balances[str(user_id)] = balances.get(str(user_id), 1000) + amount
    save_balances(balances)

# ------------------ DISCORD BOT SETUP ------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="-", intents=intents)

# ------------------ COIN FLIP BUTTONS ------------------

class CoinFlipView(discord.ui.View):
    def __init__(self, user_id: int, bet_amount: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.has_responded = False

    async def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def update_balance_and_send_result(self, interaction: discord.Interaction, user_choice: str):
        if self.has_responded:
            await interaction.response.send_message("You already flipped!", ephemeral=True)
            return

        current_balance = get_balance(self.user_id)
        if self.bet_amount > current_balance:
            await interaction.response.send_message("Not enough balance!", ephemeral=True)
            await self.disable_all_items()
            await interaction.message.edit(view=self)
            return

        result = random.choice(["heads", "tails"])
        if result == user_choice:
            new_balance = current_balance + self.bet_amount
            outcome = f"🎉 It was **{result}**! You **won** {self.bet_amount} coins!"
        else:
            new_balance = current_balance - self.bet_amount
            outcome = f"😢 It was **{result}**. You **lost** {self.bet_amount} coins."

        set_balance(self.user_id, new_balance)
        self.has_responded = True
        await self.disable_all_items()
        await interaction.message.edit(view=self)

        await interaction.response.send_message(
            f"{interaction.user.mention} {outcome} Your new balance: **{new_balance} coins**."
        )

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.primary)
    async def heads_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your coin flip!", ephemeral=True)
        await self.update_balance_and_send_result(interaction, "heads")

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.secondary)
    async def tails_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your coin flip!", ephemeral=True)
        await self.update_balance_and_send_result(interaction, "tails")

@bot.command()
async def cf(ctx, amount: int):
    if amount <= 0:
        return await ctx.send("❌ Bet must be greater than 0.")
    if get_balance(ctx.author.id) < amount:
        return await ctx.send("❌ Insufficient balance.")
    view = CoinFlipView(ctx.author.id, amount)
    await ctx.send(f"{ctx.author.mention}, choose Heads or Tails to bet **{amount}** coins!", view=view)

# ------------------ BALANCE COMMANDS ------------------

@bot.command(aliases=["balance"])
async def bal(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"{member.display_name} has 💰 **{get_balance(member.id)} coins**.")

# ------------------ ADMIN SETBAL COMMAND ------------------

def is_admin():
    async def predicate(ctx):
        role = discord.utils.get(ctx.guild.roles, name="Admin")
        if role and role in ctx.author.roles:
            return True
        await ctx.send("❌ You need the Admin role.")
        return False
    return commands.check(predicate)

@bot.command()
@is_admin()
async def setbal(ctx, amount: int, member: discord.Member = None):
    if amount < 0:
        return await ctx.send("❌ Balance can't be negative.")
    if member:
        set_balance(member.id, amount)
        return await ctx.send(f"✅ Set {member.display_name}'s balance to {amount} coins.")
    else:
        balances = load_balances()
        for user_id in balances:
            set_balance(user_id, amount)
        await ctx.send(f"✅ Set **all user balances** to {amount} coins.")

# ------------------ BLACKJACK vs NPC ------------------

@bot.command()
async def bj(ctx, amount: int):
    user_id = ctx.author.id
    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if get_balance(user_id) < amount:
        return await ctx.send("❌ Not enough balance.")

    user_card = random.randint(1, 11) + random.randint(1, 11)
    npc_card = random.randint(1, 11) + random.randint(1, 11)

    result = f"You: {user_card} | NPC: {npc_card}\n"
    if user_card > npc_card:
        add_balance(user_id, amount)
        result += f"🎉 You win! You earned {amount} coins."
    elif user_card < npc_card:
        add_balance(user_id, -amount)
        result += f"😢 You lost! You lost {amount} coins."
    else:
        result += "⚖️ It's a tie! No coins lost or won."

    await ctx.send(result)

# ------------------ MINESWEEPER (stub) ------------------

@bot.command()
async def minesweeper(ctx, amount: int):
    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if get_balance(ctx.author.id) < amount:
        return await ctx.send("❌ Not enough balance.")
    await ctx.send("💣 Minesweeper is coming soon!")

# ------------------ DAILY ALLOWANCE ------------------

@tasks.loop(hours=24)
async def daily_allowance():
    balances = load_balances()
    for user_id in balances:
        balances[user_id] += 100
    save_balances(balances)
    print("✅ Daily allowance of 100 coins given to all users.")

@daily_allowance.before_loop
async def before_daily():
    await bot.wait_until_ready()

daily_allowance.start()

# ------------------ KEEP ALIVE (RENDER FLASK) ------------------

app = Flask("")

@app.route("/")
def home():
    return "I'm alive!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ------------------ RUN BOT ------------------

keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
