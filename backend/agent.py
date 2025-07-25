# Creating agent with LangGraph 
# import dependencies
# Refer assets directory for more details on how to use LangGraph
import os
from config import GROQ_API_KEY, PINECONE_API_KEY, TAVILY_API_KEY
from langchain_groq import ChatGroq # pip install langchain-groq
from typing import TypedDict, List, Optional,Literal
from langchain_core.messages import BaseMessage,HumanMessage,AIMessage # Base Message can be Human Message, System Message, AI Message etc.
from pydantic import BaseModel,Field
from langgraph.graph import StateGraph, END  # pip install langgraph
from langgraph.checkpoint.memory import MemorySaver
from langchain_tavily import TavilySearch   # pip install langchain-tavily
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig 
from vectorstore import get_retriever, add_document # Importing the retriever function from vectorstore.py

os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY
tavily = TavilySearch(max_results=3, topic="general")

'''
Defining the tools : web_search_tool and rag_search_tool (read about tools in tools.txt)
'''

@tool
def web_search_tool(query: str) -> str:
    """Up-to-date web info via Tavily"""
    try:
        result = tavily.invoke({"query": query})
        if isinstance(result, dict) and 'results' in result:
            formatted_results = []
            for item in result['results']:
                title = item.get('title', 'No title')
                content = item.get('content', 'No content')
                url = item.get('url', '')
                formatted_results.append(f"Title: {title}\nContent: {content}\nURL: {url}")
            return "\n\n".join(formatted_results) if formatted_results else "No results found"
        else:
            return str(result)
    except Exception as e:
        return f"WEB_ERROR::{e}"

@tool
def rag_search_tool(query: str) -> str:
    """Top-K chunks from KB (empty string if none)"""
    try:
        retriever_instance = get_retriever() # import get_retriever from vectorstore.py
        docs = retriever_instance.invoke(query, k=5) # Increased from 3 to 5
        return "\n\n".join(d.page_content for d in docs) if docs else ""
    except Exception as e:
        return f"RAG_ERROR::{e}"



# Pydantic schemas for structured output
class RouteDecision(BaseModel):
    route : Literal["rag", "web", "answer", "end"] 
    reply : str | None = Field(None, description = "Filled only when route == 'end")
    
class RagJudge(BaseModel):
    sufficient:bool = Field(... , description = "True if retrieved information is sufficient to answer the user's query\
        False otherwise.")
    

# Define LLM instances with structured schemas

os.environ['GROQ_API_KEY'] = GROQ_API_KEY

# align this with pydantic schema
router_llm = ChatGroq(model="llama3-70b-8192", temperature = 0).with_structured_output(RouteDecision)
judge_llm = ChatGroq(model="llama3-70b-8192", temperature=0).with_structured_output(RagJudge)
answer_llm = ChatGroq(model="llama3-70b-8192", temperature=0.7)

    

# Define the State : Shared data structure for the agent
   
class AgentState(TypedDict,total=False):
    
    messages : List[BaseMessage] # Current conversation history (to get the latest user query)
    route : Literal["rag","web","answer","end"]
    rag:str # output from rag node
    web:str # information from web search
    web_search_enabled : bool # User's preference for web search (True/False)
    

# Build the first Node (Refer ai agent workflow diagram in assets)



"""
Core Logic : 

Extracts the latest user query

Calls the 'router_llm'(Groq LLM with structured output 'RouteDecision') to get an initial route decision based on detailed
system prompt

Conditional override : If 'web_search_enabled' is False and 'router_llm' initially decided 'web' it overrides the route to 'rag'

Ouputs / Updates to Agent State :

- route : The final decided route ('rag', 'web', 'answer', or 'end')
- messages : Updated if route is  = to 'end' (adds AI's direct response to the user's query)
- web_search_enabled : Passed through to maintain state)
- (Optional) 'initial_router_Decision' : Records LLMs raw decision before overrides
- (Optional) 'router_override_reason' : Explains why the route was overridden (if applicable)

Next possible Nodes : 
 - rag_lookup (if route == 'rag')
 - web_search (if route == 'web')
 - answer (if route == 'answer')
 - END (if route == 'end')

"""

