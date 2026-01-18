import logging
import os
import asyncio
import aiohttp
from dotenv import load_dotenv

# Use imports compatible with your version
from livekit.agents import (
    AutoSubscribe, 
    JobContext, 
    WorkerOptions, 
    cli, 
    Agent,           
    AgentSession,    
    function_tool
)
from livekit.plugins import openai, silero, deepgram

load_dotenv()
logger = logging.getLogger("voxtron-agent")

# --- 1. CONFIGURATION ---
GROQ_LLM = openai.LLM(
    model="llama-3.1-8b-instant",
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY")
)

# Use Deepgram for Ears (More reliable than Groq STT)
DEEPGRAM_STT = deepgram.STT(
    model="nova-2-general", 
    api_key=os.getenv("DEEPGRAM_API_KEY")
)

DEEPGRAM_TTS = deepgram.TTS(
    model="aura-helios-en",
    api_key=os.getenv("DEEPGRAM_API_KEY")
)

# --- 2. THE TICKET TOOL ---
@function_tool
async def create_ticket(customer_name: str, issue: str):
    """
    Creates a support ticket in the database. 
    Use this tool IMMEDIATELY when the user mentions a problem.
    """
    # DEBUG PRINT: This will show up in your terminal if the tool runs
    print(f"\n[TOOL TRIGGERED] Creating ticket for: {customer_name} -> Issue: {issue}\n")
    
    # Hardcoded email for demo simplicity
    api_url = "http://localhost:8000/api/tickets"
    payload = {
        "customer_name": customer_name,
        "customer_email": "demo@example.com", 
        "issue_description": issue,
        "status": "Open"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"[SUCCESS] Ticket ID: {data.get('id')}")
                    return f"SUCCESS: Ticket #{data.get('id')} created."
                else:
                    error_text = await response.text()
                    print(f"[ERROR] Backend refused: {error_text}")
                    return "Error: Backend failed to save ticket."
    except Exception as e:
        print(f"[EXCEPTION] {e}")
        return f"System Error: {str(e)}"

# --- 3. MAIN LOGIC ---
async def entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # FIX 1: GET USER NAME
    print("Waiting for user to join...")
    participant = await ctx.wait_for_participant()
    user_name = participant.name or "User"
    print(f"User joined: {user_name}")

    # FIX 2: STRONG INSTRUCTIONS
    # We explicitly tell the brain to USE the tool.
    agent_persona = Agent(
        instructions=(
            f"You are speaking with {user_name}. "
            "You are a helpful support bot. "
            "If the user describes a problem, IMMEDIATELY offer to create a ticket. "
            "If they say yes, call the 'create_ticket' tool."
        ),
        tools=[create_ticket] # <--- This registers the tool
    )

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=DEEPGRAM_STT,     
        llm=GROQ_LLM,
        tts=DEEPGRAM_TTS,
    )

    await session.start(room=ctx.room, agent=agent_persona)

    # Initial Greeting
    await session.generate_reply(
        instructions=f"Say 'Hello {user_name}, I am ready to help. What is the issue?'"
    )

    # Keep alive loop
    await asyncio.Event().wait()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))