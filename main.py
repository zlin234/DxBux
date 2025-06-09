import os
import discord
from discord.ext import commands
import random
import json
from threading import Thread
from flask import Flask

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
    return balances.get(str(user_id), 1000)  # Default 1000 coins if new user

def set_balance(user_id, amount):
    balances = load_balances()
    balances[str(user_id)] = amount
    save_balances(balances)

# ------------------ DISCORD BOT SETUP ------------------

intents = discord.Intents.default()
intents.message_content = True

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
            await interaction.response.send_message("You don't have enough balance for this bet!", ephemeral=True)
            await self.disable_all_items()
            await interaction.message.edit(view=self)
            return

        result = random.choice(["heads", "tails"])

        if result == user_choice:
            new_balance = current_balance + self.bet_amount
            outcome = f"🎉 It was **{result.capitalize()}**! You **won** {self.bet_amount} coins!"
        else:
            new_balance = current_balance - self.bet_amount
            outcome = f"😢 It was **{result.capitalize()}**. You **lost** {self.bet_amount} coins."

        set_balance(self.user_id, new_balance)
        self.has_responded = True

        await self.disable_all_items()
        await interaction.message.edit(view=self)

        await interaction.response.send_message(
            f"{interaction.user.mention} {outcome} Your new balance is **{new_balance} coins**."
        )

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.primary)
    async def heads_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your coin flip!", ephemeral=True)
        await self.update_balance_and_send_result(interaction, "heads")

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.secondary)
    async def tails_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your coin flip!", ephemeral=True)
        await self.update_balance_and_send_result(interaction, "tails")

@bot.command()
async def cf(ctx, amount: int):
    user_id = ctx.author.id
    current_balance = get_balance(user_id)

    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if current_balance < amount:
        return await ctx.send("❌ You don't have enough balance.")

    view = CoinFlipView(user_id, amount)
    await ctx.send(f"{ctx.author.mention}, choose Heads or Tails to flip the coin and bet **{amount}** coins!", view=view)

# ------------------ BALANCE CHECK COMMANDS ------------------

@bot.command(aliases=["balance"])
async def bal(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    balance = get_balance(member.id)
    await ctx.send(f"{member.display_name} has 💰 **{balance} coins**.")

# ------------------ ADMIN SETBAL COMMAND ------------------

def is_admin():
    async def predicate(ctx):
        admin_role = discord.utils.get(ctx.guild.roles, name="Admin")
        if admin_role in ctx.author.roles:
            return True
        await ctx.send("❌ You need the Admin role to use this command.")
        return False
    return commands.check(predicate)

@bot.command(aliases=["setbalance", "setbal"])
@is_admin()
async def setbal(ctx, member: discord.Member, amount: int):
    if amount < 0:
        return await ctx.send("❌ Balance cannot be negative.")
    set_balance(member.id, amount)
    await ctx.send(f"✅ Set {member.display_name}'s balance to **{amount} coins**.")

# ------------------ BLACKJACK (Stub) ------------------

@bot.command()
async def bj(ctx, amount: int):
    # Placeholder for blackjack game logic
    user_id = ctx.author.id
    current_balance = get_balance(user_id)
    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if current_balance < amount:
        return await ctx.send("❌ You don't have enough balance.")
    # TODO: Implement blackjack logic here
    await ctx.send(f"Blackjack is not implemented yet, but you tried to bet {amount} coins!")

# ------------------ MINESWEEPER (Stub) ------------------

@bot.command()
async def minesweeper(ctx, amount: int):
    # Placeholder for minesweeper game logic
    user_id = ctx.author.id
    current_balance = get_balance(user_id)
    if amount <= 0:
        return await ctx.send("❌ Bet must be more than 0.")
    if current_balance < amount:
        return await ctx.send("❌ You don't have enough balance.")
    # TODO: Implement minesweeper logic here
    await ctx.send(f"Minesweeper is not implemented yet, but you tried to bet {amount} coins!")

# ------------------ KEEP ALIVE (FLASK) ------------------

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
