import discord
from discord.ext import commands
import os
import sys
import importlib
import json

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_message(message):
    print(f"[BOT] on_message fired channel={message.channel.id} content={message.content[:20]}", flush=True)
    if message.author.bot:
        await bot.process_commands(message)
        return
    print(f"[BOT] Available cogs: {list(bot.cogs.keys())}", flush=True)
    ark_chat = bot.cogs.get("ArkChat")
    print(f"[BOT] ArkChat cog: {ark_chat}", flush=True)
    if ark_chat:
        await ark_chat.relay_to_ark(message)
    await bot.process_commands(message)

PLUGINS_DIR = 'plugins'
PLUGINS_STATE_FILE = 'plugins_state.json'

def load_plugins_state():
    if os.path.exists(PLUGINS_STATE_FILE):
        with open(PLUGINS_STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_plugins_state(state):
    with open(PLUGINS_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

async def load_plugins():
    """Load all enabled plugins from the plugins directory"""
    print(f"Starting plugin load from {PLUGINS_DIR}...", flush=True)
    
    if not os.path.exists(PLUGINS_DIR):
        os.makedirs(PLUGINS_DIR)
        print(f"Created {PLUGINS_DIR} directory", flush=True)
        return
    
    state = load_plugins_state()
    plugin_files = [f for f in os.listdir(PLUGINS_DIR) if f.endswith('.py') and not f.startswith('_')]
    print(f"Found {len(plugin_files)} plugin files: {plugin_files}", flush=True)
    
    for filename in plugin_files:
        plugin_name = filename[:-3]
        
        # Check if plugin is enabled
        if not state.get(plugin_name, {}).get('enabled', True):
            print(f"Skipped {plugin_name} (disabled)", flush=True)
            continue
        
        try:
            print(f"Loading plugin: {plugin_name}", flush=True)
            spec = importlib.util.spec_from_file_location(plugin_name, os.path.join(PLUGINS_DIR, filename))
            plugin = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(plugin)
            
            if hasattr(plugin, 'setup'):
                await plugin.setup(bot)
                print(f"✓ Loaded plugin: {plugin_name}", flush=True)
            else:
                print(f"✗ Plugin {plugin_name} has no setup function", flush=True)
        except Exception as e:
            print(f"✗ Error loading {plugin_name}: {e}", flush=True)
            import traceback
            traceback.print_exc()

@bot.event
async def on_ready():
    print(f"[BOT] Registered events: {list(bot.extra_events.keys())}")
    print(f"[BOT] Guilds: {[g.name for g in bot.guilds]}")
    print(f"[BOT] Can read messages in guilds: {[g.me.guild_permissions.read_messages for g in bot.guilds]}")
    for guild in bot.guilds:
        for channel in guild.text_channels[:3]:
            print(f"[BOT] Channel: {channel.name} can_read={channel.permissions_for(guild.me).read_messages} can_read_history={channel.permissions_for(guild.me).read_message_history}")
    print(f'{bot.user} has connected to Discord!', flush=True)
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)', flush=True)
    except Exception as e:
        print(f'Failed to sync: {e}', flush=True)

async def main():
    print("Bot starting...", flush=True)
    print(f"Current directory: {os.getcwd()}", flush=True)
    
    await load_plugins()
    
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    if not TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not set!")
        return
    
    print("Connecting to Discord...", flush=True)
    async with bot:
        await load_plugins()
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
