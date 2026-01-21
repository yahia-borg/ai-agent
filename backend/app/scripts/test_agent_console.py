from app.agent.core import get_agent_graph
from langchain_core.messages import HumanMessage
import sys

def chat_console():
    app = get_agent_graph()
    
    # We maintain a list of messages for state, though LangGraph's "checkpointer" could usually handle threading.
    # For a simple console loop without persistence, we can just feed a growing list or use invoke's return.
    # However, LangGraph is often stateless per invocation unless we use a Checkpointer. 
    # Let's keep a local history and pass it in for this simple test.
    chat_history = [] 
    
    print("--- Construction Agent Console (LangGraph) (Type 'exit' to quit) ---")
    
    while True:
        try:
            user_input = input("User: ")
            if user_input.lower() in ["exit", "quit"]:
                break
            
            chat_history.append(HumanMessage(content=user_input))
            
            # Invoke the graph
            # The output state will contain the full updated list of messages
            final_state = app.invoke({"messages": chat_history})
            
            # Update our local history with the new messages from the agent
            # The agent might have added multiple messages (Tool calls, Tool outputs, Final response)
            chat_history = final_state["messages"]
            
            # The last message should be the AI's final answer
            last_msg = chat_history[-1]
            print(f"Agent: {last_msg.content}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    chat_console()
