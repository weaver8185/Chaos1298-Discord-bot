import discord
import json
import os

IGN_FILE = 'user_igns.json'

def load_igns():
    if os.path.exists(IGN_FILE):
        with open(IGN_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_igns(data):
    with open(IGN_FILE, 'w') as f:
        json.dump(data, f, indent=2)

async def setup(bot):
    @bot.tree.command(name='ign')
    @discord.app_commands.describe(ingame_name="Your in-game name")
    async def set_ign(interaction: discord.Interaction, ingame_name: str):
        try:
            igns = load_igns()
            user_id = str(interaction.user.id)
            
            igns[user_id] = ingame_name
            save_igns(igns)
            
            await interaction.response.send_message(f"✅ IGN set to: **{ingame_name}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
