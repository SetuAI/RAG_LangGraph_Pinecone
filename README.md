# RAG_LangGraph_Pinecone


Pre-requisite PI Keys : Tavily ,Pinecone, Groq

Tavily : https://app.tavily.com/home
Groq : https://console.groq.com/keys
Pinecone : https://app.pinecone.io/organizations/-NvankU832R3Eg6IXOo3/projects/feff407b-ff5a-472a-a02a-d576882ed484/keys

to manage python package : uv
uv init
uv venv
source .venv/Scripts/activate

to install requirements : uv pip install -r requirements.txt
------------------------------------------------------------------------------------

After dependancies are installed 

in main.py, create a simple script to check if api will work or not

from fastapi import FastAPI


app = FastAPI(name = "langgraph-ai-agent")

# creating a simple endpoint to check if the api is working
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "LangGraph AI Agent is running successfully!"}

def main():
    print("Starting LangGraph AI Agent...")
    
if __name__ == "__main__":
    main()


to execute
uvicorn main:app --reload

You can also check it on postman
------------------------------------------------------------------------------------

After this works, move to backend programming :
create backend directory :
mkdir backend/
create .env (to store API KEYS)
then create config.py  , vectostore.py , agent.py (build the agentic workflow here)
finally go to main.py - in backend directory (for FAST API endpoint building)


------------------------------------------------------------------------------------

Postman :

Health Endpoint Check : healthCheck 

Add New Request : GET : http://127.0.0.1:8000/chat/

Check for {'Status' : '200 OK'}


Chat Endpoint Check: ChatRoute

Add New Request : POST  : http://127.0.0.1:8000/chat/

{
    "session_id": "test-session-001",
    "query" : "What do you know about Wells Fargo?",
    "enable_we_search" :true
}

Upload Document Endpoint : 

Add New Request : POST  : http://127.0.0.1:8000/upload-document/

(Select Body --> form-date --> key : file , Value : pdf document )

** Make sure the Index name is correctly defined in the vectostore.py. Also check the dimension size. **