# Define Node 1 : router (decision node) , every node returs updated AgentState

def router_node(state: AgentState , config:RunnableConfig) -> AgentState:
    print("Entering router_node ........")
    '''
    extract query ,when user gives the query, it is stored in the messages list : messages : List[BaseMessage] 
    in this AgentState, Now we need to extract the message from AgentState messages list.
    Now, the messags are stored as Base Messages, which can be HumanMessage, AIMessage, SystemMessage etc.
    But we want the Human Message .
    
    '''
    # the latest message will be stored in the last index of the messages list, reversed to get the latest message
    # next line extracts the latest human message from the messages list
    # if no human message is found, it will return None / Blank String
    query = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
    
    # if the user has enabled web search , we will call the web search node
    
    web_search_enabled = config.get("configurable", {}).get("web_search_enabled", True) # <-- CHANGED LINE
    print(f"Router received web search info : {web_search_enabled}")
    
    # Now we need the system prompt
    system_prompt = (
        "You are an intelligent routing agent designed to direct user queries to the most appropriate tool."
        "Your primary goal is to provide accurate and relevant information by selecting the best source."
        "Prioritize using the **internal knowledge base (RAG)** for factual information that is likely "
        "to be contained within pre-uploaded documents or for common, well-established facts."
    )

    # if the web_search is enabled, then we have to add another system prompt
    if web_search_enabled:
        system_prompt += (
            "You **CAN** use web search for queries that require very current, real-time, or broad general knowledge "
            "that is unlikely to be in a specific, static knowledge base (e.g., today's news, live data, very recent events)."
            "\n\nChoose one of the following routes:"
            "\n- 'rag': For queries about specific entities, historical facts, product details, procedures, or any information that would typically be found in a curated document collection (e.g., 'What is X?', 'How does Y work?', 'Explain Z policy')."
            "\n- 'web': For queries about current events, live data, very recent news, or broad general knowledge that requires up-to-date internet access (e.g., 'Who won the election yesterday?', 'What is the weather in London?', 'Latest news on technology')."
        )
    else:
        system_prompt += (
            "**Web search is currently DISABLED.** You **MUST NOT** choose the 'web' route."
            "If a query would normally require web search, you should attempt to answer it using RAG (if applicable) or directly from your general knowledge."
            "\n\nChoose one of the following routes:"
            "\n- 'rag': For queries about specific entities, historical facts, product details, procedures, or any information that would typically be found in a curated document collection, AND for queries that would normally go to web search but web search is disabled."
            "\n- 'answer': For very simple, direct questions you can answer without any external lookup (e.g., 'What is your name?')."
        )
        
    
    
    system_prompt += ( # prompt for answer route
        "\n- 'answer': For very simple, direct questions you can answer without any external lookup (e.g., 'What is your name?')."
        "\n- 'end': For pure greetings or small-talk where no factual answer is expected (e.g., 'Hi', 'How are you?'). If choosing 'end', you MUST provide a 'reply'."
        "\n\nExample routing decisions:"
        "\n- User: 'What are the treatment of diabetes?' -> Route: 'rag' (Factual knowledge, likely in KB)."
        "\n- User: 'What is the capital of France?' -> Route: 'rag' (Common knowledge, can be in KB or answered directly if LLM knows)."
        "\n- User: 'Who won the NBA finals last night?' -> Route: 'web' (Current event, requires live data)."
        "\n- User: 'How do I submit an expense report?' -> Route: 'rag' (Internal procedure)."
        "\n- User: 'Tell me about quantum computing.' -> Route: 'rag' (Foundational knowledge can be in KB. If KB is sparse, judge will route to web if enabled)."
        "\n- User: 'Hello there!' -> Route: 'end', reply='Hello! How can I assist you today?'"
    )

    messages = [
        ("system", system_prompt),
        ("user", query)
    ] 
    
    
    # we have system prompt and query , now we invoke the router_llm
    # we are storing in pydantic schema
    
    result: RouteDecision = router_llm.invoke(messages)
    
    # What is the initial router decision ? 
    
    initial_router_decision = result.route # Store LLMs raw decision
    router_override_reason = None
    
    # Override the router decision for web search
    # say user has not enabled the web_search option , but the query you are asking needs a websearch
    # So LLM will go for web search , but I want to work as User's requirement, hence we need to override LLM decision
    
    if not web_search_enabled and result.route == "web":
        #if my application needs to access the web,but user has not given the permission", hence we need to override the decision
        result.route = "rag" 
        # why the router has overriden ? 
        router_override_reason = "Web search disabled by user; redirected to RAG."
        print(f"Router decision overridden: changed from 'web' to 'rag' because web search is disabled.")
    
    # print router's final decision and reply
    print(f"Router final decision: {result.route}, Reply (if 'end'): {result.reply}")
    
    # now , we need to return all the information , initialize 'out' dictionary and store info
    out = {
        "messages": state["messages"], 
        "route": result.route,
        "web_search_enabled": web_search_enabled # Pass the flag along in the state
    }
    
    if router_override_reason: # Add override info for tracing
        out["initial_router_decision"] = initial_router_decision
        out["router_override_reason"] = router_override_reason

    if result.route == "end":
        out["messages"] = state["messages"] + [AIMessage(content=result.reply or "Hello!")]
    
    print("--- Exiting router_node ---")
    return out
    
    
