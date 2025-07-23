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
