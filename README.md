# PolicyBot

A Retrieval-Augmented Generation (RAG) assistant that answers employee questions **only** from official company policy documents. Every answer cites its source. If the answer is not in the documents, the bot says so and offers to escalate the question to HR instead of guessing.

> Sample data in this repo is fictional (Acme Technologies Pvt. Ltd.).

## What it does

- **Employees** log in and ask questions in a chat page ("How many casual leaves do I get?"). Answers show the document, section and page they came from.
- **HR admins** log in with the same account type, upload and manage policy documents, and answer escalated questions. Admins can also use the chat to test a new policy.
- **Stays on topic.** Coding help, general chat and jokes are refused. Prompt-injection attempts ("ignore your rules...") are refused too.
- **Never guesses.** If nothing relevant is retrieved, it replies: *"I don't know. I couldn't find this in the company policies. Please contact HR."* and shows an **Escalate to HR** button.