# Define Node 2 : RAG LOOKUP

'''
RAG LOOKUP NODE
--------------------------------------------------------------------------------
PURPOSE:
Retrieves relevant information from the internal knowledge base (Pinecone) and judges its sufficiency to answer the query.

--------------------------------------------------------------------------------
INPUTS (from AgentState):
- messages: The current conversation history (to get the latest user query).
- web_search_enabled: User's preference for web search (True/False).

--------------------------------------------------------------------------------
CORE LOGIC / ACTIONS:
1. Extracts the latest user `query`.
2. Calls `rag_search_tool` (custom tool) to query Pinecone, retrieving top-K (e.g., 5) chunks.
3. **Sufficiency Judgment:** Calls `judge_llm` (Groq LLM with structured output `RagJudge`) to evaluate if the retrieved RAG `chunks` are sufficient to answer the `query`.

--------------------------------------------------------------------------------
OUTPUTS / UPDATES to AgentState:
- `rag`: The retrieved content chunks from the knowledge base.
- `route`: Updated based on sufficiency verdict and `web_search_enabled`:
  - `answer` (if sufficient)
  - `web` (if not sufficient AND web search is enabled)
  - `answer` (if not sufficient AND web search is disabled)
- `web_search_enabled`: Passed through.

--------------------------------------------------------------------------------
NEXT POSSIBLE NODES:
- `answer` (if RAG is sufficient, OR if RAG is not sufficient but web search is disabled)
- `web_search` (if RAG is not sufficient AND web search is enabled)
--------------------------------------------------------------------------------

'''

