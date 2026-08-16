import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
from datetime import datetime, timedelta
import random

DATA_FILE = 'configs/giveaways.json'
BLACKLIST_FILE = 'configs/giveaway_blacklist.json'

def load_giveaways():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_giveaways(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_blacklist():
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            return json.load(f)
    return {"users": []}

def save_blacklist(data):
    with open(BLACKLIST_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def parse_time(time_str):
    """Parse time string like '1h', '30m', '5s' into seconds"""
    time_str = time_str.lower().strip()
    if time_str.endswith('h'):
        return int(time_str[:-1]) * 3600
    elif time_str.endswith('m'):
        return int(time_str[:-1]) * 60
    elif time_str.endswith('s'):
        return int(time_str[:-1])
    return None

def format_time_remaining(seconds):
    if seconds <= 0:
        return "0s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
    elif minutes > 0:
        return f"{minutes}m {secs}s" if secs > 0 else f"{minutes}m"
    else:
        return f"{secs}s"

class GiveawayManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("Giveaway manager initialized", flush=True)
        self.check_expiry.start()

    def cog_unload(self):
        self.check_expiry.cancel()

    @tasks.loop(seconds=10)
    async def check_expiry(self):
        """Check if any giveaways have expired"""
        try:
            giveaways = load_giveaways()
            for channel_id_str, giveaway in list(giveaways.items()):
                if giveaway.get('active', False):
                    started_at = datetime.fromisoformat(giveaway['started_at'])
                    end_time = started_at + timedelta(seconds=giveaway.get('duration_seconds', 3600))

                    if datetime.now() > end_time:
                        print(f"Giveaway {channel_id_str} expired", flush=True)
                        channel_id = int(channel_id_str)
                        try:
                            giveaway['active'] = False
                            save_giveaways(giveaways)
                            channel = await self.bot.fetch_channel(channel_id)
                            
                            winners = self.pick_winners(giveaway)
                            if winners:
                                winner_text = ""
                                for i, winner_id in enumerate(winners, 1):
                                    winner_text += f"{i}. <@{winner_id}>\n"
                                
                                embed = discord.Embed(title="🎊 Giveaway Ended!", color=discord.Color.gold())
                                embed.add_field(name="Prize", value=giveaway['prize'], inline=False)
                                embed.add_field(name="Entries", value=str(len(giveaway['entries'])), inline=True)
                                embed.add_field(name="Winners", value=winner_text, inline=False)
                                await channel.send(embed=embed)
                                
                                secrets = {}
                                if os.path.exists('configs/private.keys'):
                                    with open('configs/private.keys', 'r') as f:
                                        secrets = json.load(f)
                                results_channel_id = secrets.get('results_channel_id')
                                if results_channel_id:
                                    try:
                                        results_channel = await self.bot.fetch_channel(results_channel_id)
                                        await results_channel.send(embed=embed)
                                    except:
                                        pass
                            
                            giveaway['active'] = False
                            save_giveaways(giveaways)
                        except Exception as e:
                            print(f"Error auto-ending giveaway: {e}", flush=True)
        except Exception as e:
            print(f"Error in check_expiry: {e}", flush=True)

    @check_expiry.before_loop
    async def before_check_expiry(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        blacklist = load_blacklist()
        user_id_str = str(message.author.id)
        
        giveaways = load_giveaways()
        channel_id_str = str(message.channel.id)
        if channel_id_str in giveaways and giveaways[channel_id_str].get('active', False):
            if user_id_str in blacklist.get('users', []):
                # Blacklisted user - show black flag
                await message.add_reaction("🚩")
                return
            
            if user_id_str not in giveaways[channel_id_str]['entries']:
                giveaways[channel_id_str]['entries'][user_id_str] = {
                    "username": message.author.name,
                    "timestamp": datetime.now().isoformat()
                }
                save_giveaways(giveaways)
                await message.add_reaction("✅")

    giveaway_group = app_commands.Group(name="giveaway", description="Giveaway commands")
    blacklist_group = app_commands.Group(name="giveaway_blacklist", description="Blacklist commands")

    @giveaway_group.command(name="start", description="Start a giveaway")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(prize="Prize", duration="Duration (1h, 30m, 5s)", winners="Winners")
    async def start_giveaway(self, interaction: discord.Interaction, prize: str, duration: str, winners: int):
        seconds = parse_time(duration)
        if seconds is None or seconds <= 0:
            await interaction.response.send_message("❌ Invalid duration", ephemeral=True)
            return
        
        os.makedirs('configs/giveaways', exist_ok=True)
        giveaway_id = f"giveaway_{prize.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        giveaway = {
            "id": giveaway_id,
            "channel_id": interaction.channel_id,
            "active": True,
            "entries": {},
            "prize": prize,
            "duration_seconds": seconds,
            "num_winners": winners,
            "started_by": interaction.user.name,
            "started_at": datetime.now().isoformat(),
            "rejected_winners": []
        }
        
        giveaways = load_giveaways()
        giveaways[str(interaction.channel_id)] = giveaway
        save_giveaways(giveaways)
        
        embed = discord.Embed(title="🎉 Giveaway Started!", color=discord.Color.green())
        embed.add_field(name="Prize", value=prize, inline=False)
        embed.add_field(name="Duration", value=duration, inline=True)
        embed.add_field(name="Winners", value=str(winners), inline=True)
        embed.description = "Message to enter!"
        await interaction.response.send_message(embed=embed)
        print(f"Giveaway started: {prize}", flush=True)

    @giveaway_group.command(name="entries", description="View entry count")
    async def entries(self, interaction: discord.Interaction):
        giveaways = load_giveaways()
        channel_id_str = str(interaction.channel_id)
        
        if channel_id_str not in giveaways or not giveaways[channel_id_str].get('active', False):
            await interaction.response.send_message("❌ No active giveaway", ephemeral=True)
            return
        
        giveaway = giveaways[channel_id_str]
        entry_count = len(giveaway['entries'])
        started_at = datetime.fromisoformat(giveaway['started_at'])
        end_time = started_at + timedelta(seconds=giveaway.get('duration_seconds', 3600))
        remaining = int((end_time - datetime.now()).total_seconds())
        remaining_time = format_time_remaining(remaining) if remaining > 0 else "Ended"
        
        embed = discord.Embed(title="📊 Entries", color=discord.Color.blue())
        embed.add_field(name="Count", value=str(entry_count), inline=True)
        embed.add_field(name="Time Remaining", value=remaining_time, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @giveaway_group.command(name="info", description="Full giveaway info")
    async def gavinfo(self, interaction: discord.Interaction):
        giveaways = load_giveaways()
        channel_id_str = str(interaction.channel_id)
        
        if channel_id_str not in giveaways or not giveaways[channel_id_str].get('active', False):
            await interaction.response.send_message("❌ No active giveaway", ephemeral=True)
            return
        
        giveaway = giveaways[channel_id_str]
        entry_count = len(giveaway['entries'])
        started_at = datetime.fromisoformat(giveaway['started_at'])
        end_time = started_at + timedelta(seconds=giveaway.get('duration_seconds', 3600))
        remaining = int((end_time - datetime.now()).total_seconds())
        remaining_time = format_time_remaining(remaining) if remaining > 0 else "Ended"
        
        embed = discord.Embed(title="🎉 Giveaway Info", color=discord.Color.green())
        embed.add_field(name="Prize", value=giveaway['prize'], inline=False)
        embed.add_field(name="Entries", value=str(entry_count), inline=True)
        embed.add_field(name="Winners", value=str(giveaway.get('num_winners', 1)), inline=True)
        embed.add_field(name="Time Remaining", value=remaining_time, inline=True)
        embed.add_field(name="Started By", value=giveaway.get('started_by', 'Unknown'), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def pick_winners(self, giveaway):
        """Pick winners excluding rejected ones"""
        entries = list(giveaway['entries'].keys())
        rejected = giveaway.get('rejected_winners', [])
        available = [e for e in entries if e not in rejected]
        
        if not available:
            return []
        
        num_winners = giveaway.get('num_winners', 1)
        winners_count = min(num_winners, len(available))
        return random.sample(available, winners_count)

    @giveaway_group.command(name="end", description="End giveaway and pick winners")
    @app_commands.checks.has_permissions(administrator=True)
    async def end_giveaway(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        
        giveaways = load_giveaways()
        channel_id_str = str(interaction.channel_id)
        
        if channel_id_str not in giveaways or not giveaways[channel_id_str].get('active', False):
            await interaction.followup.send("❌ No active giveaway", ephemeral=True)
            return
        
        giveaway = giveaways[channel_id_str]
        entries = list(giveaway['entries'].keys())
        
        if not entries:
            giveaway['active'] = False
            save_giveaways(giveaways)
            await interaction.followup.send("❌ No entries", ephemeral=True)
            return
        
        winners = self.pick_winners(giveaway)
        
        if not winners:
            giveaway['active'] = False
            save_giveaways(giveaways)
            await interaction.followup.send("❌ No available winners", ephemeral=True)
            return
        
        winner_text = "\n".join([f"{i}. <@{wid}>" for i, wid in enumerate(winners, 1)])
        
        embed = discord.Embed(title="🎊 Giveaway Ended!", color=discord.Color.gold())
        embed.add_field(name="Prize", value=giveaway['prize'], inline=False)
        embed.add_field(name="Winners", value=winner_text, inline=False)
        
        await interaction.channel.send(embed=embed)
        
        secrets = {}
        if os.path.exists('configs/private.keys'):
            with open('configs/private.keys', 'r') as f:
                secrets = json.load(f)
        results_channel_id = secrets.get('results_channel_id')
        if results_channel_id:
            try:
                results_channel = await self.bot.fetch_channel(results_channel_id)
                await results_channel.send(embed=embed)
            except:
                pass
        
        giveaway['active'] = False
        save_giveaways(giveaways)
        await interaction.followup.send("✅ Giveaway ended", ephemeral=True)
        print(f"Giveaway ended in {channel_id_str}", flush=True)

    @giveaway_group.command(name="cancel", description="Cancel giveaway")
    @app_commands.checks.has_permissions(administrator=True)
    async def cancel_giveaway(self, interaction: discord.Interaction):
        giveaways = load_giveaways()
        channel_id_str = str(interaction.channel_id)
        
        if channel_id_str not in giveaways or not giveaways[channel_id_str].get('active', False):
            await interaction.response.send_message("❌ No active giveaway", ephemeral=True)
            return
        
        giveaways[channel_id_str]['active'] = False
        save_giveaways(giveaways)
        await interaction.response.send_message("✅ Cancelled", ephemeral=True)
        print(f"Giveaway cancelled in {channel_id_str}", flush=True)

    @blacklist_group.command(name="add", description="Blacklist user")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_blacklist(self, interaction: discord.Interaction, user: discord.User):
        blacklist = load_blacklist()
        user_id_str = str(user.id)
        if user_id_str not in blacklist['users']:
            blacklist['users'].append(user_id_str)
            save_blacklist(blacklist)
            await interaction.response.send_message(f"✅ {user} blacklisted", ephemeral=True)

    @blacklist_group.command(name="remove", description="Remove from blacklist")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_blacklist(self, interaction: discord.Interaction, user: discord.User):
        blacklist = load_blacklist()
        user_id_str = str(user.id)
        if user_id_str in blacklist['users']:
            blacklist['users'].remove(user_id_str)
            save_blacklist(blacklist)
            await interaction.response.send_message(f"✅ Removed", ephemeral=True)

    @blacklist_group.command(name="list", description="View blacklist")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_blacklist(self, interaction: discord.Interaction):
        blacklist = load_blacklist()
        users = blacklist.get('users', [])
        
        if not users:
            await interaction.response.send_message("✅ Blacklist is empty", ephemeral=True)
            return
        
        user_list = ""
        for user_id in users:
            user_list += f"<@{user_id}>\n"
        
        embed = discord.Embed(title="🚫 Giveaway Blacklist", color=discord.Color.red())
        embed.description = user_list
        embed.set_footer(text=f"Total: {len(users)} user(s)")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayManager(bot))
    print("Giveaway plugin loaded", flush=True)
