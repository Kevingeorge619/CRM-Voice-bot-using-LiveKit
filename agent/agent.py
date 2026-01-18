import logging
import os
import asyncio
import aiohttp
from dotenv import load_dotenv

# Standard imports compatible with your version
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

# --- CONFIGURATION ---
GROQ_LLM = openai.LLM(
    model="llama-3.1-8b-instant",
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY")
)

DEEPGRAM_STT = deepgram.STT(
    model="nova-2-general", 
    api_key=os.getenv("DEEPGRAM_API_KEY")
)

DEEPGRAM_TTS = deepgram.TTS(
    model="aura-helios-en",
    api_key=os.getenv("DEEPGRAM_API_KEY")
)

# --- MAIN LOGIC ---
async def entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    user_name = participant.name or "User"
    user_email = participant.metadata or "unknown@example.com"
    
    # --- MEMORY STATE ---
    # We use a dictionary to store memory for this specific call.
    # This works on ALL versions of Python/LiveKit.
    session_state = {"ticket_id": None}

    # --- DEFINING TOOL INSIDE ENTRYPOINT (CLOSURE) ---
    @function_tool
    async def manage_ticket(issue: str):
        """
        Logs a technical issue. 
        Automatically handles creating a NEW ticket or UPDATING an existing one.
        """
        base_url = "http://localhost:8000/api/tickets"
        current_id = session_state["ticket_id"]

        # SCENARIO A: UPDATE EXISTING TICKET
        if current_id:
            print(f"\n[MEMORY] Found existing Ticket #{current_id}. Appending info...\n")
            url = f"{base_url}/{current_id}/append"
            # We construct the payload manually for the backend
            payload = {"additional_info": issue}
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.put(url, json=payload) as response:
                        if response.status == 200:
                            return f"I have added that detail to your existing ticket #{current_id}."
                        else:
                            return "Error updating ticket."
            except Exception as e:
                return f"System Error: {str(e)}"

        # SCENARIO B: CREATE NEW TICKET
        else:
            print(f"\n[NEW] Creating fresh ticket for {user_name}...\n")
            payload = {
                "customer_name": user_name,
                "customer_email": user_email,
                "issue_description": issue,
                "status": "Open"
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(base_url, json=payload) as response:
                        if response.status == 200:
                            data = await response.json()
                            new_id = data.get('id')
                            
                            # SAVE TO MEMORY
                            session_state["ticket_id"] = new_id
                            print(f"[SUCCESS] Ticket ID #{new_id} saved to session memory.")
                            
                            return f"I have created a new ticket #{new_id}."
                        else:
                            return "Error creating ticket."
            except Exception as e:
                return f"System Error: {str(e)}"

    # --- AGENT INSTRUCTIONS ---
    instructions = (
        f"You are speaking with {user_name} ({user_email}). "
        "You are a Level 1 Tech Support Agent. Follow this protocol strictly:\n"
        "1. **TROUBLESHOOT FIRST:** If the user reports a problem, DO NOT create a ticket immediately. "
        "Offer 1 basic troubleshooting step (e.g., 'Have you tried restarting?', 'Check the cables').\n"
        "2. **ESCALATE IF FAILED:** Only if the user says the step didn't work, OR if they explicitly ask to 'create a ticket', "
        "then use the 'manage_ticket' tool."
    )

    agent_persona = Agent(
        instructions=instructions,
        tools=[manage_ticket] # Register the inner function
    )

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=DEEPGRAM_STT,     
        llm=GROQ_LLM,
        tts=DEEPGRAM_TTS,
    )

    await session.start(room=ctx.room, agent=agent_persona)

    await session.generate_reply(
        instructions=f"Say 'Hello {user_name}, I am your Support Agent. How can I help you today?'"
    )

    await asyncio.Event().wait()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))