def rag_node(state: AgentState,config:RunnableConfig) -> AgentState:
    print("\n--- Entering rag_node ---")
    query = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
    # MODIFIED: Get web_search_enabled directly from the config
    web_search_enabled = config.get("configurable", {}).get("web_search_enabled", True) # <-- CHANGED LINE
    print(f"Router received web search info : {web_search_enabled}")
    print(f"RAG query: {query}")
    chunks = rag_search_tool.invoke(query)
    
    # logic to handle the chunks
    if chunks.startswith("RAG_ERROR::"):
        print(f"RAG Error: {chunks}. Checking web search enabled status.")
        # If RAG fails, and web search is enabled, try web. Otherwise, go to answer.
        next_route = "web" if web_search_enabled else "answer"
        return {**state, "rag": "", "route": next_route}

    if chunks:
        print(f"Retrieved RAG chunks (first 500 chars): {chunks[:500]}...")
    else:
        print("No RAG chunks retrieved.")

    judge_messages = [
        ("system", (
            "You are a judge evaluating if the **retrieved information** is **sufficient and relevant** "
            "to fully and accurately answer the user's question. "
            "Consider if the retrieved text directly addresses the question's core and provides enough detail."
            "If the information is incomplete, vague, outdated, or doesn't directly answer the question, it's NOT sufficient."
            "If it provides a clear, direct, and comprehensive answer, it IS sufficient."
            "If no relevant information was retrieved at all (e.g., 'No results found'), it is definitely NOT sufficient."
            "\n\nRespond ONLY with a JSON object: {\"sufficient\": true/false}"
            "\n\nExample 1: Question: 'What is the capital of France?' Retrieved: 'Paris is the capital of France.' -> {\"sufficient\": true}"
            "\nExample 2: Question: 'What are the symptoms of diabetes?' Retrieved: 'Diabetes is a chronic condition.' -> {\"sufficient\": false} (Doesn't answer symptoms)"
            "\nExample 3: Question: 'How to fix error X in software Y?' Retrieved: 'No relevant information found.' -> {\"sufficient\": false}"
        )),
        ("user", f"Question: {query}\n\nRetrieved info: {chunks}\n\nIs this sufficient to answer the question?")
    ]
    verdict: RagJudge = judge_llm.invoke(judge_messages)
    print(f"RAG Judge verdict: {verdict.sufficient}")
    print("--- Exiting rag_node ---")
    
    # NEW LOGIC: Decide next route based on sufficiency AND web_search_enabled
    if verdict.sufficient:
        next_route = "answer"
    else:
        next_route = "web" if web_search_enabled else "answer" # If not sufficient, only go to web if enabled
        print(f"RAG not sufficient. Web search enabled: {web_search_enabled}. Next route: {next_route}")

    return {
        **state,
        "rag": chunks,
        "route": next_route,
        "web_search_enabled": web_search_enabled # Pass the flag along
    }
    


# Define Node 3 : WEB SEARCH

'''
WEB SEARCH NODE
--------------------------------------------------------------------------------
PURPOSE:
Performs a real-time web search to gather external, up-to-date information.
Respects the user's `web_search_enabled` setting.

INPUTS (from AgentState):
- `messages`: The current conversation history (to get the latest user query).
- `web_search_enabled`: User's preference for web search (True/False).

CORE LOGIC / ACTIONS:
1. Extracts the latest user `query`.
2. **Web Search Check:** If `web_search_enabled` is `False`, it skips the actual web search and sets a placeholder message in `web` state.
3. If `web_search_enabled` is `True`, it calls `web_search_tool` (custom tool) to query the Tavily API and retrieve web snippets.

OUTPUTS / UPDATES to AgentState:
- `web`: The retrieved web snippets, or a message indicating web search was disabled.
- `route`: Always set to `answer` after this node.
- `web_search_enabled`: Passed through.

NEXT POSSIBLE NODES:
- `answer` (always)
--------------------------------------------------------------------------------

'''

def web_node(state: AgentState,config:RunnableConfig) -> AgentState:
    print("\n--- Entering web_node ---")
    query = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
    
    # Check if web search is actually enabled before performing it
    # MODIFIED: Get web_search_enabled directly from the config
    web_search_enabled = config.get("configurable", {}).get("web_search_enabled", True) # <-- CHANGED LINE
    print(f"Router received web search info : {web_search_enabled}")
    if not web_search_enabled:
        print("Web search node entered but web search is disabled. Skipping actual search.")
        return {**state, "web": "Web search was disabled by the user.", "route": "answer"}

    print(f"Web search query: {query}")
    snippets = web_search_tool.invoke(query)
    
    if snippets.startswith("WEB_ERROR::"):
        print(f"Web Error: {snippets}. Proceeding to answer with limited info.")
        return {**state, "web": "", "route": "answer"}

    print(f"Web snippets retrieved: {snippets[:200]}...")
    print("--- Exiting web_node ---")
    return {**state, "web": snippets, "route": "answer"}



