#!/usr/bin/env python3
"""Entry point — interactive REPL for the Azure agent."""
import os
from dotenv import load_dotenv

load_dotenv()

from agent import AzureAgent


def main() -> None:
    print("Azure Agent  (type 'exit' or 'quit' to stop, 'reset' to clear history)\n")
    agent = AzureAgent()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Bye.")
            break
        if user_input.lower() == "reset":
            agent.reset()
            print("Agent: Conversation history cleared.\n")
            continue

        response = agent.chat(user_input)
        print(f"\nAgent: {response}\n")


if __name__ == "__main__":
    main()