# Define Node 4 : FINAL ANSWER

'''
ANSWER NODE : HERE WE NEED TO PROVIDE THE ENTIRE CONTEXT 
--------------------------------------------------------------------------------
PURPOSE:
Synthesizes all gathered information (from RAG and/or Web) and generates the final, coherent answer to the user's query.

INPUTS (from AgentState):
- `messages`: The current conversation history (to get the latest user query).
- `rag`: Content retrieved from the knowledge base.
- `web`: Content retrieved from web search (or a disabled message).

CORE LOGIC / ACTIONS:
1. Extracts the latest user `query`.
2. Combines `rag` and `web` content into a unified `context`.
   (Filters out "web search disabled" messages from `web` content).
3. Crafts a detailed prompt for `answer_llm` using the `query` and `context`.
4. Calls `answer_llm` (Groq LLM) to generate the final response.

OUTPUTS / UPDATES to AgentState:
- `messages`: Appends the generated AI's answer to the conversation history.

NEXT POSSIBLE NODES:
- `END` (always)
--------------------------------------------------------------------------------

'''

def answer_node(state: AgentState) -> AgentState:
    print("\n--- Entering answer_node ---")
    # user_q = user_query
    user_q = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
    
    ctx_parts = [] # context parts
    if state.get("rag"):  # if we come to asnwer node from RAG , then we need to add context from that state.
        ctx_parts.append("Knowledge Base Information:\n" + state["rag"])
    if state.get("web"): # if we come here from web search node, first check if web search was enabled
        # If web search was disabled, the 'web' field might contain a message like "Web search was disabled..."
        # We should only include actual search results here.
        if state["web"] and not state["web"].startswith("Web search was disabled"):
            ctx_parts.append("Web Search Results:\n" + state["web"])
    
    context = "\n\n".join(ctx_parts)
    if not context.strip():
        context = "No external context was available for this query. Try to answer based on general knowledge if possible."

    prompt = f"""Please answer the user's question using the provided context.
If the context is empty or irrelevant, try to answer based on your general knowledge.

Question: {user_q}

Context:
{context}

Provide a helpful, accurate, and concise response based on the available information."""

    print(f"Prompt sent to answer_llm: {prompt[:500]}...")
    ans = answer_llm.invoke([HumanMessage(content=prompt)]).content
    print(f"Final answer generated: {ans[:200]}...")
    print("--- Exiting answer_node ---")
    return {
        **state,
        "messages": state["messages"] + [AIMessage(content=ans)]
    }
    
    
    
# --- Routing helpers ---
def from_router(st: AgentState) -> Literal["rag", "web", "answer", "end"]:
    return st["route"]

def after_rag(st: AgentState) -> Literal["answer", "web"]:
    return st["route"]

def after_web(_) -> Literal["answer"]:
    return "answer"

# --- Build graph ---
def build_agent():
    """Builds and compiles the LangGraph agent."""
    g = StateGraph(AgentState)
    g.add_node("router", router_node)
    g.add_node("rag_lookup", rag_node)
    g.add_node("web_search", web_node)
    g.add_node("answer", answer_node)

    g.set_entry_point("router")
    
    g.add_conditional_edges(
        "router",
        from_router,
        {
            "rag": "rag_lookup",
            "web": "web_search",
            "answer": "answer",
            "end": END
        }
    )
    
    g.add_conditional_edges(
        "rag_lookup",
        after_rag,
        {
            "answer": "answer",
            "web": "web_search"
        }
    )
    
    g.add_edge("web_search", "answer")
    g.add_edge("answer", END)

    agent = g.compile(checkpointer=MemorySaver())
    return agent

rag_agent = build_agent()